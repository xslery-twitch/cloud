# -*- coding: utf-8 -*-
"""إعدادات عامة للمشروع — كل القيم القابلة للتعديل بمكان واحد."""

import os
import secrets
from pathlib import Path

# مجلد التخزين (مؤقت على أغلب الاستضافات)
APP_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/tmp/downloads"))
APP_DIR.mkdir(parents=True, exist_ok=True)

# ملف الكوكيز الاختياري (Netscape format) لتجاوز حظر يوتيوب لبعض الطلبات
COOKIES_PATH = APP_DIR / "cookies.txt"

# كلمة مرور الدخول للموقع (لازم تُضبط عند النشر على استضافة عامة)
APP_PASSWORD = os.environ.get("APP_PASSWORD", "7be08122f53fe4f3d0065fea458f9025")

# مفتاح تشفير الجلسة — يتغيّر تلقائيًا كل إعادة تشغيل ما لم تُضبط قيمة ثابتة
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

# أقصى عمر للملف المؤقت بالساعات قبل ما ينظّفه الخادم تلقائيًا
FILE_MAX_AGE_HOURS = float(os.environ.get("FILE_MAX_AGE_HOURS", 6))

# عدد محاولات إعادة التحميل عند فشل مؤقت (مشاكل شبكة، حظر مؤقت من المنصة...)
DOWNLOAD_RETRIES = int(os.environ.get("DOWNLOAD_RETRIES", 3))

MEDIA_EXTENSIONS = (".mp4", ".mp3", ".webm", ".mkv", ".m4a")
