#!/bin/bash
# ============================================
# سكريبت تثبيت أوتوماتيكي لبوت Nafas2 على Oracle Cloud
# شغل بأمر واحد: bash install_oracle.sh
# ============================================

set -e

echo "🚀 بدء تثبيت بوت Nafas2 على Oracle Cloud..."

# تحديث النظام
echo "📦 تحديث النظام..."
sudo apt update && sudo apt upgrade -y

# تثبيت المتطلبات
echo "🐍 تثبيت Python والمكتبات..."
sudo apt install -y python3 python3-venv python3-pip git sqlite3

# إنشاء مجلد المشروع
PROJECT_DIR="$HOME/nafas2"
echo "📁 إنشاء مجلد المشروع: $PROJECT_DIR"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# نسخ ملفات البوت (سيتم نسخها يدوياً أو عبر git)
if [ ! -f "bot.py" ]; then
    echo "⚠️ ملفات البوت غير موجودة. انسخها لهذا المجلد ثم شغّل السكريبت مرة ثانية."
    echo "   أو استنسخ من GitHub: git clone https://github.com/YOUR_USERNAME/nafas2.git ."
    exit 1
fi

# إنشاء البيئة الافتراضية
echo "🔧 إنشاء البيئة الافتراضية..."
python3 -m venv venv
source venv/bin/activate

# تثبيت المتطلبات
echo "📚 تثبيت مكتبات Python..."
pip install --upgrade pip
pip install -r requirements.txt

# إنشاء ملف .env
echo "⚙️ إنشاء ملف الإعدادات..."
cat > .env << 'ENVEOF'
BOT_TOKEN=8897033696:AAHk2wPS82MCzC29vlZ7pY9ex8neyPLa9Z4
ADMIN_ID=8993961580
GEMINI_API_KEY=ضع_مفتاح_Gemini_هنا
DB_PATH=nafas2.db
ENVEOF

# تحديث bot.py لقراءة المتغيرات من البيئة
echo "🔄 تحديث البوت لقراءة المتغيرات من .env..."
sed -i '1a import os\nfrom dotenv import load_dotenv\nload_dotenv()' bot.py
sed -i 's/BOT_TOKEN = ".*"/BOT_TOKEN = os.getenv("BOT_TOKEN")/' bot.py
sed -i 's/ADMIN_ID = .*/ADMIN_ID = int(os.getenv("ADMIN_ID"))/' bot.py
sed -i 's/GEMINI_API_KEY = ".*"/GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")/' bot.py
sed -i 's/DB_PATH = ".*"/DB_PATH = os.getenv("DB_PATH")/' bot.py

# تثبيت python-dotenv
pip install python-dotenv

# إعداد خدمة systemd
echo "⚙️ إعداد الخدمة للعمل تلقائياً..."
sudo cp nafas2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nafas2
sudo systemctl start nafas2

# إعداد فايروول (اختياري)
sudo ufw allow 22/tcp
sudo ufw --force enable

echo ""
echo "✅ تم التثبيت بنجاح!"
echo ""
echo "📋 أوامر مفيدة:"
echo "   حالة البوت:     sudo systemctl status nafas2"
echo "   سجلات البوت:    sudo journalctl -u nafas2 -f"
echo "   إعادة تشغيل:    sudo systemctl restart nafas2"
echo "   إيقاف البوت:    sudo systemctl stop nafas2"
echo ""
echo "⚠️ مهم: عدّل ملف .env وضع مفتاح Gemini API الصحيح:"
echo "   nano $PROJECT_DIR/.env"
echo "   ثم: sudo systemctl restart nafas2"
echo ""
echo "🎉 البوت سيعمل 24/7 تلقائياً حتى بعد إعادة تشغيل السيرفر!"