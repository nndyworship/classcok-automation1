"""주차별 커리큘럼 프리뷰 테이블 컴포넌트."""
import streamlit as st
from engine.parser.excel_parser import MonthData
from engine.scheduler.week_splitter import SplitResult, CourseType


def render(month_data: MonthData, split: SplitResult | None = None) -> None:
    """주차별 커리큘럼을 테이블로 렌더링한다."""
    if not month_data.weeks:
        st.warning("해당 월 데이터가 없습니다.")
        return

    rows = []
    for w in month_data.weeks:
        week_label = f"{w.week}주"

        # 공휴일(특강) 주차 표시
        if split and split.course_type == CourseType.SPLIT_3_1 and w.week == split.special_week:
            week_label += " 🎪특강"

        sensory_tag = f"🫧 {w.sensory.material}" if w.sensory.is_sensory else ""
        rows.append({
            "주차": week_label,
            "수업 주제": w.title,
            "촉감놀이": sensory_tag,
            "준비물": w.supplies,
        })

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "주차": st.column_config.TextColumn(width="small"),
            "수업 주제": st.column_config.TextColumn(width="medium"),
            "촉감놀이": st.column_config.TextColumn(width="small"),
            "준비물": st.column_config.TextColumn(width="large"),
        },
    )
