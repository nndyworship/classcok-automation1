"""
클래스콕 강좌 등록 폼 자동 입력.

DHTMLX 기반 폼의 JavaScript API를 page.evaluate()로 직접 호출한다.
XPath/CSS 셀렉터 불필요 — 글로벌 JS 변수(frmLect, frmLectCrclm, frmLectDetail)를
직접 조작한다.
"""
from __future__ import annotations

import asyncio
import random
from calendar import monthrange
from datetime import date, timedelta

from playwright.async_api import Page, Dialog

from engine.parser.excel_parser import MonthData
from engine.scheduler.week_splitter import SplitResult, CourseType
from src.utils import firebase_client as fb

REGISTER_URL = "https://sas.classkok.com/olt/lectureNew/save/init.do?openMenuCd=OLT0430011"
NAV_TIMEOUT = 20_000

# 요일 한글 → weekDayGroup checkbox key
DAY_MAP = {
    "일": "sunChk",
    "월": "monChc",
    "화": "tueChc",
    "수": "wedChc",
    "목": "thuChc",
    "금": "friChc",
    "토": "satChc",
}

# 커리큘럼 그리드 내용 컬럼 후보 (우선순위 순)
_CONTENT_KEY_CANDIDATES = ["CNTNT", "CTNT", "CONTENT", "LCTR_CNTNT", "CRCLM_CNTNT"]


async def _delay(min_ms: float = 150, max_ms: float = 350) -> None:
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


async def _js(page: Page, script: str, arg=None):
    """page.evaluate 래퍼."""
    if arg is None:
        return await page.evaluate(script)
    return await page.evaluate(script, arg)


async def _set(page: Page, form: str, field: str, value) -> None:
    """DHTMLX form 필드에 값을 설정한다."""
    await _js(
        page,
        f"([f, v]) => {{ var fm = window['{form}']; fm && fm.getItem && fm.getItem(f) && fm.getItem(f).setValue(v); }}",
        [field, value],
    )


async def _wait_forms(page: Page) -> None:
    """DHTMLX 폼 초기화 완료 대기."""
    await page.wait_for_function(
        "() => typeof frmLect !== 'undefined' "
        "&& typeof frmLectCrclm !== 'undefined' "
        "&& typeof frmLectDetail !== 'undefined'",
        timeout=NAV_TIMEOUT,
    )
    await _delay(500, 800)


# ── 강사 선택 ────────────────────────────────────────────────────────────────

async def _select_instructor(page: Page, instructor: dict, run_id: str) -> bool:
    """강사 조회 → 선택."""
    name = instructor.get("name", "")
    if not name:
        return False
    try:
        # 강사명 입력 후 조회
        await _js(page, "(n) => { var el = document.querySelector('#searchInstrArea input[type=text]'); if(el){ el.value=n; } }", name)
        await _js(page, "() => { var btn = document.querySelector('#searchInstrArea button'); if(btn) btn.click(); }")
        await _delay(800, 1200)

        # 그리드에서 강사 행 선택 후 추가
        added = await _js(page, f"""(nm) => {{
            if(typeof grdInstr === 'undefined') return false;
            var data = AUIGrid.getGridData(grdInstr);
            for(var i=0;i<data.length;i++){{
                var n = data[i].USER_NM || data[i].INSTR_NM || data[i].NM || "";
                if(n.indexOf(nm) >= 0){{
                    AUIGrid.setSelectedRowsByValue(grdInstr, i);
                    return true;
                }}
            }}
            return false;
        }}""", name)

        if added:
            # "추가" 버튼 클릭
            await _js(page, "() => { var btn = document.querySelector('#instrAreaBtn button, button[onclick*=\"addInstr\"]'); if(btn) btn.click(); }")
            await _delay(400, 600)
            fb.append_log(run_id, f"강사 선택 완료: {name}", "info")
            return True

        fb.append_log(run_id, f"강사 조회 결과 없음: {name} (수동 확인 필요)", "warn")
        return False
    except Exception as e:
        fb.append_log(run_id, f"강사 선택 오류: {e}", "warn")
        return False


# ── 커리큘럼 그리드 ──────────────────────────────────────────────────────────

