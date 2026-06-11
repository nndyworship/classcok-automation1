"""
GET /api/log?branch_id=dongtan&month=2026-07 — 최근 등록 결과 조회.

Vercel Serverless Function (< 3초 실행).
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        branch_id = params.get("branch_id", ["dongtan"])[0]
        month = params.get("month", [""])[0]

        data = _fetch_courses(branch_id, month)
        body = json.dumps(data, ensure_ascii=False, default=str).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def _fetch_courses(branch_id: str, month: str) -> dict:
    try:
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
        from src.utils import firebase_client as fb
        fb.init()
        instructors = fb.get_instructors(branch_id)
        return {"status": "ok", "branch_id": branch_id, "month": month, "instructors": instructors}
    except Exception as e:
        return {"status": "error", "message": str(e)}
