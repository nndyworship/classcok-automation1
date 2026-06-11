"""
로컬 실행 진입점.

사용법:
  python engine/bot/run_local.py --headed --branch dongtan --month 2026-07
  python engine/bot/run_local.py --headless --branch dongtan --month 2026-07 --instructors choi_bora,baek_haram
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv()

from src.utils import firebase_client as fb
from engine.bot.classcok_client import run as bot_run


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="클래스콕 강좌 자동 등록 로컬 실행")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--headed", action="store_true", help="브라우저 창 표시 (모니터링용)")
    mode.add_argument("--headless", action="store_true", help="백그라운드 실행 (CI/Actions용)")
    p.add_argument("--branch", default="dongtan", help="지점 코드 (기본: dongtan)")
    p.add_argument("--month", required=True, help="등록 월 (예: 2026-07)")
    p.add_argument("--instructors", default="", help="강사 ID 쉼표 구분 (비우면 전체)")
    p.add_argument("--excel", default="", help="Excel 파일 경로 (기본: data/ 폴더 자동 탐색)")
    return p.parse_args()


def _find_excel(override: str) -> str:
    if override and Path(override).exists():
        return override
    data_dir = Path("data")
    xlsx_files = list(data_dir.glob("*.xlsx"))
    if xlsx_files:
        return str(xlsx_files[0])
    raise FileNotFoundError(
        "Excel 파일을 찾을 수 없습니다. --excel 옵션으로 경로를 지정하거나 data/ 폴더에 파일을 넣으세요."
    )


async def main() -> None:
    args = _parse_args()

    fb.init()
    run_id = fb.new_run_id()

    instructor_ids = [i.strip() for i in args.instructors.split(",") if i.strip()]

    try:
        excel_path = _find_excel(args.excel)
    except FileNotFoundError as e:
        print(f"[오류] {e}")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f" 키즈와플 클래스콕 자동 등록")
    print(f" 지점: {args.branch} | 월: {args.month}")
    print(f" 모드: {'headed (브라우저 표시)' if args.headed else 'headless'}")
    print(f" Excel: {excel_path}")
    print(f" Run ID: {run_id}")
    print(f"{'='*50}\n")

    result = await bot_run(
        branch_id=args.branch,
        target_month=args.month,
        instructor_ids=instructor_ids,
        excel_path=excel_path,
        run_id=run_id,
        headless=args.headless,
        sms_queue=None,  # 로컬 stdin 입력 모드
    )

    print(f"\n{'='*50}")
    print(f" 결과: {result['status'].upper()}")
    print(f" 성공: {len(result['success'])}명 {result['success']}")
    print(f" 실패: {len(result['failed'])}명 {result['failed']}")
    print(f" 로그: data/log_{run_id}.jsonl")
    print(f"{'='*50}\n")

    sys.exit(0 if result["status"] == "done" else 1)


if __name__ == "__main__":
    asyncio.run(main())
