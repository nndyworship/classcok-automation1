"""
강좌 자동 등록 패널 — 클래스콕 등록 화면과 동일한 구조.
이전 양식을 DB에서 불러오거나 새로 작성 후 저장·실행할 수 있다.
"""
from __future__ import annotations

import io
from datetime import date, timedelta

import streamlit as st

from src.utils import firebase_client as fb
from src.utils import github_dispatch
from engine.parser import excel_parser
from engine.scheduler.week_splitter import compute as compute_split, CourseType

st.set_page_config(
    page_title="강좌 등록 | 키즈와플",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown("""
<style>
  [data-testid="stSidebar"] { display: none; }
  .block-container { padding-top: 0.8rem; max-width: 100%; }
  header { visibility: hidden; height: 0; }
  .section-header {
    background: #f0f4ff; border-left: 4px solid #4361ee;
    padding: 6px 12px; border-radius: 0 6px 6px 0;
    font-weight: bold; margin: 16px 0 10px 0;
  }
  .required { color: #e63946; }
</style>
""", unsafe_allow_html=True)

fb.init()
BRANCH_ID = "dongtan"
DAYS = ["월", "화", "수", "목", "금", "토", "일"]

# ── 옵션 상수 ─────────────────────────────────────────────────────────────────
TKCRS_OPTIONS = {"자녀 동반 (보호자+자녀)": "Y", "성인 단독": "N", "커플/패밀리": "X"}
CATEGORY_GROUP = {
    "선택": "", "영유아": "3", "아동": "4", "청소년": "2", "성인": "1",
}
CATEGORY_MAIN = {
    "선택": "", "공예/DIY": "1", "쿠킹/베이킹": "2", "뷰티/패션": "3",
    "음악": "4", "그림/미술": "5", "글쓰기": "6",
    "스포츠/운동": "7", "댄스": "8", "자기계발": "12",
}
ADULT_AGRP = {
    "선택": "", "0~12개월": "0TO12M", "13~24개월": "13TO24M",
    "25~36개월": "25TO36M", "37~48개월": "37TO48M",
    "49~60개월": "49TO60M", "61~72개월": "61TO72M",
    "4~5세": "4TO5", "5~7세": "5TO7", "6~8세": "6TO8",
    "전연령": "ALL",
}


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def _idx(mapping: dict, val: str) -> int:
    vals = list(mapping.values())
    return vals.index(val) if val in vals else 0


def _key(mapping: dict, val: str) -> str:
    for k, v in mapping.items():
        if v == val:
            return k
    return list(mapping.keys())[0]


# ── 세션 초기화 ───────────────────────────────────────────────────────────────
_DEFAULTS: dict = {
    "branch": "동탄본점",
    "year_month": f"{date.today().year}-{date.today().month + 1:02d}",
    "course_name": "",
    "fdtr_yn": "Y",          # 정기
    "cat_group_main": "",
    "cat_main": "",
    "tkcrs_type": "Y",
    "capacity": 10,
    "room_code": "",
    "start_date": date.today() + timedelta(days=14),
    "end_date": date.today() + timedelta(days=42),
    "begin_hour": "10", "begin_min": "30",
    "end_hour": "11", "end_min": "20",
    "day_of_week": "월",
    "acpt_start": date.today(),
    "acpt_deadline": "Y",     # 개강당일
    "auto_close": "N",
    "intro": "",
    "supplies": "",
    "price": 0,
    "adult_agrp": "",
    "search_keywords": "",
    "instructor_id": "",
    "weeks_content": {},      # {1: "내용", 2: "내용", ...}
    "template_name": "",
    # 실행 상태
    "reg_run_id": "",
    "reg_running": False,
    "selected_instructors": [],
}

for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def _ss(key: str):
    return st.session_state.get(key, _DEFAULTS.get(key))


def _apply_template(tpl: dict) -> None:
    """불러온 템플릿을 세션에 반영한다."""
    mapping = {
        "course_name": "course_name", "fdtr_yn": "fdtr_yn",
        "cat_group_main": "cat_group_main", "cat_main": "cat_main",
        "tkcrs_type": "tkcrs_type", "capacity": "capacity",
        "room_code": "room_code",
        "begin_hour": "begin_hour", "begin_min": "begin_min",
        "end_hour": "end_hour", "end_min": "end_min",
        "day_of_week": "day_of_week", "acpt_deadline": "acpt_deadline",
        "auto_close": "auto_close", "intro": "intro", "supplies": "supplies",
        "price": "price", "adult_agrp": "adult_agrp",
        "search_keywords": "search_keywords", "instructor_id": "instructor_id",
        "weeks_content": "weeks_content",
    }
    for tpl_key, ss_key in mapping.items():
        if tpl_key in tpl:
            st.session_state[ss_key] = tpl[tpl_key]
    # 날짜 처리
    for dk in ("start_date", "end_date", "acpt_start"):
        if dk in tpl and tpl[dk]:
            try:
                st.session_state[dk] = date.fromisoformat(tpl[dk])
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 헤더
# ─────────────────────────────────────────────────────────────────────────────
col_title, col_back = st.columns([5, 1])
col_title.markdown("## 📝 강좌 자동 등록")
col_back.markdown("<br>", unsafe_allow_html=True)
col_back.page_link("streamlit_app.py", label="← 대시보드")

# ─────────────────────────────────────────────────────────────────────────────
# 상단 바: 불러오기 + Excel + 월 선택
# ─────────────────────────────────────────────────────────────────────────────
with st.container():
    ta, tb, tc, td = st.columns([2, 2, 2, 1])

    year_month = ta.selectbox(
        "등록 월",
        [f"{y}-{m:02d}" for y in [2026, 2027] for m in range(1, 13)],
        index=[f"{y}-{m:02d}" for y in [2026, 2027] for m in range(1, 13)].index(
            _ss("year_month")
        ) if _ss("year_month") in [f"{y}-{m:02d}" for y in [2026, 2027] for m in range(1, 13)] else 6,
        key="ym_select",
    )
    st.session_state["year_month"] = year_month
    year, month = int(year_month.split("-")[0]), int(year_month.split("-")[1])

    uploaded = tb.file_uploader("Excel 업로드", type=["xlsx"], label_visibility="collapsed",
                                key="excel_file_reg")

    # 저장된 양식 불러오기
    templates = fb.list_form_templates(BRANCH_ID)
    tpl_names = ["— 새로 작성 —"] + [t.get("template_name", "") for t in templates]
    selected_tpl = tc.selectbox("저장된 양식 불러오기", tpl_names, key="tpl_select")

    if td.button("불러오기", use_container_width=True, disabled=(selected_tpl == "— 새로 작성 —")):
        tpl = fb.load_form_template(BRANCH_ID, selected_tpl)
        if tpl:
            _apply_template(tpl)
            st.success(f"'{selected_tpl}' 불러오기 완료")
            st.rerun()

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# 메인: 좌(등록 폼) / 우(커리큘럼 프리뷰 + 실행)
# ─────────────────────────────────────────────────────────────────────────────
col_form, col_exec = st.columns([6, 4], gap="medium")

# ══════════════════════════════════════════════════════════════════════════════
# 왼쪽: 등록 폼 (클래스콕 화면 동일 구조)
# ══════════════════════════════════════════════════════════════════════════════
with col_form:

    # ── 기본정보 ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">📋 기본정보</div>', unsafe_allow_html=True)

    r1a, r1b = st.columns(2)
    r1a.text_input("점포", value="동탄본점", disabled=True, key="store_disp")
    r1b.text_input("플랫폼사", value="키즈와플", disabled=True, key="pfmco_disp")

    course_name = st.text_input(
        "강좌명 *",
        value=_ss("course_name"),
        placeholder="예: 오감팡팡 최보라T 7월",
        key="f_course_name",
    )
    st.session_state["course_name"] = course_name

    r2a, r2b, r2c, r2d = st.columns(4)
    cat_group_label = r2a.selectbox("수강대상(주) *", list(CATEGORY_GROUP.keys()),
                                    index=_idx(CATEGORY_GROUP, _ss("cat_group_main")),
                                    key="f_catg")
    st.session_state["cat_group_main"] = CATEGORY_GROUP[cat_group_label]

    cat_main_label = r2b.selectbox("카테고리(주) *", list(CATEGORY_MAIN.keys()),
                                   index=_idx(CATEGORY_MAIN, _ss("cat_main")),
                                   key="f_cat")
    st.session_state["cat_main"] = CATEGORY_MAIN[cat_main_label]

    fdtr_label = r2c.radio("구분 *", ["정기", "1회"], horizontal=True,
                           index=0 if _ss("fdtr_yn") == "Y" else 1, key="f_fdtr")
    st.session_state["fdtr_yn"] = "Y" if fdtr_label == "정기" else "N"

    tkcrs_label = r2d.radio(
        "수강인원 설정 *",
        ["자녀 동반", "성인 단독", "커플/패밀리"],
        horizontal=False,
        index=["Y", "N", "X"].index(_ss("tkcrs_type")),
        key="f_tkcrs",
    )
    st.session_state["tkcrs_type"] = {"자녀 동반": "Y", "성인 단독": "N", "커플/패밀리": "X"}[tkcrs_label]

    # ── 수강 일정 ─────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">📅 수강 일정</div>', unsafe_allow_html=True)

    s1a, s1b, s1c = st.columns([2, 1, 1])
    room_code = s1a.text_input(
        "강의실 코드 (LCTRM_CD) *",
        value=_ss("room_code"),
        placeholder="개발자도구로 확인한 value 값",
        help="F12 콘솔: frmLectCrclm.getItem('LCTRM_CD').getOptions()",
        key="f_room",
    )
    st.session_state["room_code"] = room_code

    capacity = s1b.number_input("정원 * (명)", min_value=1, max_value=25,
                                value=_ss("capacity"), key="f_cap")
    st.session_state["capacity"] = capacity

    day_of_week = s1c.selectbox("요일 *", DAYS,
                                index=DAYS.index(_ss("day_of_week")) if _ss("day_of_week") in DAYS else 0,
                                key="f_day")
    st.session_state["day_of_week"] = day_of_week

    s2a, s2b = st.columns(2)
    start_date = s2a.date_input("강좌기간 시작 *", value=_ss("start_date"), key="f_start")
    st.session_state["start_date"] = start_date
    end_date = s2b.date_input("강좌기간 종료 *", value=_ss("end_date"), key="f_end")
    st.session_state["end_date"] = end_date

    s3a, s3b, s3c, s3d = st.columns(4)
    HOURS = [f"{h:02d}" for h in range(6, 23)]
    MINS = ["00", "10", "20", "30", "40", "50"]
    begin_hour = s3a.selectbox("시작 시 *", HOURS,
                               index=HOURS.index(_ss("begin_hour")) if _ss("begin_hour") in HOURS else 4,
                               key="f_bh")
    begin_min = s3b.selectbox("시작 분 *", MINS,
                              index=MINS.index(_ss("begin_min")) if _ss("begin_min") in MINS else 3,
                              key="f_bm")
    end_hour = s3c.selectbox("종료 시 *", HOURS,
                             index=HOURS.index(_ss("end_hour")) if _ss("end_hour") in HOURS else 5,
                             key="f_eh")
    end_min = s3d.selectbox("종료 분 *", MINS,
                            index=MINS.index(_ss("end_min")) if _ss("end_min") in MINS else 2,
                            key="f_em")
    st.session_state.update({
        "begin_hour": begin_hour, "begin_min": begin_min,
        "end_hour": end_hour, "end_min": end_min,
    })

    s4a, s4b = st.columns(2)
    acpt_start = s4a.date_input(
        "접수시작일 *",
        value=_ss("acpt_start"),
        key="f_acpt",
    )
    st.session_state["acpt_start"] = acpt_start

    acpt_deadline_label = s4b.radio("접수마감일 *", ["개강 당일", "직접 입력"], horizontal=True,
                                    index=0 if _ss("acpt_deadline") == "Y" else 1,
                                    key="f_acpt_dl")
    st.session_state["acpt_deadline"] = "Y" if acpt_deadline_label == "개강 당일" else "N"

    # ── 강의계획서 (Excel에서 자동 로드) ──────────────────────────────────────
    st.markdown('<div class="section-header">📖 강의계획서 (주차별 내용)</div>', unsafe_allow_html=True)

    weeks_content: dict[int, str] = _ss("weeks_content") or {}

    if uploaded:
        excel_bytes = io.BytesIO(uploaded.read())
        try:
            instructors_db = fb.get_instructors(BRANCH_ID)
            instructor_names = {i.get("excel_data_path", ""): i for i in instructors_db}
            all_sheets = excel_parser.list_instructors(excel_bytes)

            sel_sheet = st.selectbox("강사 시트 선택", all_sheets, key="f_sheet")
            if sel_sheet:
                excel_bytes.seek(0)
                month_data = excel_parser.parse(excel_bytes, sel_sheet, month, year)
                inst_info = instructor_names.get(sel_sheet, {})
                day_info = inst_info.get("day_of_week", day_of_week)
                split = compute_split(year, month, day_info) if day_info != "?" else None

                if split and split.course_type == CourseType.SPLIT_3_1:
                    st.warning(f"⚠️ {split.special_week}주차 공휴일 → 3주 정기 + 1주 원데이 특강", icon="📅")

                for w in month_data.weeks:
                    is_sp = split and split.course_type == CourseType.SPLIT_3_1 and w.week == split.special_week
                    label = f"{'[원데이] ' if is_sp else ''}{w.week}주차"
                    default_content = weeks_content.get(w.week, w.content)
                    edited = st.text_area(
                        label,
                        value=default_content,
                        height=80,
                        key=f"week_content_{w.week}",
                    )
                    weeks_content[w.week] = edited

                    if w.supplies:
                        st.caption(f"준비물 힌트: {w.supplies}")

                st.session_state["weeks_content"] = weeks_content

                # 준비물/소개 자동 채우기 버튼
                if st.button("📥 소개·준비물 자동 채우기 (Excel)", key="auto_fill"):
                    intro_lines = []
                    supply_set: list[str] = []
                    for w in month_data.weeks:
                        intro_lines.append(f"[{w.week}주] {w.content}")
                        if w.supplies and w.supplies not in supply_set:
                            supply_set.append(w.supplies)
                    st.session_state["intro"] = "\n".join(intro_lines)
                    st.session_state["supplies"] = ", ".join(supply_set)
                    st.rerun()
        except Exception as e:
            st.error(f"Excel 로드 오류: {e}")
    else:
        st.info("Excel을 업로드하면 주차별 내용이 자동으로 채워집니다.")
        # 수동 입력 (4주)
        for wn in range(1, 5):
            edited = st.text_area(
                f"{wn}주차",
                value=weeks_content.get(wn, ""),
                height=70,
                key=f"week_content_{wn}",
            )
            weeks_content[wn] = edited
        st.session_state["weeks_content"] = weeks_content

    # ── 상세정보 ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">📄 상세정보</div>', unsafe_allow_html=True)

    intro = st.text_area("클래스소개 *", value=_ss("intro"), height=120, key="f_intro")
    st.session_state["intro"] = intro

    supplies = st.text_area("준비물", value=_ss("supplies"), height=70, key="f_supplies")
    st.session_state["supplies"] = supplies

    d1a, d1b, d1c = st.columns(3)
    price = d1a.number_input("학습비 * (원)", min_value=0, step=1000,
                             value=_ss("price"), key="f_price")
    st.session_state["price"] = price

    adult_agrp_label = d1b.selectbox("수강연령 추천 *", list(ADULT_AGRP.keys()),
                                     index=_idx(ADULT_AGRP, _ss("adult_agrp")),
                                     key="f_agrp")
    st.session_state["adult_agrp"] = ADULT_AGRP[adult_agrp_label]

    keywords = d1c.text_input("추가 검색 키워드", value=_ss("search_keywords"), key="f_kw")
    st.session_state["search_keywords"] = keywords

    # ── 강사 선택 ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">👩‍🏫 강사</div>', unsafe_allow_html=True)
    instructors_db = fb.get_instructors(BRANCH_ID)
    inst_options = {f"{i.get('name','')} ({i.get('day_of_week','')}요일)": i.get("instructor_id", "")
                    for i in instructors_db}
    inst_options_rev = {v: k for k, v in inst_options.items()}

    current_inst_label = inst_options_rev.get(_ss("instructor_id"), list(inst_options.keys())[0] if inst_options else "")
    if inst_options:
        sel_inst_label = st.selectbox("강사 선택", list(inst_options.keys()),
                                     index=list(inst_options.keys()).index(current_inst_label)
                                     if current_inst_label in inst_options else 0,
                                     key="f_inst")
        st.session_state["instructor_id"] = inst_options[sel_inst_label]
    else:
        st.warning("등록된 강사가 없습니다. [⚙️ 강사 설정] 페이지에서 먼저 등록하세요.")


# ══════════════════════════════════════════════════════════════════════════════
# 오른쪽: 요약 + 저장 + 실행
# ══════════════════════════════════════════════════════════════════════════════
with col_exec:

    # ── 양식 저장 ────────────────────────────────────────────────────────────
    st.markdown("#### 💾 양식 저장")
    with st.container(border=True):
        tpl_name_input = st.text_input(
            "저장 이름",
            value=_ss("template_name") or f"{_ss('course_name') or '양식'}_{year_month}",
            placeholder="예: 최보라T_2026-07",
            key="tpl_name_input",
        )
        save_col, del_col = st.columns(2)

        if save_col.button("💾 저장", use_container_width=True, type="primary"):
            if not tpl_name_input.strip():
                st.error("저장 이름을 입력하세요.")
            else:
                payload = {
                    "course_name": _ss("course_name"),
                    "fdtr_yn": _ss("fdtr_yn"),
                    "cat_group_main": _ss("cat_group_main"),
                    "cat_main": _ss("cat_main"),
                    "tkcrs_type": _ss("tkcrs_type"),
                    "capacity": _ss("capacity"),
                    "room_code": _ss("room_code"),
                    "start_date": _ss("start_date").isoformat() if isinstance(_ss("start_date"), date) else "",
                    "end_date": _ss("end_date").isoformat() if isinstance(_ss("end_date"), date) else "",
                    "begin_hour": _ss("begin_hour"),
                    "begin_min": _ss("begin_min"),
                    "end_hour": _ss("end_hour"),
                    "end_min": _ss("end_min"),
                    "day_of_week": _ss("day_of_week"),
                    "acpt_start": _ss("acpt_start").isoformat() if isinstance(_ss("acpt_start"), date) else "",
                    "acpt_deadline": _ss("acpt_deadline"),
                    "auto_close": _ss("auto_close"),
                    "intro": _ss("intro"),
                    "supplies": _ss("supplies"),
                    "price": _ss("price"),
                    "adult_agrp": _ss("adult_agrp"),
                    "search_keywords": _ss("search_keywords"),
                    "instructor_id": _ss("instructor_id"),
                    "weeks_content": {str(k): v for k, v in (_ss("weeks_content") or {}).items()},
                }
                fb.save_form_template(BRANCH_ID, tpl_name_input.strip(), payload)
                st.session_state["template_name"] = tpl_name_input.strip()
                st.success(f"✅ '{tpl_name_input}' 저장 완료")
                st.rerun()

        if del_col.button("🗑 삭제", use_container_width=True,
                          disabled=selected_tpl == "— 새로 작성 —"):
            fb.delete_form_template(BRANCH_ID, selected_tpl)
            st.success(f"'{selected_tpl}' 삭제 완료")
            st.rerun()

        # 저장된 양식 목록
        if templates:
            st.caption(f"저장된 양식 {len(templates)}개")
            for t in templates[:5]:
                saved_at = t.get("saved_at", "")[:10]
                st.caption(f"• {t.get('template_name','')} ({saved_at})")
            if len(templates) > 5:
                st.caption(f"  … 외 {len(templates)-5}개")

    st.divider()

    # ── 등록 정보 요약 ────────────────────────────────────────────────────────
    st.markdown("#### 📋 등록 정보 요약")
    with st.container(border=True):
        time_str = f"{_ss('begin_hour')}:{_ss('begin_min')} ~ {_ss('end_hour')}:{_ss('end_min')}"
        start = _ss("start_date")
        end = _ss("end_date")
        st.markdown(f"""
| 항목 | 값 |
|---|---|
| 강좌명 | {_ss('course_name') or '—'} |
| 구분 | {'정기' if _ss('fdtr_yn')=='Y' else '1회(원데이)'} |
| 요일/시간 | {_ss('day_of_week')}요일 {time_str} |
| 기간 | {start} ~ {end} |
| 정원 | {_ss('capacity')}명 |
| 학습비 | {int(_ss('price') or 0):,}원 |
| 접수 시작 | {_ss('acpt_start')} |
        """)

        weeks_c = _ss("weeks_content") or {}
        if weeks_c:
            st.markdown("**주차별 내용 미리보기**")
            for wn, content in sorted(weeks_c.items()):
                if content:
                    st.markdown(f"- **{wn}주**: {content[:40]}{'…' if len(content)>40 else ''}")

    st.divider()

    # ── 실행 ─────────────────────────────────────────────────────────────────
    st.markdown("#### 🚀 자동 등록 실행")

    # 필수 항목 검증
    missing = []
    if not _ss("course_name"):
        missing.append("강좌명")
    if not _ss("room_code"):
        missing.append("강의실 코드")
    if not _ss("instructor_id"):
        missing.append("강사")
    if not _ss("price"):
        missing.append("학습비")

    if missing:
        st.warning(f"미입력 필수 항목: {', '.join(missing)}", icon="⚠️")

    is_running = _ss("reg_running")
    btn_label = "⏳ 실행 중..." if is_running else "🚀 등록 실행"
    disabled = bool(missing) or is_running

    if st.button(btn_label, type="primary", disabled=disabled, use_container_width=True):
        # 봇에 전달할 instructor 데이터를 세션의 폼 데이터로 구성
        inst_data = {
            "instructor_id": _ss("instructor_id"),
            "name": next((i.get("name","") for i in instructors_db
                          if i.get("instructor_id") == _ss("instructor_id")), ""),
            "course_name_prefix": _ss("course_name"),
            "day_of_week": _ss("day_of_week"),
            "time_slot": f"{_ss('begin_hour')}:{_ss('begin_min')}~{_ss('end_hour')}:{_ss('end_min')}",
            "tkcrs_type": _ss("tkcrs_type"),
            "capacity": _ss("capacity"),
            "room_code": _ss("room_code"),
            "category_group_main": _ss("cat_group_main"),
            "category_main": _ss("cat_main"),
            "adult_agrp": _ss("adult_agrp"),
            "price": _ss("price"),
            "search_keywords": _ss("search_keywords"),
        }
        # 실행용 임시 instructor를 Firebase에 저장
        fb.save_instructor(BRANCH_ID, f"_temp_{_ss('instructor_id')}", inst_data)

        run_id = fb.new_run_id()
        st.session_state["reg_run_id"] = run_id
        st.session_state["reg_running"] = True
        fb.set_run_status(run_id, "triggered", BRANCH_ID, year_month)
        fb.append_log(run_id, f"등록 요청: {_ss('course_name')} / {year_month}")

        result = github_dispatch.trigger(
            branch_id=BRANCH_ID,
            target_month=year_month,
            instructor_ids=[_ss("instructor_id")],
            run_id=run_id,
        )
        fb.append_log(run_id, f"GitHub Dispatch: {result['message']}")
        st.rerun()

    if is_running and st.button("■ 중단", use_container_width=True):
        st.session_state["reg_running"] = False
        st.session_state["reg_run_id"] = ""
        st.rerun()

    # 실행 로그
    run_id = _ss("reg_run_id")
    if run_id:
        st.caption(f"Run ID: `{run_id}`")
        with st.expander("실행 로그", expanded=True):
            logs = fb.get_logs(run_id)
            for log in logs[-15:]:
                lvl = log.get("level", "info")
                icon = {"success": "✅", "error": "❌", "warn": "⚠️"}.get(lvl, "▶")
                st.caption(f"{icon} {log.get('message','')}")
            if any(l.get("screenshot_url") for l in logs):
                latest_shot = next((l["screenshot_url"] for l in reversed(logs) if l.get("screenshot_url")), None)
                if latest_shot:
                    st.image(latest_shot, caption="최신 화면", use_container_width=True)
