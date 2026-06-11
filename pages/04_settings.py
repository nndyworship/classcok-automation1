"""강사 마스터 데이터 CRUD — 최초 1회 입력 및 이후 수정."""
import streamlit as st
from src.utils import firebase_client as fb

st.set_page_config(page_title="강사 설정", page_icon="⚙️", layout="wide")
st.title("⚙️ 강사 마스터 데이터 설정")
st.caption("요일·시간대·클래스콕 등록 정보를 최초 1회 입력합니다. 이후 매달 자동 상속됩니다.")

fb.init()

DAYS = ["월", "화", "수", "목", "금", "토", "일"]
BRANCH_ID = "dongtan"

# 수강인원 설정 옵션
TKCRS_OPTIONS = {"자녀 동반 (보호자+자녀)": "Y", "성인 단독": "N", "커플/패밀리": "X"}

# 수강대상 연령별 강좌추천 — 클래스콕 공통코드 기준 (실제 값은 시스템에서 확인 필요)
ADULT_AGRP_OPTIONS = {
    "선택 안함": "",
    "0~12개월": "0TO12M",
    "13~24개월": "13TO24M",
    "25~36개월": "25TO36M",
    "37~48개월": "37TO48M",
    "49~60개월": "49TO60M",
    "61~72개월": "61TO72M",
    "4~5세": "4TO5",
    "5~7세": "5TO7",
    "6~8세": "6TO8",
    "20~29세": "20TO29",
    "전연령": "ALL",
}

# 카테고리(주) — 클래스콕 공통코드 기준 (실제 값은 시스템에서 확인 필요)
CATEGORY_MAIN_OPTIONS = {
    "선택 안함": "",
    "공예/DIY": "1",
    "쿠킹/베이킹": "2",
    "뷰티/패션": "3",
    "음악": "4",
    "그림/미술": "5",
    "글쓰기": "6",
    "스포츠/운동": "7",
    "댄스": "8",
    "사진/영상": "9",
    "언어": "10",
    "IT/코딩": "11",
    "자기계발": "12",
}

# 수강대상(주) — 클래스콕 공통코드 기준
CATEGORY_GROUP_MAIN_OPTIONS = {
    "선택 안함": "",
    "성인": "1",
    "청소년": "2",
    "영유아": "3",
    "아동": "4",
}


def _render_instructor(inst: dict) -> None:
    iid = inst["instructor_id"]
    with st.expander(
        f"**{inst.get('name', '')}** — {inst.get('day_of_week', '')}요일 {inst.get('time_slot', '')}",
        expanded=False,
    ):
        st.markdown("##### 기본 정보")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("강사명", value=inst.get("name", ""), key=f"name_{iid}")
        day = c2.selectbox("수업 요일", DAYS,
                           index=DAYS.index(inst.get("day_of_week", "월")),
                           key=f"day_{iid}")
        time_slot = c3.text_input("시간대 (예: 10:30~11:20)",
                                  value=inst.get("time_slot", ""), key=f"time_{iid}")

        c4, c5 = st.columns(2)
        age = c4.text_input("수강 연령 (표시용, 예: 25~36개월)",
                            value=inst.get("recommended_age", ""), key=f"age_{iid}")
        sheet = c5.text_input("Excel 시트명 (예: 최보라T)",
                              value=inst.get("excel_data_path", ""), key=f"sheet_{iid}")

        st.markdown("##### 클래스콕 등록 정보")
        st.caption("아래 값은 클래스콕 강좌 등록 폼에 그대로 입력됩니다.")

        d1, d2, d3 = st.columns(3)
        course_name_prefix = d1.text_input(
            "강좌명 접두어 (예: 오감팡팡 최보라T)",
            value=inst.get("course_name_prefix", f"오감팡팡 {inst.get('name','')}"),
            key=f"prefix_{iid}",
        )
        tkcrs_label = d2.selectbox(
            "수강인원 설정",
            list(TKCRS_OPTIONS.keys()),
            index=list(TKCRS_OPTIONS.values()).index(inst.get("tkcrs_type", "Y")),
            key=f"tkcrs_{iid}",
        )
        capacity = d3.number_input("정원 (명)", min_value=1, max_value=25,
                                   value=int(inst.get("capacity", 10)),
                                   key=f"cap_{iid}")

        e1, e2, e3 = st.columns(3)
        cat_group_label = e1.selectbox(
            "수강대상(주)",
            list(CATEGORY_GROUP_MAIN_OPTIONS.keys()),
            index=list(CATEGORY_GROUP_MAIN_OPTIONS.values()).index(
                inst.get("category_group_main", "")
            ) if inst.get("category_group_main", "") in CATEGORY_GROUP_MAIN_OPTIONS.values() else 0,
            key=f"catg_{iid}",
        )
        cat_main_label = e2.selectbox(
            "카테고리(주)",
            list(CATEGORY_MAIN_OPTIONS.keys()),
            index=list(CATEGORY_MAIN_OPTIONS.values()).index(
                inst.get("category_main", "")
            ) if inst.get("category_main", "") in CATEGORY_MAIN_OPTIONS.values() else 0,
            key=f"cat_{iid}",
        )
        adult_agrp_label = e3.selectbox(
            "수강대상 연령별 추천",
            list(ADULT_AGRP_OPTIONS.keys()),
            index=list(ADULT_AGRP_OPTIONS.values()).index(
                inst.get("adult_agrp", "")
            ) if inst.get("adult_agrp", "") in ADULT_AGRP_OPTIONS.values() else 0,
            key=f"agrp_{iid}",
        )

        f1, f2, f3 = st.columns(3)
        price = f1.number_input("학습비 (원)", min_value=0, step=1000,
                                value=int(inst.get("price", 0)), key=f"price_{iid}")
        room_code = f2.text_input(
            "강의실 코드 (클래스콕 LCTRM_CD)",
            value=inst.get("room_code", ""),
            key=f"room_{iid}",
            help="클래스콕 관리자 강의실 드롭다운의 내부 value 값. 개발자도구 확인 필요.",
        )
        keywords = f3.text_input("추가 검색 키워드",
                                 value=inst.get("search_keywords", ""),
                                 key=f"kw_{iid}")

        if st.button("💾 저장", key=f"save_{iid}", type="primary"):
            fb.save_instructor(BRANCH_ID, iid, {
                "name": name,
                "day_of_week": day,
                "time_slot": time_slot,
                "recommended_age": age,
                "excel_data_path": sheet,
                # 클래스콕 등록 정보
                "course_name_prefix": course_name_prefix,
                "tkcrs_type": TKCRS_OPTIONS[tkcrs_label],
                "capacity": capacity,
                "category_group_main": CATEGORY_GROUP_MAIN_OPTIONS[cat_group_label],
                "category_main": CATEGORY_MAIN_OPTIONS[cat_main_label],
                "adult_agrp": ADULT_AGRP_OPTIONS[adult_agrp_label],
                "price": price,
                "room_code": room_code,
                "search_keywords": keywords,
            })
            st.success(f"✅ {name} 저장 완료")
            st.rerun()


