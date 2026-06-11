"""
클래스콕 강좌 등록 폼 자동 입력.

설계 원칙:
  - XPath 중심 셀렉터 (동적 ID 변동 대응)
  - 인간 모방 딜레이: random.uniform(100, 300)ms
  - Claude Self-Healing: TimeoutError 시 DOM 스냅샷 → 대체 셀렉터 1회 재시도
"""
from __future__ import annotations

import asyncio
import os
import random

from playwright.async_api import Page, TimeoutError as PWTimeout

from engine.parser.excel_parser import WeekData, MonthData
from engine.scheduler.week_splitter import SplitResult, CourseType
from src.utils import firebase_client as fb

FILL_TIMEOUT = 8_000
NAV_TIMEOUT = 15_000


# ── 딜레이 헬퍼 ─────────────────────────────────────────────────────────────

async def human_delay(min_ms: float = 100, max_ms: float = 300) -> None:
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


# ── Self-Healing ─────────────────────────────────────────────────────────────

async def _heal_selector(page: Page, hint: str, run_id: str) -> str | None:
    """
    DOM 스냅샷을 Claude API에 전달하고 대체 XPath 셀렉터를 반환한다.
    Claude API 미설정 시 None 반환.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    try:
        import anthropic
        dom = await page.content()
        dom_snippet = dom[:6000]  # 토큰 절약: 앞 6000자만 전송

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            messages=[{
                "role": "user",
                "content": (
                    f"아래 HTML에서 '{hint}'에 해당하는 요소의 XPath를 한 줄로만 반환해. "
                    f"다른 설명 없이 XPath만:\n\n{dom_snippet}"
                ),
            }],
        )
        xpath = msg.content[0].text.strip().strip('"').strip("'")
        fb.append_log(run_id, f"Self-Healing 셀렉터: {xpath}", "warn")
        return xpath if xpath.startswith("//") else None
    except Exception as e:
        fb.append_log(run_id, f"Self-Healing 실패: {e}", "error")
        return None


async def _safe_fill(page: Page, xpath: str, value: str, hint: str, run_id: str) -> bool:
    """XPath로 입력 시도. 실패 시 Self-Healing 후 1회 재시도."""
    try:
        await page.fill(xpath, value, timeout=FILL_TIMEOUT)
        return True
    except PWTimeout:
        fb.append_log(run_id, f"셀렉터 실패 ({hint}) — Self-Healing 시도", "warn")
        healed = await _heal_selector(page, hint, run_id)
        if healed:
            try:
                await page.fill(healed, value, timeout=FILL_TIMEOUT)
                return True
            except PWTimeout:
                pass
        fb.append_log(run_id, f"Self-Healing 실패 ({hint}) — 수동 확인 필요", "error")
        return False


async def _safe_click(page: Page, xpath: str, hint: str, run_id: str) -> bool:
    try:
        await page.click(xpath, timeout=FILL_TIMEOUT)
        return True
    except PWTimeout:
        fb.append_log(run_id, f"클릭 실패 ({hint}) — Self-Healing 시도", "warn")
        healed = await _heal_selector(page, hint, run_id)
        if healed:
            try:
                await page.click(healed, timeout=FILL_TIMEOUT)
                return True
            except PWTimeout:
                pass
        fb.append_log(run_id, f"Self-Healing 실패 ({hint})", "error")
        return False


# ── 강좌 등록 네비게이션 ─────────────────────────────────────────────────────

async def navigate_to_new_course(page: Page, run_id: str) -> bool:
    """강좌 신규 등록 페이지로 이동한다."""
    try:
        # 강좌 관리 메뉴 → 신규 등록 버튼
        await _safe_click(page, "//a[contains(text(),'강좌') or contains(@href,'course')]", "강좌 메뉴", run_id)
        await human_delay(400, 700)
        await _safe_click(page, "//button[contains(text(),'등록') or contains(text(),'추가') or contains(text(),'신규')]", "신규 등록 버튼", run_id)
        await human_delay(500, 900)
        fb.append_log(run_id, "강좌 신규 등록 페이지 진입", "info")
        return True
    except Exception as e:
        fb.append_log(run_id, f"강좌 등록 페이지 이동 실패: {e}", "error")
        return False


# ── 강좌 폼 입력 ─────────────────────────────────────────────────────────────

async def fill_course_form(
    page: Page,
    instructor: dict,
    week: WeekData,
    year: int,
    month: int,
    run_id: str,
    is_special: bool = False,
) -> bool:
    """
    강좌 등록 폼의 각 필드를 순서대로 자동 입력한다.

    필드 순서: 강의명 → 요일/시간 → 커리큘럼 → 준비물
    """
    title = f"[특강] {week.title}" if is_special else week.title
    time_slot = instructor.get("time_slot", "")
    day = instructor.get("day_of_week", "")
    age = instructor.get("recommended_age", "")

    fb.append_log(run_id, f"폼 입력 시작: {title}", "info")

    # 1. 강의명
    ok = await _safe_fill(
        page,
        "//input[preceding-sibling::label[contains(text(),'강의명')] or @placeholder[contains(.,'강의명') or contains(.,'수업명')]]",
        title, "강의명 입력란", run_id,
    )
    if not ok:
        return False
    await human_delay(150, 300)

    # 2. 수강 연령
    if age:
        await _safe_fill(
            page,
            "//input[preceding-sibling::label[contains(text(),'연령') or contains(text(),'나이')]]",
            age, "수강연령 입력란", run_id,
        )
        await human_delay(120, 250)

    # 3. 요일 선택 (드롭다운 or 체크박스)
    try:
        day_selector = f"//select[preceding-sibling::label[contains(text(),'요일')]]"
        select_el = page.locator(day_selector)
        if await select_el.count() > 0:
            await select_el.select_option(label=f"{day}요일")
        else:
            await _safe_click(page, f"//label[contains(text(),'{day}요일')] | //input[@value='{day}']", f"{day}요일 선택", run_id)
        await human_delay(150, 300)
    except Exception:
        fb.append_log(run_id, f"요일 선택 스킵 (수동 확인 필요): {day}요일", "warn")

    # 4. 시간 입력
    if time_slot and "~" in time_slot:
        start_t, end_t = time_slot.split("~")
        await _safe_fill(
            page,
            "//input[@type='time' or preceding-sibling::label[contains(text(),'시작')]][1]",
            start_t.strip(), "수업 시작시간", run_id,
        )
        await human_delay(120, 250)
        await _safe_fill(
            page,
            "//input[@type='time' or preceding-sibling::label[contains(text(),'종료') or contains(text(),'끝')]][last()]",
            end_t.strip(), "수업 종료시간", run_id,
        )
        await human_delay(120, 250)

    # 5. 커리큘럼 (활동 내용)
    await _safe_fill(
        page,
        "//textarea[preceding-sibling::label[contains(text(),'커리큘럼') or contains(text(),'내용') or contains(text(),'소개')]]",
        week.content, "커리큘럼/활동내용 입력란", run_id,
    )
    await human_delay(200, 400)

    # 6. 준비물
    await _safe_fill(
        page,
        "//textarea[preceding-sibling::label[contains(text(),'준비물')]] | //input[preceding-sibling::label[contains(text(),'준비물')]]",
        week.supplies, "준비물 입력란", run_id,
    )
    await human_delay(200, 400)

    # 7. 저장 버튼
    saved = await _safe_click(
        page,
        "//button[@type='submit' or contains(text(),'저장') or contains(text(),'등록')]",
        "저장 버튼", run_id,
    )
    if not saved:
        return False

    await human_delay(800, 1500)
    fb.append_log(run_id, f"폼 저장 완료: {title}", "success")
    return True


# ── 월별 전체 등록 오케스트레이션 ───────────────────────────────────────────

async def register_month(
    page: Page,
    instructor: dict,
    month_data: MonthData,
    split: SplitResult,
    run_id: str,
) -> dict[int, bool]:
    """
    한 강사의 한 달치 강좌를 전체 등록한다.

    Returns:
        {week_num: 성공여부} 딕셔너리
    """
    results: dict[int, bool] = {}

    for week in month_data.weeks:
        is_special = (
            split.course_type == CourseType.SPLIT_3_1
            and week.week == split.special_week
        )

        fb.append_log(
            run_id,
            f"{instructor.get('name')} {week.week}주 등록 시작"
            + (" (특강)" if is_special else ""),
            "info",
        )

        ok = await navigate_to_new_course(page, run_id)
        if not ok:
            results[week.week] = False
            continue

        ok = await fill_course_form(
            page, instructor, week,
            month_data.year, month_data.month,
            run_id, is_special,
        )
        results[week.week] = ok

        if ok:
            fb.save_course(
                "dongtan",
                instructor.get("instructor_id", ""),
                f"{month_data.year}{month_data.month:02d}",
                {f"week_{week.week}_status": "done", f"week_{week.week}_title": week.title},
            )
        await human_delay(500, 1000)

    return results
