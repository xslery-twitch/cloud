# -*- coding: utf-8 -*-
"""نظام تسجيل دخول بسيط بجلسة (session) بدل نافذة المتصفح الافتراضية."""

import time
from functools import wraps

from flask import session, request, redirect, url_for, jsonify

import config

# حماية بسيطة من محاولات التخمين المتكررة (بالذاكرة فقط، تكفي للاستخدام الشخصي)
_failed_attempts = {}  # ip -> [timestamps]
_MAX_ATTEMPTS = 8
_WINDOW_SECONDS = 300


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < _WINDOW_SECONDS]
    _failed_attempts[ip] = attempts
    return len(attempts) >= _MAX_ATTEMPTS


def _record_failed_attempt(ip: str):
    _failed_attempts.setdefault(ip, []).append(time.time())


def check_password(password: str) -> bool:
    if not config.APP_PASSWORD:
        return True  # لا حماية إن لم تُضبط كلمة مرور
    ip = request.remote_addr or "unknown"
    if _is_rate_limited(ip):
        return False
    ok = secrets_compare(password, config.APP_PASSWORD)
    if not ok:
        _record_failed_attempt(ip)
    return ok


def secrets_compare(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a or "", b or "")


def is_logged_in() -> bool:
    if not config.APP_PASSWORD:
        return True
    return bool(session.get("authed"))


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if is_logged_in():
            return f(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": "الرجاء تسجيل الدخول أولًا"}), 401
        return redirect(url_for("login_page", next=request.path))
    return wrapped
