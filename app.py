# -*- coding: utf-8 -*-
"""
موقع تحميل المقاطع — نقطة الدخول الرئيسية
==========================================
محليًا: python app.py  ثم افتح http://127.0.0.1:5000
على الاستضافة: يشغّلها Dockerfile/Procfile عبر gunicorn تلقائيًا
"""

import os
import time
import threading
import uuid
import traceback
from pathlib import Path

from flask import (
    Flask, request, jsonify, render_template, send_from_directory,
    session, redirect, url_for, Response
)
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

import config
import auth
import stats
import downloader

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# job_id -> {status, pct, speed, error, filename}
JOBS = {}
JOBS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# تسجيل الدخول
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if auth.is_logged_in():
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if auth.check_password(password):
            session["authed"] = True
            return redirect(request.args.get("next") or url_for("index"))
        error = "كلمة المرور غير صحيحة، أو تجاوزت عدد المحاولات المسموح — انتظر شوي وحاول مرة ثانية"
    return render_template("login.html", error=error, needs_password=bool(config.APP_PASSWORD))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------------------------------------------------------------------------
# الصفحة الرئيسية
# ---------------------------------------------------------------------------

@app.route("/")
@auth.login_required
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# جلب معلومات المقطع
# ---------------------------------------------------------------------------

@app.route("/api/info", methods=["POST"])
@auth.login_required
def api_info():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "الرابط فارغ"}), 400
    try:
        return jsonify(downloader.fetch_info(url))
    except Exception as e:
        return jsonify({"error": _friendly_error(str(e))}), 400


# ---------------------------------------------------------------------------
# التحميل
# ---------------------------------------------------------------------------

@app.route("/api/download", methods=["POST"])
@auth.login_required
def api_download():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "الرابط فارغ"}), 400

    file_type = data.get("file_type", "video")
    with_audio = bool(data.get("with_audio", True))
    quality = int(data.get("quality", 1080))
    use_range = bool(data.get("use_range", False))
    start_sec = data.get("start_sec")
    end_sec = data.get("end_sec")

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "pct": 0, "speed": "", "error": None, "filename": None}

    t = threading.Thread(
        target=_run_download,
        args=(job_id, url, file_type, with_audio, quality, use_range, start_sec, end_sec),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id})


def _run_download(job_id, url, file_type, with_audio, quality, use_range, start_sec, end_sec):
    def hook(d):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                job["pct"] = round((done / total * 100), 1) if total else job["pct"]
                speed = d.get("speed")
                job["speed"] = f"{speed/1024/1024:.2f} MB/s" if speed else ""
            elif d["status"] == "finished":
                job["pct"] = 99
                job["speed"] = "جاري المعالجة..."

    def on_retry(attempt, err):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                job["speed"] = f"محاولة {attempt} فشلت، جاري إعادة المحاولة..."

    try:
        filepath = downloader.download_with_retry(
            url=url, out_dir=config.APP_DIR, file_type=file_type, quality=quality,
            with_audio=with_audio, use_range=use_range, start_sec=start_sec, end_sec=end_sec,
            hook=hook, on_retry=on_retry,
        )
        filename = Path(filepath).name if filepath else None
        size = Path(filepath).stat().st_size if filepath and Path(filepath).exists() else 0
        stats.record_success(file_type, size)

        with JOBS_LOCK:
            JOBS[job_id].update({"status": "done", "pct": 100, "speed": "", "filename": filename})

    except Exception as e:
        traceback.print_exc()
        stats.record_failure()
        with JOBS_LOCK:
            JOBS[job_id].update({"status": "error", "error": _friendly_error(str(e))})


def _friendly_error(raw: str) -> str:
    low = raw.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        return "يوتيوب طلب تأكيد أنك لست بوت. ارفع ملف كوكيز من حسابك (من صفحة الإعدادات) ليتجاوز هذا الحظر."
    if "unsupported url" in low:
        return "هذا الرابط غير مدعوم أو غير صحيح."
    if "video unavailable" in low:
        return "المقطع غير متاح (محذوف أو خاص أو مقيّد بمنطقة جغرافية)."
    return raw


