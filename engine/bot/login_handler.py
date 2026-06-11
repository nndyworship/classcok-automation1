"""
클래스콕 어드민 로그인 핸들러.

흐름:
  1. Firestore에서 저장된 쿠키 복호화 → storage_state 주입
  2. 세션 유효성 확인 (어드민 메인 페이지 접근 가능 여부)
  3. 만료 시 → ID/PW 입력 → SMS 2차 인증 대기 → 쿠키 재저장
"""
from __future__ import annotations

import asyncio
import json
import os
import queue

from playwright.async_api import Page, BrowserContext, TimeoutError as PWTimeout

from src.utils import firebase_client as fb
from engine.bot.form_filler import human_delay

ADMIN_URL = "https://www.classcok.com"
LOGIN_URL = f"{ADMIN_URL}/login"
ADMIN_CHECK_PATH = "/admin"
LOGIN_TIMEOUT = 15_000
SMS_WAIT_TIMEOUT = 120_000


async def ensure_logged_in(
    context: BrowserContext,
    run_id: str,
    sms_queue: queue.Queue | None = None,
) -> bool:
    """
    세션을 확인하고 필요 시 로그인을 수행한다.

    Args:
        context: Playwright BrowserContext (storage_state 미리 주입됐을 수 있음)
        run_id: 로그 기록용 실행 ID
        sms_queue: SMS 인증번호를 외부에서 전달하는 큐 (None이면 stdin 사용)

    Returns:
        True: 로그인 성공  False: 실패
    """
    page = await context.new_page()
    try:
        if await _is_session_valid(page, run_id):
            return True
        return await _do_login(page, context, run_id, sms_queue)
    finally:
        await page.close()


async def _is_session_valid(page: Page, run_id: str) -> bool:
    """저장된 쿠키로 어드민에 진입 가능한지 확인한다."""
    try:
        await page.goto(ADMIN_URL + ADMIN_CHECK_PATH, timeout=LOGIN_TIMEOUT)
        await human_delay(300, 600)
        if "login" not in page.url.lower():
            fb.append_log(run_id, "세션 유효 — 재로그인 불필요", "success")
            return True
    except PWTimeout:
        pass
    fb.append_log(run_id, "세션 만료 또는 미존재 — 로그인 시도", "warn")
    return False


async def _do_login(
    page: Page,
    context: BrowserContext,
    run_id: str,
    sms_queue: queue.Queue | None,
) -> bool:
    """ID/PW 입력 후 SMS 2차 인증을 처리한다."""
    classcok_id = os.getenv("CLASSCOK_ID", "")
    classcok_pw = os.getenv("CLASSCOK_PW", "")

    if not classcok_id or not classcok_pw:
        fb.append_log(run_id, "CLASSCOK_ID / CLASSCOK_PW 환경변수 미설정", "error")
        return False

    try:
        await page.goto(LOGIN_URL, timeout=LOGIN_TIMEOUT)
        await human_delay(400, 800)

        # ID / PW 입력 (XPath 기반 — 동적 ID 변동 대응)
        await page.fill("//input[@type='text' or @name='id' or @placeholder[contains(.,'아이디')]]", classcok_id)
        await human_delay(150, 300)
        await page.fill("//input[@type='password']", classcok_pw)
        await human_delay(200, 400)
        await page.click("//button[@type='submit' or contains(text(),'로그인')]")
        await human_delay(500, 900)

        fb.append_log(run_id, "ID/PW 입력 완료 — SMS 인증 대기", "info")

        # SMS 인증번호 대기
        sms_code = await _wait_for_sms(sms_queue)
        if not sms_code:
            fb.append_log(run_id, "SMS 인증번호 미수신 — 타임아웃", "error")
            fb.mark_session_expired()
            return False

        # SMS 입력창 탐색 및 입력
        sms_input = page.locator(
            "//input[@type='number' or @placeholder[contains(.,'인증')] or @maxlength='6']"
        )
        await sms_input.fill(sms_code)
        await human_delay(200, 400)
        await page.click("//button[contains(text(),'확인') or contains(text(),'인증')]")
        await human_delay(800, 1200)

        # 로그인 성공 확인
        if "login" in page.url.lower():
            fb.append_log(run_id, "SMS 인증 실패 또는 비밀번호 오류", "error")
            return False

        # 쿠키 저장
        storage = await context.storage_state()
        fb.save_session_cookie(json.dumps(storage))
        fb.append_log(run_id, "로그인 성공 — 세션 쿠키 저장 완료", "success")
        return True

    except PWTimeout as e:
        fb.append_log(run_id, f"로그인 타임아웃: {e}", "error")
        return False
    except Exception as e:
        fb.append_log(run_id, f"로그인 오류: {e}", "error")
        return False


async def _wait_for_sms(sms_queue: queue.Queue | None, timeout: float = 120.0) -> str:
    """SMS 인증번호를 큐 또는 stdin에서 대기한다."""
    if sms_queue is not None:
        loop = asyncio.get_event_loop()
        try:
            code = await asyncio.wait_for(
                loop.run_in_executor(None, sms_queue.get),
                timeout=timeout,
            )
            return str(code).strip()
        except asyncio.TimeoutError:
            return ""
    # 로컬 headed 모드: stdin에서 직접 입력
    print("\n[SMS 인증] 문자로 받은 인증번호를 입력하세요: ", end="", flush=True)
    loop = asyncio.get_event_loop()
    try:
        code = await asyncio.wait_for(
            loop.run_in_executor(None, input),
            timeout=timeout,
        )
        return code.strip()
    except asyncio.TimeoutError:
        return ""