instructors = fb.get_instructors(BRANCH_ID)

st.subheader("등록된 강사 목록")
if instructors:
    for inst in instructors:
        _render_instructor(inst)
else:
    st.info("등록된 강사가 없습니다. 아래에서 신규 등록하세요.")

st.divider()
st.subheader("신규 강사 등록")
with st.form("new_instructor"):
    c1, c2, c3 = st.columns(3)
    new_id = c1.text_input("강사 ID (영문, 예: choi_bora)")
    new_name = c2.text_input("강사명")
    new_day = c3.selectbox("수업 요일", DAYS)

    c4, c5, c6 = st.columns(3)
    new_time = c4.text_input("시간대 (예: 10:30~11:20)")
    new_age = c5.text_input("수강 연령 (예: 25~36개월)")
    new_sheet = c6.text_input("Excel 시트명 (예: 최보라T)")

    st.caption("나머지 클래스콕 등록 정보는 저장 후 수정 화면에서 입력하세요.")
    submitted = st.form_submit_button("등록", type="primary")
    if submitted:
        if not all([new_id, new_name, new_day, new_time, new_sheet]):
            st.error("강사 ID, 강사명, 요일, 시간대, Excel 시트명은 필수입니다.")
        else:
            fb.save_instructor(BRANCH_ID, new_id, {
                "name": new_name,
                "day_of_week": new_day,
                "time_slot": new_time,
                "recommended_age": new_age,
                "excel_data_path": new_sheet,
                "course_name_prefix": f"오감팡팡 {new_name}",
                "tkcrs_type": "Y",
                "capacity": 10,
                "category_group_main": "",
                "category_main": "",
                "adult_agrp": "",
                "price": 0,
                "room_code": "",
                "search_keywords": "",
            })
            st.success(f"✅ '{new_name}' 등록 완료. 위 목록에서 클래스콕 등록 정보를 추가로 입력하세요.")
            st.rerun()

st.divider()
st.caption("""
**강의실 코드(LCTRM_CD) 확인 방법:**
클래스콕 강좌 등록 페이지에서 브라우저 개발자도구(F12) → 콘솔 탭에서 아래 입력:
`frmLectCrclm.getItem('LCTRM_CD').getOptions()`
결과의 `value` 값을 복사해 위 강의실 코드에 입력하세요.
""")
