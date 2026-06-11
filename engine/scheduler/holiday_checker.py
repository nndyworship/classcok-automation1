"""
data.go.kr 한국천문연구원 특일정보 API를 호출하여
특정 연월의 공휴일 날짜 집합을 반환한다.
"""

from __future__ import annotations
import os
import xml.etree.ElementTree as ET
from datetime import date
from functools import lru_cache

import requests

API_URL = "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
TIMEOUT = 10


@lru_cache(maxsize=24)
def fetch_holidays(year: int, month: int) -> frozenset[date]:
    """
    해당 연월의 공휴일 날짜 집합을 반환한다.
    API 키 미설정 시 내장 2026년 공휴일 테이블로 fallback.
    """
    api_key = os.getenv("HOLIDAY_API_KEY", "")
    if api_key:
        try:
            return _fetch_from_api(api_key, year, month)
        except Exception:
            pass
    return _fallback_holidays(year, month)


def _fetch_from_api(api_key: str, year: int, month: int) -> frozenset[date]:
    params = {
        "serviceKey": api_key,
        "solYear": year,
        "solMonth": f"{month:02d}",
        "numOfRows": 20,
    }
    resp = requests.get(API_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    holidays: set[date] = set()
    for item in root.iter("item"):
        locdate = item.findtext("locdate", "")
        if len(locdate) == 8:
            holidays.add(date(int(locdate[:4]), int(locdate[4:6]), int(locdate[6:])))
    return frozenset(holidays)


# 2026년 법정 공휴일 내장 테이블 (API 키 없을 때 fallback)
_BUILTIN_2026: frozenset[date] = frozenset([
    date(2026, 1, 1),   # 신정
    date(2026, 1, 28),  # 설날 연휴
    date(2026, 1, 29),  # 설날
    date(2026, 1, 30),  # 설날 연휴
    date(2026, 3, 1),   # 삼일절
    date(2026, 5, 5),   # 어린이날
    date(2026, 5, 25),  # 부처님오신날
    date(2026, 6, 6),   # 현충일
    date(2026, 8, 15),  # 광복절
    date(2026, 9, 24),  # 추석 연휴
    date(2026, 9, 25),  # 추석
    date(2026, 9, 26),  # 추석 연휴
    date(2026, 10, 3),  # 개천절
    date(2026, 10, 9),  # 한글날
    date(2026, 12, 25), # 크리스마스
])


def _fallback_holidays(year: int, month: int) -> frozenset[date]:
    if year == 2026:
        return frozenset(d for d in _BUILTIN_2026 if d.month == month)
    return frozenset()


def is_holiday(d: date) -> bool:
    return d in fetch_holidays(d.year, d.month)
