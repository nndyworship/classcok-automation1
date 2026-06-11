"""강사별 등록 상태 카드 컴포넌트."""
import streamlit as st
from engine.scheduler.week_splitter import SplitResult, CourseType


def render(instructor: dict, split: SplitResult | None = None, selected: bool = False) -> bool:
    """
    강사 카드를 렌더링하고 선택 여부(체크박스 값)를 반환한다.

    Args:
        instructor: Firestore / class_config의 강사 dict
        split: 공휴일 분기 결과 (None이면 미계산)
        selected: 초기 선택 상태
    """
    name = instructor.get("name", "")
    day = instructor.get("day_of_week", "?")
    time_slot = instructor.get("time_slot", "?")
    age = instructor.get("recommended_age", "")

    if split and split.course_type == CourseType.SPLIT_3_1:
        badge = f"⚠️ 3주 정규 + 1주 특강 (공휴일 {split.holiday_week}주차)"
        border_color = "#ffc107"
    else:
        badge = "✅ 4주 정규"
        border_color = "#10b981"

    with st.container():
        st.markdown(
            f"""
            <div style="border-left:4px solid {border_color};
                        padding:10px 14px; margin-bottom:8px;
                        background:var(--background-color, #fff);
                        border-radius:0 6px 6px 0;">
              <strong>{name}</strong>
              &nbsp;|&nbsp; {day}요일 {time_slot}
              &nbsp;|&nbsp; <span style="color:#6c757d;font-size:0.85em">{age}</span><br/>
              <span style="font-size:0.9em">{badge}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        checked = st.checkbox("등록 대상 포함", value=selected, key=f"chk_{instructor.get('instructor_id', name)}")
    return checked
