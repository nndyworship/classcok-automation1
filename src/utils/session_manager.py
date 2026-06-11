"""Streamlit session_state 키 관리 헬퍼."""
import streamlit as st


def get(key: str, default=None):
    return st.session_state.get(key, default)


def set(key: str, value):
    st.session_state[key] = value


def require(key: str, default=None):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]