async def _fill_curriculum_grid(page: Page, month_data: MonthData, split: SplitResult | None, run_id: str) -> None:
    """커리큘럼 그리드 각 행의 내용 컬럼을 주차별로 채운다."""
    try:
        row_count = await _js(page, "() => typeof grdCrclm !== 'undefined' ? AUIGrid.getRowCount(grdCrclm) : 0")
        if not row_count:
            fb.append_log(run_id, "커리큘럼 그리드 행 없음 — 커리큘럼 생성 필요", "warn")
            return

        # 첫 행 데이터로 내용 컬럼 키 탐색
        first_row = await _js(page, "() => AUIGrid.getGridData(grdCrclm)[0] || {}")
        content_key = next((k for k in _CONTENT_KEY_CANDIDATES if k in first_row), None)
        if not content_key:
            # fallback: 문자열 값 가진 키 중 날짜/시간 외 첫 번째
            skip = {"DATE", "DT", "DAY", "TIME", "HR", "MIN", "SEQ", "NO", "YN"}
            content_key = next((k for k, v in first_row.items() if isinstance(v, str) and k.upper() not in skip), None)

        if not content_key:
            fb.append_log(run_id, "커리큘럼 내용 컬럼 키 탐색 실패", "warn")
            return

        # 정기 주차 순서대로 채우기 (특강 주차 제외)
        target_weeks = [
            w for w in month_data.weeks
            if not (split and split.course_type == CourseType.SPLIT_3_1 and w.week == split.special_week)
        ]

        for i, week in enumerate(target_weeks):
            if i >= row_count:
                break
            await _js(
                page,
                "([idx, key, val]) => { var item = {}; item[key] = val; AUIGrid.updateRow(grdCrclm, idx, item); }",
                [i, content_key, week.content],
            )
            await _delay(80, 150)

        fb.append_log(run_id, f"커리큘럼 그리드 {len(target_weeks)}주 입력 완료", "info")
    except Exception as e:
        fb.append_log(run_id, f"커리큘럼 그리드 입력 오류: {e}", "warn")


# ── 날짜 계산 ────────────────────────────────────────────────────────────────

def _course_period(month_data: MonthData, split: SplitResult | None, is_special: bool) -> tuple[str, str]:
    """정기/특강 강좌기간 시작·종료일 반환."""
    year, month = month_data.year, month_data.month
    weeks = month_data.weeks
    if not weeks:
        last = monthrange(year, month)[1]
        return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last:02d}"

    if is_special and split:
        target = [w for w in weeks if w.week == split.special_week] or [weeks[-1]]
    elif split and split.course_type == CourseType.SPLIT_3_1:
        target = [w for w in weeks if w.week != split.special_week] or weeks
    else:
        target = weeks

    # WeekData에 date 속성이 있으면 사용, 없으면 주차로 추정
    def _dt(w) -> date:
        if hasattr(w, "date") and w.date:
            return w.date
        return date(year, month, 1) + timedelta(weeks=w.week - 1)

    return _dt(target[0]).strftime("%Y-%m-%d"), _dt(target[-1]).strftime("%Y-%m-%d")


# ── 텍스트 빌더 ──────────────────────────────────────────────────────────────

def _build_intro(month_data: MonthData, split: SplitResult | None, is_special: bool) -> str:
    lines = []
    for w in month_data.weeks:
        is_sp = bool(split and split.course_type == CourseType.SPLIT_3_1 and w.week == split.special_week)
        if is_special == is_sp:
            lines.append(f"[{w.week}주] {w.content}")
    return "\n".join(lines)


def _build_supplies(month_data: MonthData, split: SplitResult | None, is_special: bool) -> str:
    seen: list[str] = []
    for w in month_data.weeks:
        is_sp = bool(split and split.course_type == CourseType.SPLIT_3_1 and w.week == split.special_week)
        if is_special == is_sp and w.supplies and w.supplies not in seen:
            seen.append(w.supplies)
    return ", ".join(seen)


def _build_name(instructor: dict, month_data: MonthData, is_special: bool) -> str:
    prefix = instructor.get("course_name_prefix") or f"오감팡팡 {instructor.get('name', '')}"
    tag = "[원데이] " if is_special else ""
    return f"{tag}{prefix} {month_data.month}월"


# ── 메인 등록 함수 ────────────────────────────────────────────────────────────