@app.route("/api/progress/<job_id>")
@auth.login_required
def api_progress(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "غير موجود"}), 404
    return jsonify(job)


# ---------------------------------------------------------------------------
# الملفات والسجل
# ---------------------------------------------------------------------------

@app.route("/api/files")
@auth.login_required
def api_files():
    files = []
    for f in sorted(config.APP_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.suffix.lower() in config.MEDIA_EXTENSIONS:
            st = f.stat()
            files.append({
                "name": f.name,
                "kind": "audio" if f.suffix.lower() in (".mp3", ".m4a") else "video",
                "url": f"/media/{f.name}",
                "size_mb": round(st.st_size / 1024 / 1024, 1),
                "modified": st.st_mtime,
            })
    return jsonify(files)


@app.route("/api/files/<path:filename>", methods=["DELETE"])
@auth.login_required
def api_delete_file(filename):
    safe = secure_filename(filename)
    target = None
    for f in config.APP_DIR.iterdir():
        if f.name == filename or secure_filename(f.name) == safe:
            target = f
            break
    if not target or not target.exists():
        return jsonify({"error": "الملف غير موجود"}), 404
    target.unlink()
    return jsonify({"ok": True})


@app.route("/media/<path:filename>")
@auth.login_required
def media(filename):
    safe_path = (config.APP_DIR / filename).resolve()
    if config.APP_DIR.resolve() not in safe_path.parents and safe_path != config.APP_DIR.resolve():
        return jsonify({"error": "غير مسموح"}), 403
    return send_from_directory(config.APP_DIR, filename)


# ---------------------------------------------------------------------------
# ملف الكوكيز (لتجاوز حظر يوتيوب لبعض الطلبات)
# ---------------------------------------------------------------------------

@app.route("/api/cookies", methods=["POST", "DELETE"])
@auth.login_required
def api_cookies():
    if request.method == "DELETE":
        if config.COOKIES_PATH.exists():
            config.COOKIES_PATH.unlink()
        return jsonify({"ok": True})

    f = request.files.get("cookies")
    if not f:
        return jsonify({"error": "لم يتم إرفاق ملف"}), 400
    f.save(config.COOKIES_PATH)
    return jsonify({"ok": True})


@app.route("/api/cookies/status")
@auth.login_required
def api_cookies_status():
    return jsonify({"has_cookies": config.COOKIES_PATH.exists()})


# ---------------------------------------------------------------------------
# لوحة الإحصائيات
# ---------------------------------------------------------------------------

@app.route("/api/stats")
@auth.login_required
def api_stats():
    return jsonify(stats.get_stats())


# ---------------------------------------------------------------------------
# تنظيف الملفات المؤقتة تلقائيًا
# ---------------------------------------------------------------------------

def _cleanup_loop():
    while True:
        try:
            cutoff = time.time() - config.FILE_MAX_AGE_HOURS * 3600
            for f in config.APP_DIR.iterdir():
                if f.suffix.lower() in config.MEDIA_EXTENSIONS and f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
        except Exception:
            traceback.print_exc()
        time.sleep(1800)  # كل نصف ساعة


threading.Thread(target=_cleanup_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# معالجة الأخطاء العامة — ترجع JSON لطلبات الـ API، وصفحة عادية لغيرها
# ---------------------------------------------------------------------------

@app.errorhandler(HTTPException)
def handle_http_error(e):
    if request.path.startswith("/api/") or request.path.startswith("/media/"):
        return jsonify({"error": e.description or str(e)}), e.code
    return e


@app.errorhandler(Exception)
def handle_any_error(e):
    traceback.print_exc()
    if request.path.startswith("/api/") or request.path.startswith("/media/"):
        return jsonify({"error": f"خطأ في السيرفر: {e}"}), 500
    return f"حدث خطأ: {e}", 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
