"""
Firebase Admin SDK 초기화 및 Firestore CRUD.

환경변수 미설정 시 /data/class_config.json 로컬 파일로 fallback.
세션 쿠키는 AES-256-GCM으로 암호화하여 Firestore에 저장한다.
"""

from __future__ import annotations
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Firebase는 선택적 import — 로컬 fallback 환경에서 미설치 허용
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    _FIREBASE_AVAILABLE = True
except ImportError:
    _FIREBASE_AVAILABLE = False

# AES-256-GCM 암호화
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64, secrets as _secrets

LOCAL_CONFIG_PATH = Path("data/class_config.json")
_db = None


# ── 초기화 ──────────────────────────────────────────────────────────────────

def init() -> bool:
    """Firebase Admin SDK를 초기화한다. 성공 여부를 반환한다."""
    global _db
    if _db is not None:
        return True
    if not _FIREBASE_AVAILABLE:
        return False

    def _s(key: str) -> str:
        val = os.getenv(key, "")
        if val:
            return val
        try:
            import streamlit as st
            return st.secrets.get(key, "")
        except Exception:
            return ""

    project_id = _s("FIREBASE_PROJECT_ID")
    private_key = _s("FIREBASE_PRIVATE_KEY").replace("\\n", "\n")
    client_email = _s("FIREBASE_CLIENT_EMAIL")

    if not all([project_id, private_key, client_email]):
        return False

    if not firebase_admin._apps:
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": project_id,
            "private_key": private_key,
            "client_email": client_email,
            "token_uri": "https://oauth2.googleapis.com/token",
        })
        firebase_admin.initialize_app(cred)

    _db = firestore.client()
    return True


def _is_online() -> bool:
    return _db is not None


# ── 세션 쿠키 암호화 ────────────────────────────────────────────────────────

def _get_aes_key() -> bytes:
    raw = os.getenv("SESSION_ENCRYPT_KEY", "")
    if len(raw) == 64:
        return bytes.fromhex(raw)
    # 키가 없으면 임시 키 생성 (재시작 시 쿠키 무효화됨 — 경고)
    return _secrets.token_bytes(32)


def encrypt_cookie(cookie_json: str) -> str:
    """쿠키 JSON 문자열을 AES-256-GCM으로 암호화하여 base64 반환."""
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = _secrets.token_bytes(12)
    ct = aesgcm.encrypt(nonce, cookie_json.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_cookie(encrypted: str) -> str:
    """암호화된 base64 쿠키를 복호화하여 JSON 문자열 반환."""
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce, ct = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()


# ── 세션 쿠키 저장/조회 ─────────────────────────────────────────────────────

def save_session_cookie(cookie_json: str) -> None:
    encrypted = encrypt_cookie(cookie_json)
    now = datetime.now(timezone.utc)
    if _is_online():
        _db.collection("sessions").document("main").set({
            "cookies_encrypted": encrypted,
            "last_valid": now,
        })
    else:
        Path("data/session.enc.json").write_text(
            json.dumps({"cookies_encrypted": encrypted, "last_valid": now.isoformat()})
        )


def load_session_cookie() -> str | None:
    """복호화된 쿠키 JSON 반환. 없으면 None."""
    try:
        if _is_online():
            doc = _db.collection("sessions").document("main").get()
            if not doc.exists:
                return None
            return decrypt_cookie(doc.to_dict()["cookies_encrypted"])
        else:
            p = Path("data/session.enc.json")
            if not p.exists():
                return None
            data = json.loads(p.read_text())
            return decrypt_cookie(data["cookies_encrypted"])
    except Exception:
        return None


def mark_session_expired() -> None:
    if _is_online():
        _db.collection("sessions").document("main").update({"status": "SESSION_EXPIRED"})


# ── 강사 마스터 데이터 ──────────────────────────────────────────────────────

def get_instructors(branch_id: str = "dongtan") -> list[dict]:
    if _is_online():
        docs = _db.collection("branches").document(branch_id).collection("instructors").stream()
        return [{"instructor_id": d.id, **d.to_dict()} for d in docs]

    if LOCAL_CONFIG_PATH.exists():
        cfg = json.loads(LOCAL_CONFIG_PATH.read_text())
        return cfg.get("instructors", [])
    return []


def save_instructor(branch_id: str, instructor_id: str, data: dict) -> None:
    if _is_online():
        _db.collection("branches").document(branch_id)\
           .collection("instructors").document(instructor_id).set(data, merge=True)
    else:
        cfg = json.loads(LOCAL_CONFIG_PATH.read_text()) if LOCAL_CONFIG_PATH.exists() else {}
        instructors = cfg.get("instructors", [])
        for i, inst in enumerate(instructors):
            if inst.get("instructor_id") == instructor_id:
                instructors[i] = {"instructor_id": instructor_id, **data}
                break
        else:
            instructors.append({"instructor_id": instructor_id, **data})
        cfg["instructors"] = instructors
        LOCAL_CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))


