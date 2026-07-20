# -*- coding: utf-8 -*-
"""كل التعامل مع yt-dlp بمكان واحد: جلب المعلومات، التحميل، إعادة المحاولة، الكوكيز."""

import time
import traceback
from pathlib import Path

import yt_dlp

import config


def _base_opts():
    opts = {"quiet": True, "no_warnings": True}
    # لو المستخدم رفع ملف كوكيز (لتجاوز حظر يوتيوب لبعض الطلبات)، يُستخدم تلقائيًا
    if config.COOKIES_PATH.exists():
        opts["cookiefile"] = str(config.COOKIES_PATH)
    return opts


def fetch_info(url: str) -> dict:
    opts = _base_opts()
    opts["skip_download"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    duration = info.get("duration")
    return {
        "title": info.get("title", "بدون عنوان"),
        "duration": duration,
        "duration_txt": (f"{int(duration // 60):02d}:{int(duration % 60):02d}" if duration else None),
        "uploader": info.get("uploader", ""),
        "thumbnail": info.get("thumbnail"),
    }


def build_ydl_opts(out_dir: Path, file_type: str, quality: int, with_audio: bool,
                    use_range: bool, start_sec, end_sec, hook) -> dict:
    opts = _base_opts()
    out_tmpl = str(out_dir / "%(title).80s [%(id)s].%(ext)s")

    if file_type == "audio":
        fmt = "bestaudio/best"
        postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        merge_fmt = None
    else:
        if with_audio:
            fmt = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
        else:
            fmt = f"bestvideo[height<={quality}]"
        postprocessors = [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]
        merge_fmt = "mp4"

    opts.update({
        "format": fmt,
        "outtmpl": out_tmpl,
        "postprocessors": postprocessors,
        "progress_hooks": [hook],
    })
    if merge_fmt:
        opts["merge_output_format"] = merge_fmt

    if use_range and start_sec is not None and end_sec is not None:
        opts["download_ranges"] = lambda info, ydl: [{"start_time": float(start_sec), "end_time": float(end_sec)}]
        opts["force_keyframes_at_cuts"] = True

    return opts


def download_with_retry(url, out_dir, file_type, quality, with_audio,
                         use_range, start_sec, end_sec, hook, retries=None, on_retry=None):
    """يحاول التحميل عدة مرات عند فشل مؤقت (مشاكل شبكة، حظر مؤقت من المنصة)."""
    retries = retries if retries is not None else config.DOWNLOAD_RETRIES
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            opts = build_ydl_opts(out_dir, file_type, quality, with_audio, use_range, start_sec, end_sec, hook)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                requested = info.get("requested_downloads")
                filepath = requested[0].get("filepath") if requested else ydl.prepare_filename(info)
            return filepath
        except Exception as e:
            last_err = e
            traceback.print_exc()
            if attempt < retries:
                if on_retry:
                    on_retry(attempt, str(e))
                time.sleep(min(2 ** attempt, 10))
            else:
                raise last_err
