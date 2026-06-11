"""
강사 수업 요일과 월을 기반으로 4주 날짜를 계산하고,
공휴일 충돌 시 정규 3주 + 원데이 특강 1주로 분기한다.
"""

from __future__ import annotations
import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from engine.scheduler.holiday_checker import fetch_holidays

DAY_KO_TO_INT = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


class CourseType(Enum):
    REGULAR_4WEEK = "regular_4week"
    SPLIT_3_1 = "split_3_1"


@dataclass
class WeekSchedule:
    week: int
    lesson_date: date
    is_holiday: bool
    is_special: bool = False


@dataclass
class SplitResult:
    course_type: CourseType
    weeks: list[WeekSchedule] = field(default_factory=list)
    holiday_week: int | None = None
    special_week: int | None = None


def compute(year: int, month: int, day_of_week_ko: str) -> SplitResult:
    """
    특정 연월에서 강사 수업 요일의 4주 날짜를 계산하고 분기 결과를 반환한다.

    Args:
        year: 연도
        month: 월 (1~12)
        day_of_week_ko: 수업 요일 한글 ("월"~"일")

    Returns:
        SplitResult
    """
    dow = DAY_KO_TO_INT.get(day_of_week_ko)
    if dow is None:
        raise ValueError(f"알 수 없는 요일: {day_of_week_ko}")

    holidays = fetch_holidays(year, month)

    # 해당 월에서 수업 요일에 해당하는 날짜 4개 추출
    lesson_dates: list[date] = []
    d = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    while d <= end and len(lesson_dates) < 4:
        if d.weekday() == dow:
            lesson_dates.append(d)
        d += timedelta(days=1)

    weeks: list[WeekSchedule] = []
    holiday_week: int | None = None

    for i, ld in enumerate(lesson_dates, start=1):
        is_hol = ld in holidays
        if is_hol and holiday_week is None:
            holiday_week = i
        weeks.append(WeekSchedule(week=i, lesson_date=ld, is_holiday=is_hol))

    if holiday_week is None:
        return SplitResult(course_type=CourseType.REGULAR_4WEEK, weeks=weeks)

    # 공휴일 주차를 특강으로 전환
    for w in weeks:
        if w.week == holiday_week:
            w.is_special = True

    return SplitResult(
        course_type=CourseType.SPLIT_3_1,
        weeks=weeks,
        holiday_week=holiday_week,
        special_week=holiday_week,
    )