# ── 강좌 등록 결과 저장 ─────────────────────────────────────────────────────

def save_course(branch_id: str, instructor_id: str, yyyymm: str, data: dict) -> None:
    if _is_online():
        _db.collection("branches").document(branch_id)\
           .collection("instructors").document(instructor_id)\
           .collection("courses").document(yyyymm).set(data, merge=True)


# ── 실행 로그 ───────────────────────────────────────────────────────────────

def new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def append_log(run_id: str, message: str, level: str = "info", screenshot_url: str = "") -> None:
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "level": level,
    }
    if screenshot_url:
        entry["screenshot_url"] = screenshot_url

    if _is_online():
        _db.collection("logs").document(run_id)\
           .collection("steps").add(entry)
    else:
        log_path = Path(f"data/log_{run_id}.jsonl")
        with log_path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_logs(run_id: str) -> list[dict]:
    if _is_online():
        docs = _db.collection("logs").document(run_id).collection("steps")\
                   .order_by("timestamp").stream()
        return [d.to_dict() for d in docs]

    log_path = Path(f"data/log_{run_id}.jsonl")
    if not log_path.exists():
        return []
    return [json.loads(l) for l in log_path.read_text().splitlines() if l]


def set_run_status(run_id: str, status: str, branch_id: str = "", target_month: str = "") -> None:
    if _is_online():
        _db.collection("logs").document(run_id).set({
            "status": status,
            "branch_id": branch_id,
            "target_month": target_month,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, merge=True)


# ── 등록 양식 템플릿 저장/조회 ─────────────────────────────────────────────

_TEMPLATE_LOCAL = Path("data/form_templates.json")


def save_form_template(branch_id: str, template_name: str, data: dict) -> None:
    """등록 양식을 이름으로 저장한다."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {**data, "template_name": template_name, "saved_at": now}
    if _is_online():
        _db.collection("branches").document(branch_id)\
           .collection("form_templates").document(template_name).set(payload)
    else:
        templates = _load_local_templates()
        templates[template_name] = payload
        _TEMPLATE_LOCAL.parent.mkdir(parents=True, exist_ok=True)
        _TEMPLATE_LOCAL.write_text(json.dumps(templates, ensure_ascii=False, indent=2))


def list_form_templates(branch_id: str) -> list[dict]:
    """저장된 등록 양식 목록을 최신순으로 반환한다."""
    if _is_online():
        docs = _db.collection("branches").document(branch_id)\
                   .collection("form_templates")\
                   .order_by("saved_at", direction="DESCENDING").stream()
        return [d.to_dict() for d in docs]
    templates = _load_local_templates()
    return sorted(templates.values(), key=lambda x: x.get("saved_at", ""), reverse=True)


def load_form_template(branch_id: str, template_name: str) -> dict | None:
    """이름으로 등록 양식을 불러온다."""
    if _is_online():
        doc = _db.collection("branches").document(branch_id)\
                  .collection("form_templates").document(template_name).get()
        return doc.to_dict() if doc.exists else None
    templates = _load_local_templates()
    return templates.get(template_name)


def delete_form_template(branch_id: str, template_name: str) -> None:
    """저장된 등록 양식을 삭제한다."""
    if _is_online():
        _db.collection("branches").document(branch_id)\
           .collection("form_templates").document(template_name).delete()
    else:
        templates = _load_local_templates()
        templates.pop(template_name, None)
        _TEMPLATE_LOCAL.write_text(json.dumps(templates, ensure_ascii=False, indent=2))


def _load_local_templates() -> dict:
    if _TEMPLATE_LOCAL.exists():
        try:
            return json.loads(_TEMPLATE_LOCAL.read_text())
        except Exception:
            return {}
    return {}
