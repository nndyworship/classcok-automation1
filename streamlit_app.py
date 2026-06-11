"""메인 대시보드 — 좌: 클래스콕 운영시스템 / 우: 자동 등록 컨트롤 패널."""
import io
import streamlit as st
import streamlit.components.v1 as components
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
    initial_sidebar_state="collapsed",
)

# ── CSS: 사이드바 숨김 + 전체 여백 최소화 ──────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"] { display: none; }
  .block-container { padding-top: 0.5rem; padding-bottom: 0; max-width: 100%; }
  header { visibility: hidden; height: 0; }
  #classcok-frame { border: none; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

fb.init()
require("run_id", "")
require("running", False)

CLASSCOK_URL = "https://sas.classkok.com"

# ── 좌우 분할 레이아웃 ──────────────────────────────────────────────────────
col_left, col_right = st.columns([6, 4], gap="small")

# ═══════════════════════════════════════════════════════════════════════════
# ◀ 왼쪽: 클래스콕 바로가기 + 실행 로그 모니터링
# ═══════════════════════════════════════════════════════════════════════════
with col_left:
    # 클래스콕 바로가기 버튼
    st.markdown(
        f"""
        <a href="{CLASSCOK_URL}" target="_blank" style="
            display: block; width: 100%; padding: 14px;
            background: #4361ee; color: white; text-align: center;
            border-radius: 8px; text-decoration: none;
            font-size: 16px; font-weight: bold; margin-bottom: 16px;">
            🖥️ 클래스콕 운영시스템 열기 ↗
        </a>
        """,
        unsafe_allow_html=True,
    )

    cur_run = st.session_state.get("run_id", "")
    is_running = st.session_state.get("running", False)

    if is_running:
        st_autorefresh(interval=3000, key="left_log_refresh")

    if cur_run:
        st.markdown("#### 📋 실행 로그 + 실시간 화면")
        st.caption(f"Run ID: `{cur_run}`")

        # 스크린샷 피드 — screenshot_url이 있는 로그만 추출해 최신 1장 크게 표시
        logs = fb.get_logs(cur_run)
        shot_logs = [l for l in logs if l.get("screenshot_url")]
        if shot_logs:
            latest = shot_logs[-1]
            st.image(latest["screenshot_url"], caption="최신 화면 (자동 갱신)", use_container_width=True)

        # 전체 로그 텍스트
        with st.expander("전체 로그 보기", expanded=not shot_logs):
            log_stream.render(cur_run)
    else:
        st.markdown("#### 📋 실행 로그 모니터링")
        st.info("등록 실행 후 진행 로그와 클래스콕 화면이 실시간으로 여기에 표시됩니다.", icon="📋")
        st.markdown("""
**자동화 흐름 안내**
1. 오른쪽에서 Excel 업로드 → 강사 선택
2. 🚀 등록 실행 클릭
3. GitHub Actions가 클래스콕에 자동 등록
4. **이 화면에서 클래스콕 화면 실시간 확인** (3초 간격 갱신)
5. 완료 후 위 버튼으로 클래스콕에서 최종 확인
        """)

# ═══════════════════════════════════════════════════════════════════════════
# ▶ 오른쪽: 자동 등록 컨트롤 패널
# ═══════════════════════════════════════════════════════════════════════════
with col_right:
    st.markdown("#### 🧸 강좌 자동 등록 패널")

    # 설정 입력
    with st.expander("⚙️ 등록 설정", expanded=True):
        branch = st.selectbox("지점", ["동탄본점"], key="branch")
        BRANCH_ID = "dongtan"

        year_month = st.selectbox(
            "등록 월",
            [f"2026-{m:02d}" for m in range(1, 13)],
            index=6,
            key="target_month",
        )
        year = int(year_month.split("-")[0])
        month = int(year_month.split("-")[1])

        uploaded = st.file_uploader("📂 Excel 업로드", type=["xlsx"], key="excel_file")
        st.caption("강사별 수업주제 최종.xlsx")

    if not uploaded:
        st.info("Excel 파일을 업로드하면 강사 목록이 표시됩니다.", icon="📂")
        st.stop()

    # Excel 로드
    excel_bytes = io.BytesIO(uploaded.read())
    try:
        instructor_sheets = excel_parser.list_instructors(excel_bytes)
    except Exception as e:
        st.error(f"Excel 읽기 오류: {e}")
        st.stop()

    # 강사 마스터 로드
    instructors_db = fb.get_instructors(BRANCH_ID)
    instructor_map = {i.get("excel_data_path", ""): i for i in instructors_db}
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

    # 강사 선택
    st.markdown("**① 강사 선택**")
    st.caption("요일 '?'는 [⚙️ 강사 설정] 페이지에서 먼저 입력하세요.")

    selected_ids: list[str] = []
    preview_target: str | None = None

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

    # 커리큘럼 프리뷰
    st.markdown("**② 커리큘럼 프리뷰**")
    if preview_target:
        try:
            excel_bytes.seek(0)
            inst = instructor_map[preview_target]
            month_data = excel_parser.parse(excel_bytes, preview_target, month, year)
            day = inst.get("day_of_week", "?")
            split = compute_split(year, month, day) if day != "?" else None
            st.caption(
                f"**{inst.get('name', preview_target)}** — {year_month}"
                + (f" | {split.course_type.value}" if split else "")
            )
            week_table.render(month_data, split)
            if split and split.course_type == CourseType.SPLIT_3_1:
                st.warning(
                    f"⚠️ {split.holiday_week}주차 공휴일 → 3주 정규 + 1주 원데이 특강",
                    icon="📅",
                )
        except Exception as e:
            st.error(f"프리뷰 오류: {e}")
    else:
        st.info("강사를 선택하면 프리뷰가 표시됩니다.")

    st.divider()

    # 실행 영역
    st.markdown("**③ 등록 실행**")
    disabled = len(selected_ids) == 0 or st.session_state.get("running", False)
    btn_label = "⏳ 실행 중..." if st.session_state.get("running", False) else "🚀 등록 실행"

    col_b1, col_b2 = st.columns([3, 1])
    with col_b1:
        if st.button(btn_label, type="primary", disabled=disabled, use_container_width=True):
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
    with col_b2:
        if st.session_state.get("running") and st.button("■ 중단", use_container_width=True):
            st.session_state["running"] = False
            st.session_state["run_id"] = ""
            st.rerun()

    run_id = st.session_state.get("run_id", "")
    if run_id:
        st.caption(f"Run ID: `{run_id}` — 왼쪽 패널에서 로그 확인")

    # SMS 인증 팝업
    if st.session_state.get("session_expired"):
        st.error("🔑 SMS 인증 필요", icon="🔐")
        sms_code = st.text_input("SMS 인증번호", max_chars=6, key="sms_input")
        if st.button("인증 완료") and sms_code:
            fb.append_log(run_id, f"SMS 인증번호: {sms_code}")
            st.session_state["sms_code"] = sms_code
            st.session_state["session_expired"] = False
            st.rerun()
