"""
GET /api/status?run_id=xxx — Firestore에서 실행 상태 조회.

Vercel Serverless Function (< 3초 실행).
대시보드가 2초마다 폴링하여 실시간 진행 상황을 표시한다.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        run_id = params.get("run_id", [""])[0]

        data = _fetch_status(run_id)
        body = json.dumps(data, ensure_ascii=False, default=str).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass  # Vercel 로그 노이즈 억제


def _fetch_status(run_id: str) -> dict:
    if not run_id:
        return {"status": "idle", "logs": []}

    # Firebase 초기화 시도
    try:
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
        from src.utils import firebase_client as fb
        fb.init()
        logs = fb.get_logs(run_id)
        return {"status": "ok", "run_id": run_id, "logs": logs, "count": len(logs)}
    except Exception as e:
        return {"status": "error", "message": str(e), "logs": []}
