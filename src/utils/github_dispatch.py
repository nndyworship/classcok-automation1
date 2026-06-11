"""
GitHub Actions workflow_dispatch API 호출 유틸.

대시보드 → Vercel /api/trigger → GitHub Actions 파이프라인.
PAT·레포 정보 미설정 시 stub 응답 반환 (로컬 개발용).
"""
from __future__ import annotations

import os
import requests

def _secret(key: str, default: str = "") -> str:
    """os.environ → st.secrets 순서로 시크릿 조회. 공백·따옴표 자동 제거."""
    val = os.getenv(key, "").strip().strip('"').strip("'")
    if val:
        return val
    try:
        import streamlit as st
        raw = st.secrets.get(key, default)
        return str(raw).strip().strip('"').strip("'") if raw else default
    except Exception:
        return default

GITHUB_API = "https://api.github.com"
TIMEOUT = 8


def trigger(
    branch_id: str,
    target_month: str,
    instructor_ids: list[str] | None = None,
    run_id: str = "",
) -> dict:
    """
    GitHub Actions workflow_dispatch를 트리거한다.

    Vercel 배포 환경에서는 /api/trigger 엔드포인트를 경유하고,
    로컬 환경에서는 GitHub API를 직접 호출한다.
    """
    pat = _secret("GH_PAT") or _secret("GITHUB_PAT")
    owner = _secret("GITHUB_REPO_OWNER")
    repo = _secret("GITHUB_REPO_NAME") or "classcok-automation1"
    vercel_url = _secret("VERCEL_API_URL")

    # Vercel 배포 환경: /api/trigger 경유
    if vercel_url:
        return _trigger_via_vercel(vercel_url, branch_id, target_month, instructor_ids or [], run_id)

    # 로컬: GitHub API 직접 호출
    if not pat:
        return {"status": "stub", "message": "GH_PAT 미설정 — Streamlit Cloud Secrets에 GH_PAT를 추가하세요.", "run_id": run_id}
    if not owner:
        return {"status": "stub", "message": "GITHUB_REPO_OWNER 미설정 — Streamlit Cloud Secrets에 GITHUB_REPO_OWNER를 추가하세요.", "run_id": run_id}

    return _trigger_github_api(pat, owner, repo, branch_id, target_month, instructor_ids or [], run_id)


def _trigger_github_api(
    pat: str, owner: str, repo: str,
    branch_id: str, target_month: str,
    instructor_ids: list[str], run_id: str,
) -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows/classcok_register.yml/dispatches"
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "ref": "main",
        "inputs": {
            "branch_id": branch_id,
            "target_month": target_month,
            "instructor_ids": ",".join(instructor_ids),
            "run_id": run_id,
        },
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
        if resp.status_code == 204:
            return {"status": "triggered", "message": "GitHub Actions 실행 요청 완료", "run_id": run_id}
        if resp.status_code == 401:
            return {"status": "error", "message": f"인증 실패(401) — GH_PAT 토큰이 만료되었거나 잘못됨. Streamlit Cloud Secrets에서 GH_PAT를 새 토큰으로 교체하세요."}
        if resp.status_code == 404:
            return {"status": "error", "message": f"레포/워크플로우 없음(404) — GITHUB_REPO_OWNER={owner}, GITHUB_REPO_NAME={repo} 확인 필요. 워크플로우 파일명: classcok_register.yml"}
        if resp.status_code == 422:
            return {"status": "error", "message": f"워크플로우 입력값 오류(422): {resp.text[:300]}"}
        return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except requests.Timeout:
        return {"status": "error", "message": "GitHub API 타임아웃"}
    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}


def _trigger_via_vercel(
    vercel_url: str,
    branch_id: str, target_month: str,
    instructor_ids: list[str], run_id: str,
) -> dict:
    url = f"{vercel_url.rstrip('/')}/api/trigger"
    payload = {
        "branch_id": branch_id,
        "target_month": target_month,
        "instructor_ids": instructor_ids,
        "run_id": run_id,
    }
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        return resp.json()
    except requests.Timeout:
        return {"status": "error", "message": "Vercel API 타임아웃"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
