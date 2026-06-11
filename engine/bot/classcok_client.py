"""
클래스콕 자동화 클라이언트 — Playwright 컨텍스트 관리 및 전체 실행 오케스트레이션.

Persistent Context로 세션 쿠키를 재사용하며,
세션 만료 시 Firestore에 SESSION_EXPIRED를 기록하고 대시보드에 알린다.
"""
from __future__ import annotations

import json
import queue
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext

from src.utils import firebase_client as fb
from src.utils.screenshot_uploader import upload_screenshot
from engine.bot.login_handler import ensure_logged_in
from engine.bot.form_filler import register_month
from engine.parser import excel_parser
from engine.scheduler.week_splitter import compute as compute_split

USER_DATA_DIR = str(Path("tmp/browser_profile"))


async def run(
    branch_id: str,
    target_month: str,
    instructor_ids: list[str],
    excel_path: str,
    run_id: str,
    headless: bool = True,
    sms_queue: queue.Queue | None = None,
) -> dict:
    """
    강좌 자동 등록 전체 플로우를 실행한다.

    Args:
        branch_id: 지점 코드 (예: "dongtan")
        target_month: "YYYY-MM" 형식
        instructor_ids: 등록할 강사 ID 목록 (빈 리스트면 전체)
        excel_path: 엑셀 파일 경로
        run_id: 로그 기록용 실행 ID
        headless: True=헤드리스(Actions), False=headed(로컬 모니터링)
        sms_queue: SMS 인증번호 전달 큐

    Returns:
        {"success": [...], "failed": [...], "status": "done"|"partial"|"failed"}
    """
    year = int(target_month.split("-")[0])
    month = int(target_month.split("-")[1])

    fb.set_run_status(run_id, "running", branch_id, target_month)
    fb.append_log(run_id, f"자동화 시작 — {target_month} / headless={headless}", "info")

    # 강사 목록 로드
    all_instructors = fb.get_instructors(branch_id)
    if instructor_ids:
        instructors = [i for i in all_instructors if i.get("instructor_id") in instructor_ids]
    else:
        instructors = all_instructors

    if not instructors:
        fb.append_log(run_id, "등록할 강사 없음 — 종료", "error")
        fb.set_run_status(run_id, "failed")
        return {"success": [], "failed": [], "status": "failed"}

    success_list: list[str] = []
    failed_list: list[str] = []

    async with async_playwright() as pw:
        context = await _build_context(pw, headless, run_id)

        # 로그인 (세션 재사용 또는 신규 로그인)
        logged_in = await ensure_logged_in(context, run_id, sms_queue)
        if not logged_in:
            fb.append_log(run_id, "로그인 실패 — 전체 중단", "error")
            fb.set_run_status(run_id, "failed")
            await context.close()
            return {"success": [], "failed": [i.get("instructor_id") for i in instructors], "status": "failed"}

        # 로그인 후 스크린샷
        _page = await context.new_page()
        try:
            await _page.goto("https://sas.classkok.com", timeout=15000)
            shot = await _page.screenshot(full_page=False)
            url = upload_screenshot(shot, run_id, "login_done")
            fb.append_log(run_id, "로그인 완료 — 클래스콕 진입", "success", url)
        except Exception:
            fb.append_log(run_id, "로그인 완료", "success")
        finally:
            await _page.close()

        for inst in instructors:
            inst_id = inst.get("instructor_id", "")
            inst_name = inst.get("name", inst_id)
            sheet = inst.get("excel_data_path", "")
            day = inst.get("day_of_week", "?")

            fb.append_log(run_id, f"── {inst_name} 등록 시작 ──", "info")

            try:
                month_data = excel_parser.parse(excel_path, sheet, month, year)
                split = compute_split(year, month, day) if day != "?" else None

                page = await context.new_page()
                results = await register_month(page, inst, month_data, split, run_id)

                # 강사 등록 완료 스크린샷
                try:
                    shot = await page.screenshot(full_page=False)
                    url = upload_screenshot(shot, run_id, f"{inst_id}_done")
                    fb.append_log(run_id, f"{inst_name} 등록 화면", "info", url)
                except Exception:
                    pass

                await page.close()

                all_ok = all(results.values())
                if all_ok:
                    success_list.append(inst_id)
                    fb.append_log(run_id, f"{inst_name} 전체 등록 완료 ✅", "success")
                else:
                    failed_list.append(inst_id)
                    failed_weeks = [w for w, ok in results.items() if not ok]
                    fb.append_log(run_id, f"{inst_name} 일부 실패: {failed_weeks}주", "error")

            except Exception as e:
                # 오류 시 스크린샷
                try:
                    ep = await context.new_page()
                    shot = await ep.screenshot(full_page=False)
                    url = upload_screenshot(shot, run_id, f"{inst_id}_error")
                    fb.append_log(run_id, f"{inst_name} 오류: {e}", "error", url)
                    await ep.close()
                except Exception:
                    fb.append_log(run_id, f"{inst_name} 오류: {e}", "error")
                failed_list.append(inst_id)

        await context.close()

    status = "done" if not failed_list else ("partial" if success_list else "failed")
    fb.set_run_status(run_id, status)
    fb.append_log(
        run_id,
        f"완료 — 성공: {len(success_list)}명 / 실패: {len(failed_list)}명",
        "success" if status == "done" else "warn",
    )

    return {"success": success_list, "failed": failed_list, "status": status}


async def _build_context(pw, headless: bool, run_id: str) -> BrowserContext:
    """저장된 쿠키를 주입한 BrowserContext를 생성한다."""
    Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)

    browser = await pw.chromium.launch(
        headless=headless,
        args=["--no-sandbox", "--disable-dev-shm-usage"] if headless else [],
    )

    # 저장된 쿠키 복원
    storage_state = None
    cookie_json = fb.load_session_cookie()
    if cookie_json:
        try:
            storage_state = json.loads(cookie_json)
            fb.append_log(run_id, "저장된 세션 쿠키 로드 완료", "info")
        except json.JSONDecodeError:
            fb.append_log(run_id, "쿠키 파싱 실패 — 신규 로그인 진행", "warn")

    context = await browser.new_context(
        storage_state=storage_state,
        viewport={"width": 1280, "height": 900},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    return context
