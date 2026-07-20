# -*- coding: utf-8 -*-
"""إحصائيات بسيطة (عدد التحميلات، الحجم الكلي...) — تُخزَّن بملف JSON صغير."""

import json
import threading
from pathlib import Path

import config

_STATS_FILE = config.APP_DIR / "stats.json"
_lock = threading.Lock()

_DEFAULT = {"total_downloads": 0, "video_count": 0, "audio_count": 0, "total_bytes": 0, "failed": 0}


def _load():
    if _STATS_FILE.exists():
        try:
            return json.loads(_STATS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(_DEFAULT)


def _save(data):
    try:
        _STATS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def record_success(file_type: str, size_bytes: int):
    with _lock:
        data = _load()
        data["total_downloads"] += 1
        data["total_bytes"] += max(size_bytes, 0)
        if file_type == "audio":
            data["audio_count"] += 1
        else:
            data["video_count"] += 1
        _save(data)


def record_failure():
    with _lock:
        data = _load()
        data["failed"] += 1
        _save(data)


def get_stats():
    with _lock:
        return _load()
