"""강사 마스터 데이터 CRUD — 최초 1회 입력 및 이후 수정."""
import streamlit as st
from src.utils import firebase_client as fb

st.set_page_config(page_title="강사 설정", page_icon="⚙️", layout="wide")
st.title("⚙️ 강사 마스터 데이터 설정")
st.caption("요일·시간대·연령 등 기본 정보를 최초 1회 입력합니다. 이후 매달 자동 상속됩니다.")

fb.init()

DAYS = ["월", "화", "수", "목", "금", "토", "일"]
BRANCH_ID = "dongtan"

instructors = fb.get_instructors(BRANCH_ID)

st.subheader("등록된 강사 목록")
if instructors:
    for inst in instructors:
        with st.expander(f"**{inst.get('name', '')}** — {inst.get('day_of_week', '')}요일 {inst.get('time_slot', '')}"):
            col1, col2, col3 = st.columns(3)
            name = col1.text_input("강사명", value=inst.get("name", ""), key=f"name_{inst['instructor_id']}")
            day = col2.selectbox("수업 요일", DAYS, index=DAYS.index(inst.get("day_of_week", "월")),
                                 key=f"day_{inst['instructor_id']}")
            time_slot = col3.text_input("시간대", value=inst.get("time_slot", ""), key=f"time_{inst['instructor_id']}")
            col4, col5 = st.columns(2)
            age = col4.text_input("수강 연령", value=inst.get("recommended_age", ""), key=f"age_{inst['instructor_id']}")
            sheet = col5.text_input("Excel 시트명", value=inst.get("excel_data_path", ""), key=f"sheet_{inst['instructor_id']}")
            if st.button("저장", key=f"save_{inst['instructor_id']}"):
                fb.save_instructor(BRANCH_ID, inst["instructor_id"], {
                    "name": name, "day_of_week": day, "time_slot": time_slot,
                    "recommended_age": age, "excel_data_path": sheet,
                })
                st.success(f"{name} 저장 완료")
                st.rerun()
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
    new_age = c5.text_input("수강 연령 (예: 18~36개월)")
    new_sheet = c6.text_input("Excel 시트명 (예: 최보라T)")
    submitted = st.form_submit_button("등록")
    if submitted:
        if not all([new_id, new_name, new_day, new_time, new_sheet]):
            st.error("모든 필드를 입력하세요.")
        else:
            fb.save_instructor(BRANCH_ID, new_id, {
                "name": new_name, "day_of_week": new_day, "time_slot": new_time,
                "recommended_age": new_age, "excel_data_path": new_sheet,
            })
            st.success(f"'{new_name}' 등록 완료")
            st.rerun()
