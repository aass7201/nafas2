# Dockerfile for Nafas2 Bot
# يعمل على أي منصة تدعم Docker (Railway, Fly.io, Render, VPS, etc.)

FROM python:3.11-slim

# تثبيت المتطلبات النظامية
RUN apt-get update && rm -rf /var/lib/apt/lists/*

# تعيين مجلد العمل
WORKDIR /app

# نسخ ملفات المتطلبات أولاً (للاستفادة من كاش Docker)
COPY requirements.txt .

# تثبيت مكتبات Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# إنشاء مستخدم غير root للأمان
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# متغيرات البيئة (تُمرر وقت التشغيل)
ENV BOT_TOKEN=""
ENV ADMIN_ID=""
ENV GEMINI_API_KEY=""
ENV DATABASE_URL=""

# الأمر الافتراضي
CMD ["python", "bot.py"]