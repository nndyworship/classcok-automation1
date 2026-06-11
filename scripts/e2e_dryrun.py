"""
E2E Dry-Run 검증 스크립트.

실제 클래스콕 등록 없이 전체 파이프라인의 데이터 흐름을 검증한다.
배포 전 로컬 최종 점검 및 T8 Self-Check용.

실행: python scripts/e2e_dryrun.py --month 2026-07 --instructor 최보라T
"""
from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv()

# ── ANSI 색상 ────────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
BLUE  = "\033[94m"
RESET = "\033[0m"
BOLD  = "\033[1m"

def ok(msg):  print(f"  {GREEN}✅{RESET} {msg}")
def err(msg): print(f"  {RED}❌{RESET} {msg}"); sys.exit(1)
def warn(msg):print(f"  {YELLOW}⚠️ {RESET} {msg}")
def step(msg):print(f"\n{BOLD}{BLUE}── {msg}{RESET}")


def main():
    p = argparse.ArgumentParser(description="E2E Dry-Run 검증")
    p.add_argument("--month", default="2026-07", help="등록 월 (YYYY-MM)")
    p.add_argument("--instructor", default="최보라T", help="검증할 강사 시트명")
    p.add_argument("--excel", default="", help="Excel 파일 경로")
    args = p.parse_args()

    year = int(args.month.split("-")[0])
    month = int(args.month.split("-")[1])

    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD}  키즈와플 클래스콕 자동화 — E2E Dry-Run{RESET}")
    print(f"  대상: {args.instructor} / {args.month}")
    print(f"{BOLD}{'='*55}{RESET}")

    # ── STEP 1: Excel 파일 탐색 ─────────────────────────────────────────────
    step("STEP 1: Excel 파일 탐색")
    excel_path = args.excel
    if not excel_path:
        candidates = list(Path("data").glob("*.xlsx"))
        if candidates:
            excel_path = str(candidates[0])
        else:
            err("data/ 폴더에 xlsx 파일 없음. --excel 로 경로 지정 필요.")
    ok(f"Excel: {excel_path}")

    # ── STEP 2: Excel 파서 ──────────────────────────────────────────────────
    step("STEP 2: Excel 파서 — 월별 주차 추출")
    from engine.parser.excel_parser import parse, list_instructors
    sheets = list_instructors(excel_path)
    ok(f"강사 시트 {len(sheets)}개: {sheets}")

    if args.instructor not in sheets:
        err(f"'{args.instructor}' 시트 없음. 사용 가능: {sheets}")

    month_data = parse(excel_path, args.instructor, month, year)
    ok(f"{args.instructor} {month}월 → {len(month_data.weeks)}주차 추출")
    for w in month_data.weeks:
        sensory = f" 🫧{w.sensory.material}" if w.sensory.is_sensory else ""
        print(f"    {w.week}주: {w.title}{sensory}")
        if w.sensory.is_sensory:
            assert "여벌의 옷(미술가운)" in w.supplies, "촉감놀이 준비물 누락"

    # ── STEP 3: 공휴일 분기 엔진 ────────────────────────────────────────────
    step("STEP 3: 공휴일 분기 계산")
    from engine.scheduler.week_splitter import compute, CourseType
    from engine.scheduler.holiday_checker import fetch_holidays

    holidays = fetch_holidays(year, month)
    ok(f"{year}-{month:02d} 공휴일: {sorted(holidays) or '없음'}")

    # 강사 요일 (DB 없으면 "화" 기본값으로 테스트)
    day_of_week = "화"
    from src.utils import firebase_client as fb
    os.environ.setdefault("SESSION_ENCRYPT_KEY", "e" * 64)
    fb.init()
    instructors = fb.get_instructors("dongtan")
    for inst in instructors:
        if inst.get("excel_data_path") == args.instructor:
            day_of_week = inst.get("day_of_week", "화")
            break

    split = compute(year, month, day_of_week)
    if split.course_type == CourseType.SPLIT_3_1:
        ok(f"공휴일 감지 → {split.holiday_week}주차 특강 분리 ({split.course_type.value})")
    else:
        ok(f"공휴일 없음 → 4주 정규 ({split.course_type.value})")

    # ── STEP 4: Firebase / 로그 기록 ────────────────────────────────────────
    step("STEP 4: Firebase 연결 및 로그 기록")
    run_id = fb.new_run_id()
    fb.append_log(run_id, f"Dry-Run 시작: {args.instructor} {args.month}", "info")
    fb.append_log(run_id, f"주차 추출: {len(month_data.weeks)}주", "info")
    fb.append_log(run_id, f"분기: {split.course_type.value}", "info")
    logs = fb.get_logs(run_id)
    assert len(logs) == 3
    ok(f"로그 기록/조회: {len(logs)}건 (Run ID: {run_id})")

    # ── STEP 5: GitHub Dispatch stub ────────────────────────────────────────
    step("STEP 5: GitHub Dispatch 연결 확인")
    from src.utils.github_dispatch import trigger
    result = trigger("dongtan", args.month, [args.instructor], run_id=run_id)
    if result["status"] == "triggered":
        ok(f"GitHub Actions 실제 트리거 성공")
    elif result["status"] == "stub":
        warn(f"Stub 모드 (GITHUB_PAT 미설정) — 실제 배포 후 재확인 필요")
    else:
        warn(f"Dispatch 오류: {result['message']}")

    # ── STEP 6: 쿠키 암호화 검증 ────────────────────────────────────────────
    step("STEP 6: 세션 쿠키 AES-256-GCM 검증")
    from src.utils.firebase_client import encrypt_cookie, decrypt_cookie
    sample = '{"cookies":[{"name":"session","value":"DRYRUN_TOKEN"}]}'
    assert decrypt_cookie(encrypt_cookie(sample)) == sample
    ok("AES-256-GCM 암호화/복호화 왕복 정상")

    # ── STEP 7: 환경변수 점검 ───────────────────────────────────────────────
    step("STEP 7: 환경변수 설정 점검")
    env_checks = {
        "FIREBASE_PROJECT_ID": "Firebase 프로젝트 ID",
        "FIREBASE_PRIVATE_KEY": "Firebase 서비스 키",
        "FIREBASE_CLIENT_EMAIL": "Firebase 서비스 계정 이메일",
        "GITHUB_PAT": "GitHub Personal Access Token",
        "GITHUB_REPO_OWNER": "GitHub 레포 소유자",
        "ANTHROPIC_API_KEY": "Claude API 키",
        "SESSION_ENCRYPT_KEY": "세션 암호화 키",
        "CLASSCOK_ID": "클래스콕 로그인 ID",
        "CLASSCOK_PW": "클래스콕 로그인 PW",
    }
    missing = []
    for key, label in env_checks.items():
        val = os.getenv(key, "")
        if val:
            ok(f"{key} 설정됨")
        else:
            warn(f"{key} 미설정 ({label})")
            missing.append(key)

    # ── 최종 결과 ────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'='*55}{RESET}")
    if not missing:
        print(f"{BOLD}{GREEN}  🎉 E2E Dry-Run 전체 통과 — 배포 준비 완료!{RESET}")
    else:
        print(f"{BOLD}{YELLOW}  ⚠️  Dry-Run 완료 — 미설정 환경변수 {len(missing)}개{RESET}")
        print(f"  배포 전 .env 또는 플랫폼 Secrets에 등록 필요:")
        for k in missing:
            print(f"    - {k}")
    print(f"{BOLD}{'='*55}{RESET}\n")


if __name__ == "__main__":
    main()
