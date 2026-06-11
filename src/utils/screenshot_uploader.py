"""Cloudinary 스크린샷 업로드 유틸."""
from __future__ import annotations
import os
import base64


def _secret(key: str) -> str:
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, "")
    except Exception:
        return ""


def upload_screenshot(png_bytes: bytes, run_id: str, label: str = "") -> str:
    """
    PNG bytes를 Cloudinary에 업로드하고 URL을 반환한다.
    실패 시 빈 문자열 반환.
    """
    try:
        import cloudinary
        import cloudinary.uploader

        cloudinary.config(
            cloud_name=_secret("CLOUDINARY_CLOUD_NAME"),
            api_key=_secret("CLOUDINARY_API_KEY"),
            api_secret=_secret("CLOUDINARY_API_SECRET"),
        )
        if not cloudinary.config().cloud_name:
            return ""

        public_id = f"classcok/{run_id}/{label or 'shot'}"
        data_uri = f"data:image/png;base64,{base64.b64encode(png_bytes).decode()}"
        result = cloudinary.uploader.upload(
            data_uri,
            public_id=public_id,
            overwrite=True,
            resource_type="image",
        )
        return result.get("secure_url", "")
    except Exception:
        return ""
