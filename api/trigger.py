"""
POST /api/trigger — GitHub Actions workflow_dispatch 프록시.

Vercel Serverless Function (< 10초 실행).
실제 Playwright는 Actions Runner에서 실행하므로 이 함수는
Dispatch API 호출(~2초)만 수행한다.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler

import requests

GITHUB_API = "https://api.github.com"
DISPATCH_TIMEOUT = 8


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._respond(400, {"error": "Invalid JSON body"})
            return

        branch_id = body.get("branch_id", "dongtan")
        target_month = body.get("target_month", "")
        instructor_ids = body.get("instructor_ids", [])
        run_id = body.get("run_id", "")

        if not target_month:
            self._respond(400, {"error": "target_month 필수"})
            return

        result = _dispatch(branch_id, target_month, instructor_ids, run_id)
        status_code = 200 if result["status"] in ("triggered", "stub") else 502
        self._respond(status_code, result)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _respond(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def _dispatch(
    branch_id: str,
    target_month: str,
    instructor_ids: list,
    run_id: str,
) -> dict:
    pat = os.getenv("GITHUB_PAT", "")
    owner = os.getenv("GITHUB_REPO_OWNER", "")
    repo = os.getenv("GITHUB_REPO_NAME", "classcok-automation")

    if not all([pat, owner]):
        return {"status": "stub", "message": "GITHUB_PAT/GITHUB_REPO_OWNER 미설정 — stub 모드"}

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
            "instructor_ids": ",".join(instructor_ids) if isinstance(instructor_ids, list) else instructor_ids,
            "run_id": run_id,
        },
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=DISPATCH_TIMEOUT)
        if resp.status_code == 204:
            return {"status": "triggered", "message": "GitHub Actions 실행 요청 완료", "run_id": run_id}
        return {
            "status": "error",
            "message": f"GitHub API 오류 HTTP {resp.status_code}",
            "detail": resp.text[:300],
        }
    except requests.Timeout:
        return {"status": "error", "message": "GitHub API 타임아웃"}
    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}
