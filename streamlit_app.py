"""메인 대시보드 — 지점/월 선택 → 프리뷰 → 컨펌 → 실행 → 모니터링."""
import io
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src.utils import firebase_client as fb
from src.utils import github_dispatch
from src.utils.session_manager import require
from src.components import instructor_card, week_table, log_stream
from engine.parser import excel_parser
from engine.scheduler.week_splitter import compute as compute_split, CourseType

# ── 페이지 설정 ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="키즈와플 오감팡팡 | 강좌 자동 등록",
    page_icon="🧸",
    layout="wide",
    initial_sidebar_state="expanded",
)

fb.init()

# ── 사이드바 ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://placehold.co/200x60/4361ee/white?text=KidsWaffle", width=200)
    st.header("등록 설정")

    branch = st.selectbox("지점 선택", ["동탄본점"], key="branch")
    BRANCH_ID = "dongtan"

    year_month = st.selectbox(
        "등록 월",
        [f"2026-{m:02d}" for m in range(1, 13)],
        index=6,
        key="target_month",
    )
    year = int(year_month.split("-")[0])
    month = int(year_month.split("-")[1])

    st.divider()
    uploaded = st.file_uploader("📂 Excel 파일 업로드", type=["xlsx"], key="excel_file")
    st.caption("강사별 수업주제 최종.xlsx")
    st.divider()
    st.page_link("src/pages/04_settings.py", label="⚙️ 강사 설정", icon="⚙️")
    st.caption("v0.5.0 — T5 대시보드 구현")

# ── 상태 초기화 ─────────────────────────────────────────────────────────────
require("run_id", "")
require("running", False)
require("selected_instructors", [])

# ── 메인 헤더 ────────────────────────────────────────────────────────────────
st.title("🧸 클래스콕 강좌 자동 등록 시스템")
st.caption(f"**{branch}** | 등록 대상: **{year_month}**")

if not uploaded:
    st.info("왼쪽 사이드바에서 Excel 파일을 업로드하면 프리뷰가 시작됩니다.", icon="📂")
    st.stop()

# ── Excel 로드 ──────────────────────────────────────────────────────────────
excel_bytes = io.BytesIO(uploaded.read())

try:
    instructor_sheets = excel_parser.list_instructors(excel_bytes)
except Exception as e:
    st.error(f"Excel 파일 읽기 오류: {e}")
    st.stop()

# ── 강사 마스터 데이터 로드 ─────────────────────────────────────────────────
instructors_db = fb.get_instructors(BRANCH_ID)
instructor_map = {i.get("excel_data_path", ""): i for i in instructors_db}

# DB에 없는 강사는 Excel 시트명으로 임시 생성
for sheet in instructor_sheets:
    if sheet not in instructor_map:
        instructor_map[sheet] = {
            "instructor_id": sheet,
            "name": sheet,
            "day_of_week": "?",
            "time_slot": "미설정",
            "recommended_age": "",
            "excel_data_path": sheet,
        }

# ── 강사 카드 + 프리뷰 ──────────────────────────────────────────────────────
st.subheader("① 등록 대상 강사 선택")
st.caption("요일이 '?'로 표시된 강사는 [설정] 페이지에서 수업 요일을 먼저 입력하세요.")

selected_ids: list[str] = []
preview_target: str | None = None

col_cards, col_preview = st.columns([1, 2])

with col_cards:
    for sheet, inst in instructor_map.items():
        day = inst.get("day_of_week", "?")
        split = None
        if day != "?":
            try:
                split = compute_split(year, month, day)
            except Exception:
                pass

        checked = instructor_card.render(inst, split=split, selected=True)
        if checked:
            selected_ids.append(inst["instructor_id"])
            if preview_target is None:
                preview_target = sheet

with col_preview:
    st.subheader("② 커리큘럼 프리뷰")
    if preview_target:
        try:
            excel_bytes.seek(0)
            inst = instructor_map[preview_target]
            month_data = excel_parser.parse(excel_bytes, preview_target, month, year)
            day = inst.get("day_of_week", "?")
            split = compute_split(year, month, day) if day != "?" else None

            st.caption(
                f"**{inst.get('name', preview_target)}** — {year_month} "
                + (f"| {split.course_type.value}" if split else "")
            )
            week_table.render(month_data, split)

            if split and split.course_type == CourseType.SPLIT_3_1:
                st.warning(
                    f"⚠️ {split.holiday_week}주차 공휴일 감지 → "
                    f"3주 정규 + 1주 원데이 특강으로 자동 분리 등록됩니다.",
                    icon="📅",
                )
        except Exception as e:
            st.error(f"프리뷰 오류: {e}")
    else:
        st.info("강사를 1명 이상 선택하면 프리뷰가 표시됩니다.")

st.divider()

# ── 실행 영역 ────────────────────────────────────────────────────────────────
st.subheader("③ 등록 실행")

col_btn, col_status = st.columns([1, 3])

with col_btn:
    disabled = len(selected_ids) == 0 or st.session_state.get("running", False)
    btn_label = "⏳ 실행 중..." if st.session_state.get("running", False) else "🚀 등록 실행"

    if st.button(btn_label, type="primary", disabled=disabled, use_container_width=True):  # noqa: streamlit-compat
        run_id = fb.new_run_id()
        st.session_state["run_id"] = run_id
        st.session_state["running"] = True

        fb.set_run_status(run_id, "triggered", BRANCH_ID, year_month)
        fb.append_log(run_id, f"등록 요청: {year_month} / {len(selected_ids)}명")

        result = github_dispatch.trigger(
            branch_id=BRANCH_ID,
            target_month=year_month,
            instructor_ids=selected_ids,
        )
        fb.append_log(run_id, f"GitHub Dispatch: {result['message']}")
        st.rerun()

    if st.session_state.get("running") and st.button("■ 중단", use_container_width=True):
        st.session_state["running"] = False
        st.session_state["run_id"] = ""
        st.rerun()

with col_status:
    run_id = st.session_state.get("run_id", "")
    if run_id:
        st.caption(f"Run ID: `{run_id}`")
        if st.session_state.get("running"):
            st_autorefresh(interval=2000, key="log_refresh")
        log_stream.render(run_id)
    else:
        st.caption("실행 버튼을 누르면 진행 로그가 여기에 표시됩니다.")

# ── 세션 만료 경고 ────────────────────────────────────────────────────────────
if st.session_state.get("session_expired"):
    st.error("🔑 클래스콕 세션이 만료되었습니다. SMS 인증이 필요합니다.", icon="🔐")
    sms_code = st.text_input("SMS 인증번호 입력", max_chars=6, key="sms_input")
    if st.button("인증 완료") and sms_code:
        fb.append_log(run_id, f"SMS 인증번호 입력: {sms_code}")
        st.session_state["sms_code"] = sms_code
        st.session_state["session_expired"] = False
        st.rerun()
