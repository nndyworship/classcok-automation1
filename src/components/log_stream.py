"""실행 로그 실시간 스트림 컴포넌트 (Firestore 폴링)."""
import streamlit as st
from src.utils import firebase_client as fb

LEVEL_ICON = {"info": "ℹ️", "success": "✅", "error": "❌", "warn": "⚠️"}


def render(run_id: str) -> None:
    """run_id에 해당하는 실행 로그를 표시한다."""
    if not run_id:
        st.caption("실행 로그가 여기에 표시됩니다.")
        return

    logs = fb.get_logs(run_id)
    if not logs:
        st.caption("로그 없음 또는 실행 대기 중...")
        return

    for entry in logs:
        icon = LEVEL_ICON.get(entry.get("level", "info"), "ℹ️")
        ts = entry.get("timestamp", "")[:19].replace("T", " ")
        msg = entry.get("message", "")
        shot = entry.get("screenshot_url", "")

        st.markdown(f"`{ts}` {icon} {msg}")
        if shot:
            st.image(shot, width=320)