async def register_course(
    page: Page,
    instructor: dict,
    month_data: MonthData,
    split: SplitResult | None,
    run_id: str,
    is_special: bool = False,
) -> bool:
    """강좌 신규 등록 페이지에서 한 강좌를 저장한다."""
    course_name = _build_name(instructor, month_data, is_special)
    fb.append_log(run_id, f"강좌 등록 시작: {course_name}", "info")

    # 페이지 진입
    await page.goto(REGISTER_URL, timeout=NAV_TIMEOUT, wait_until="networkidle")
    await _wait_forms(page)

    # dialog(alert) 자동 수락
    async def _accept(d: Dialog):
        await d.accept()
    page.on("dialog", _accept)

    try:
        # ── 기본정보 ────────────────────────────────────────────────────────
        fdtr_yn = "N" if is_special else "Y"
        await _set(page, "frmLect", "FDTR_YN", fdtr_yn)
        await _delay(300, 500)

        await _set(page, "frmLect", "LCTR_NM", course_name)
        await _delay(150, 250)

        if v := instructor.get("category_group_main"):
            await _set(page, "frmLect", "CATEGORY_GROUP_MAIN", v)
            await _delay(250, 400)

        if v := instructor.get("category_main"):
            await _set(page, "frmLect", "CATEGORY_MAIN", v)
            await _delay(200, 350)

        tkcrs = instructor.get("tkcrs_type", "Y")  # Y=자녀, N=성인, X=커플/패밀리
        await _set(page, "frmLect", "CHLDR_TKCRS_SBSCT_AVLBL_YN", tkcrs)
        await _delay(150, 250)

        # ── 수강 일정 ────────────────────────────────────────────────────────
        if v := instructor.get("room_code"):
            await _set(page, "frmLectCrclm", "LCTRM_CD", v)
            await _delay(200, 400)

        if v := str(instructor.get("capacity", "")):
            await _set(page, "frmLectCrclm", "FNP_PRCNT", v)
            await _delay(100, 200)

        start_date, end_date = _course_period(month_data, split, is_special)
        await _set(page, "frmLectCrclm", "LCTR_BEGIN", start_date)
        await _delay(300, 500)
        await _set(page, "frmLectCrclm", "LCTR_TRMNT", end_date)
        await _delay(300, 500)

        time_slot = instructor.get("time_slot", "")
        if time_slot and "~" in time_slot:
            st, et = [t.strip() for t in time_slot.split("~")]
            sh, sm = st.split(":")
            eh, em = et.split(":")
            await _set(page, "frmLectCrclm", "lctrBeginHour", sh)
            await _set(page, "frmLectCrclm", "lctrBeginMin", sm)
            await _set(page, "frmLectCrclm", "lctrTrmntHour", eh)
            await _set(page, "frmLectCrclm", "lctrTrmntMin", em)
            await _delay(150, 300)

        day = instructor.get("day_of_week", "")
        if day_key := DAY_MAP.get(day):
            await _js(
                page,
                "(key) => { var v = {}; v[key] = true; frmLectCrclm && frmLectCrclm.getItem('weekDayGroup') && frmLectCrclm.getItem('weekDayGroup').setValue(v); }",
                day_key,
            )
            await _delay(200, 350)

        # 접수시작일: 강좌 시작 2주 전
        acpt_start = (date.fromisoformat(start_date) - timedelta(weeks=2)).strftime("%Y-%m-%d")
        await _set(page, "frmLectCrclm", "ACPT_BEGIN_DTM", acpt_start)
        await _delay(150, 250)

        # ── 커리큘럼 생성 (정기만) ───────────────────────────────────────────
        if not is_special:
            await _js(page, """() => {
                var btns = document.querySelectorAll('[id*="crclmCreate"], button');
                for(var b of btns){ if(b.textContent.trim()==='커리큘럼 생성'){ b.click(); break; } }
            }""")
            await _delay(1200, 1800)
            await _fill_curriculum_grid(page, month_data, split, run_id)

        # ── 상세정보 ────────────────────────────────────────────────────────
        intro = _build_intro(month_data, split, is_special)
        await _set(page, "frmLectDetail", "INTRD_CNTNT", intro)
        await _delay(150, 250)

        supplies = _build_supplies(month_data, split, is_special)
        if supplies:
            await _set(page, "frmLectDetail", "PRPRN_THING_DSCRT", supplies)
            await _delay(100, 200)

        if v := str(instructor.get("price", "")):
            await _set(page, "frmLectDetail", "DC_BFR_STDY_AMT", v)
            await _delay(100, 200)

        if v := instructor.get("adult_agrp"):
            await _js(page, "(v) => frmLectDetail && frmLectDetail.getItem('ADULT_AGRP') && frmLectDetail.getItem('ADULT_AGRP').setValue([v])", v)
            await _delay(100, 200)

        if v := instructor.get("search_keywords", ""):
            await _set(page, "frmLectDetail", "SRCH_KYWRD_CNTNT", v)
            await _delay(100, 200)

        # ── 강사 선택 ────────────────────────────────────────────────────────
        await _select_instructor(page, instructor, run_id)

        # ── 저장 ─────────────────────────────────────────────────────────────
        fb.append_log(run_id, f"저장 클릭: {course_name}", "info")
        await _js(page, "() => { var btn = document.getElementById('btnEtc2'); if(btn) btn.click(); }")
        await _delay(2500, 4000)

        fb.append_log(run_id, f"강좌 저장 완료: {course_name}", "success")
        return True

    except Exception as e:
        fb.append_log(run_id, f"강좌 등록 오류: {e}", "error")
        return False
    finally:
        page.remove_listener("dialog", _accept)


# ── 월별 오케스트레이션 ──────────────────────────────────────────────────────

async def register_month(
    page: Page,
    instructor: dict,
    month_data: MonthData,
    split: SplitResult | None,
    run_id: str,
) -> dict[int, bool]:
    """한 강사의 한 달치 강좌를 등록한다."""
    results: dict[int, bool] = {}

    # 정기 강좌 (특강 주차 제외)
    regular_weeks = [
        w.week for w in month_data.weeks
        if not (split and split.course_type == CourseType.SPLIT_3_1 and w.week == split.special_week)
    ]
    if regular_weeks:
        ok = await register_course(page, instructor, month_data, split, run_id, is_special=False)
        for wn in regular_weeks:
            results[wn] = ok

    # 원데이 특강
    if split and split.course_type == CourseType.SPLIT_3_1:
        ok = await register_course(page, instructor, month_data, split, run_id, is_special=True)
        results[split.special_week] = ok

    return results
