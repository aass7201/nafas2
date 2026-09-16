# ============================================
# دليل النشر على Railway (5 دقائق)
# ============================================

## 1. ارفع الكود على GitHub
```bash
cd K:\psagle
git init
git add .
git commit -m "Nafas2 bot ready for deployment"
# أنشئ ريبو جديد على GitHub.com ثم:
git remote add origin https://github.com/YOUR_USERNAME/nafas2.git
git branch -M main
git push -u origin main
```

## 2. على Railway.app
1. ادخل على **railway.app** → سجل دخول بـ **GitHub**
2. **New Project** → **Deploy from GitHub repo**
3. اختر ريبو `nafas2`
4. سيكتشف `Procfile` تلقائياً ويبدأ النشر

## 3. أضف متغيرات البيئة (Variables)
في تبويب **Variables** أضف:
```
BOT_TOKEN=أضف_Token_هنا
ADMIN_ID=8993961580
GEMINI_API_KEY=أضف_مفتاح_Gemini_هنا
DATABASE_URL=postgresql://user:password@host:5432/nafas2
```

## 4. انشر!
- اضغط **Deploy**
- راقب اللوجز حتى تظهر: `Application started`

## ⚠️ ملاحظة مهمة عن Railway:
- البوت **قد ينام** بعد فترة عدم نشاط (الخطة المجانية)
- لحل هذا: أضف **UptimeRobot** أو **Cron-job.org** يرسل طلب كل 5 دقايق
- أو استخدم **Oracle Cloud** (أدناه) للعمل الحقيقي 24/7

---

# ============================================
# النشر على Oracle Cloud (الأقوى - مجاني للأبد)
# ============================================

## 1. أنشئ حساب Oracle Cloud
- ادخل: **cloud.oracle.com**
- سجل دخول → **Start for Free**
- يحتاج **بطاقة بنكية** للتحقق فقط (لا يُخصم منها)

## 2. أنشئ Instance (VM)
- **Create a VM instance**
- Name: `nafas2-bot`
- Image: **Ubuntu 22.04** (أو 24.04)
- Shape: **Ampere ARM** → **4 OCPU, 24 GB** (Always Free)
- SSH Keys: ارفع مفتاحك العام أو أنشئ جديد
- **Create**

## 3. اتصل بالسيرفر
```bash
# من PowerShell/Terminal:
ssh ubuntu@YOUR_SERVER_IP
```

## 4. شغّل سكريبت التثبيت (أمر واحد!)
```bash
# انسخ محتوى install_oracle.sh أو نزله من GitHub:
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/nafas2/main/install_oracle.sh | bash

# أو يدوياً:
# 1. انسخ ملفات البوت للسيرفر (scp أو git clone)
# 2. شغّل: bash install_oracle.sh
```

## 5. ضع مفتاح Gemini API
```bash
echo "GEMINI_API_KEY=مفتاحك_الحقيقي" >> ~/nafas2/.env
sudo systemctl restart nafas2
```

## 6. تحقق من العمل
```bash
sudo systemctl status nafas2
sudo journalctl -u nafas2 -f
```

---

## 🎯 الخلاصة: اختر واحد

| الميزة | Railway | Oracle Cloud |
|----------|---------|--------------|
| **سهولة** | ⭐⭐⭐⭐⭐ (5 دقايق) | ⭐⭐⭐ (15-20 دقيقة) |
| **استمرارية** | قد ينام | **24/7 حقيقي** |
| **مجاني** | $5/شهر رصيد | **مجاني للأبد** |
| **أداء** | محدود | **4 CPU, 24 GB RAM** |
| **صيانة** | تلقائية | أنت تدير (لكن稳定) |

**توصيتي:** **Oracle Cloud** - تعبت مرة وحدة، يشتغل للأبد مجاناً.