"""실행 로그 모니터링 페이지 — Firestore 폴링."""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from src.utils import firebase_client as fb
from src.components.log_stream import render as render_logs

st.set_page_config(page_title="실행 로그", page_icon="📋", layout="wide")
st.title("📋 실행 로그 모니터링")

fb.init()

run_id = st.text_input("Run ID 입력", value=st.session_state.get("run_id", ""), placeholder="run_20260711_103022_a1b2c3")

if run_id:
    auto = st.toggle("자동 새로고침 (2초)", value=True)
    if auto:
        st_autorefresh(interval=2000, key="log_page_refresh")

    st.divider()
    render_logs(run_id)
else:
    st.info("메인 대시보드에서 실행하거나 Run ID를 직접 입력하세요.")
