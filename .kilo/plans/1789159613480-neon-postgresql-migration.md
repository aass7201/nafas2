# خطة رفع ملفات البوت على Telegram بشكل دائم

## المشكلة
- الملفات (كتب، ملازم، امتحانات) مخزنة بـ `file_id` على Telegram (دائمة ✅)
- قاعدة البيانات SQLite على Railway تضيع عند إعادة التشغيل ❌
- بعد كل restart، البوت يفقد سجل الملفات ولا يستطيع إرسالها

## الحل
- استبدال SQLite بـ PostgreSQL مجاني (Neon.tech)
- الملفات تبقى على Telegram (لا تحتاج سوبابيس Storage)
- قاعدة البيانات (file_ids + مستخدمين + تبليغات + إعدادات) تبقى دائمة على Neon

## ما تم إنجازه ✅
- [x] تعديل `bot.py` - استبدال SQLite بـ PostgreSQL (psycopg2)
- [x] تعديل `requirements.txt` - إضافة psycopg2-binary
- [x] تحديث Dockerfile, docker-compose, DEPLOY_GUIDE, install_oracle.sh, nafas2.service
- [x] إنشاء .gitignore و .env.example

## الخطوات المطلوبة (المستخدم يقوم بها)

### الخطوة 1: إنشاء حساب Neon.tech
- ادخل على [neon.tech](https://neon.tech)
- سجل دخول (GitHub أو Email)
- أنشئ مشروع جديد (اسمه: nafas2)
- ⚠️ لا تحتاج بطاقة ائتمان

### الخطوة 2: إنشاء قاعدة البيانات
- من لوحة Neon → **Console** → **SQL Editor**
- شغّل هذا السكربت:

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    file_id TEXT NOT NULL,
    file_unique_id TEXT,
    file_name TEXT,
    file_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    media_type TEXT DEFAULT 'document',
    uploaded_by BIGINT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS announcements (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS psychological_assessments (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    score INTEGER,
    category TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO announcements (text) VALUES ('📌 أهلاً بكم زملائنا طلبة المرحلة الثانية (قسم علم النفس) 🧠✨

سوف يتم نشر أي تبليغات رسمية بخصوص المحاضرات، القاعات، أو الجداول الامتحانية هنا بتحديث مستمر.

نتمنى لكم دوام التوفيق والنجاح والتفوق يا رب! 🤍');
```

### الخطوة 3: الحصول على DATABASE_URL
- من Neon Console → **Connection String** → **View Credentials**
- انسخ الرابط (مثال):
```
postgresql://neon_user:password@ep-xxx.us-east-1.aws.neon.tech:5432/neon_db?sslmode=require
```

### الخطوة 4: تحديث Railway Variables
- ادخل على [railway.app](https://railway.app) → مشروع nafas2
- **Variables** tab:
  - أضف: `DATABASE_URL` = (الرابط من الخطوة 3)
  - تأكد: `BOT_TOKEN` = **الـ Token الجديد من @BotFather**
  - تأكد: `ADMIN_ID` = `8993961580`
  - تأكد: `GEMINI_API_KEY` = (مفتاحك)

### الخطوة 5: Deploy
- اضغط **Deploy** على Railway
- انتظر حتى يظهر `Application started`
- اختبر البوت بالضغط /start

## التحقق من النجاح
- [ ] البوت يستجيب لـ /start
- [ ] الأدمن يستطيع رفع ملفات جديدة
- [ ] بعد Railway restart، الملفات لا تضيع
- [ ] الطلاب يستطيعون تحميل الملفات

## المخاطر
- Neon free tier: 0.5GB فقط (كافية للبوت)
- Neon free tier: connection pool محدود (كافي للبوت)
- إذا تجاوزت الحد، يمكن الترقية أو الانتقال لخدمة أخرى
