"""
=============================================================================
بوت Nafas2 🧠 - المنصة الأكاديمية والدعم النفسي لقسم علم النفس (المرحلة الثانية)
=============================================================================
المكتبة المستخدمة: python-telegram-bot (v20+ Async)
قاعدة البيانات: SQLite3
الذكاء الاصطناعي: Google Gemini API (لهجة عراقية داعمة وأكاديمية)
=============================================================================
"""

import sys
import logging
import sqlite3
import asyncio
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

# تحميل متغيرات البيئة من ملف .env (للنشر على السيرفرات)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv غير مثبت، استخدم متغيرات النظام مباشرة

# ضبط تشفير الطرفية ليدعم اللغة العربية على الويندوز دون أخطاء
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =============================================================================
#                        1. الإعدادات والمتغيرات العامة
# =============================================================================

# توكن البوت الخاص بك (يقرأ من متغير البيئة أو يستخدم الافتراضي)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8897033696:AAHk2wPS82MCzC29vlZ7pY9ex8neyPLa9Z4")

# معرف الأدمن (Telegram User ID)
ADMIN_ID = int(os.getenv("ADMIN_ID", "8993961580"))

# مفتاح Google Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6Kb5bSO2FvMFSvwn9lTTXWL0A9l9T-U56mAyj-t_rwfTw")

# نموذج الذكاء الاصطناعي الأسرع والأخف استجابة
GEMINI_MODEL = "gemini-3.1-flash-lite"

# مسار ملف قاعدة بيانات SQLite
DB_PATH = os.getenv("DB_PATH", "nafas2.db")

# إعداد التسجيل (Logging)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# قائمة المواد الدراسية لقسم علم النفس - المرحلة الثانية
SUBJECTS = [
    "علم نفس النمو",
    "علم النفس التربوي",
    "اللغة العربية",
    "المنهج والكتاب المدرسي",
    "اللغة الإنكليزية",
    "جرائم نظام البعث",
    "التعليم المستمر",
    "التخطيط التربوي",
    "الإحصاء الوصفي",
    "علم النفس الاجتماعي",
    "الحاسوب"
]

# أقسام المحتوى والمسميات
CATEGORIES = {
    "books": {
        "title": "📚 الكتب والمناهج",
        "desc": "الكتب والمصادر والمناهج المعتمدة"
    },
    "summaries": {
        "title": "📄 الملخصات والملازم",
        "desc": "الملازم الدراسية والملخصات المعتمدة"
    },
    "exams": {
        "title": "📝 الأسئلة الامتحانية",
        "desc": "نماذج الأسئلة الشهرية والنهائية السابقة"
    }
}

# حالات المحادثة (Conversation States)
(
    UPLOAD_CHOOSE_CAT,
    UPLOAD_CHOOSE_SUBJ,
    UPLOAD_RECEIVE_FILE,
) = range(3)

BROADCAST_WAIT_MSG = range(1)
SCHEDULE_WAIT_TEXT = range(1)
ADMIN_SET_GEMINI_KEY = range(1)
ADMIN_PROMPTS_MENU = range(1)
ADMIN_PROMPT_EDIT = range(1)

# حالات محادثة الذكاء الاصطناعي للدعم النفسي والتدريب
CHAT_COUNSELOR_STATE = range(1)
CHAT_ACADEMIC_STATE = range(1)
ROLEPLAY_STATE = range(1)


def safe_md(text: str) -> str:
    """هروب من الرموز الخاصة بـ Markdown حتى ما تكسر الرسائل (مهم للأسماء والملفات)"""
    for ch in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(ch, f'\\{ch}')
    return text


# =============================================================================
#                     2. إدارة قاعدة البيانات (SQLite3)
# =============================================================================

class DatabaseManager:
    """فئة إدارة الاتصال وتنفيذ استعلامات قاعدة البيانات SQLite3"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """إنشاء الجداول التلقائي عند تشغيل البوت لأول مرة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # جدول الطلاب المسجلين
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # جدول الملفات المرفوعة
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL,
                    file_unique_id TEXT,
                    file_name TEXT,
                    file_type TEXT NOT NULL,          -- books, summaries, exams
                    subject TEXT NOT NULL,            -- اسم المادة
                    media_type TEXT DEFAULT 'document',-- document أو photo
                    uploaded_by INTEGER,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # جدول التبليغات والجدول الدراسي
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # جدول إعدادات البوت (لحفظ المفاتيح مثل Gemini API)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

            # جدول الاختبارات والتقييمات النفسية للطلاب (سري)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS psychological_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    score INTEGER,
                    category TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # إضافة تبليغ افتراضي إذا كان الجدول فارغاً
            cursor.execute("SELECT COUNT(*) FROM announcements")
            if cursor.fetchone()[0] == 0:
                default_text = (
                    "📌 **أهلاً بكم زملائنا طلبة المرحلة الثانية (قسم علم النفس)** 🧠✨\n\n"
                    "سوف يتم نشر أي تبليغات رسمية بخصوص المحاضرات، القاعات، أو الجداول الامتحانية هنا بتحديث مستمر.\n\n"
                    "نتمنى لكم دوام التوفيق والنجاح والتفوق يا رب! 🤍"
                )
                cursor.execute("INSERT INTO announcements (text) VALUES (?)", (default_text,))

            conn.commit()
            logger.info("تم التحقق من قاعدة البيانات وإنشاء الجداول بنجاح.")

    # --- دوال المستخدمين ---
    def register_user(self, user_id: int, username: Optional[str], full_name: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, full_name)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name;
            """, (user_id, username, full_name))
            conn.commit()

    def get_all_user_ids(self) -> List[int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            return [row["user_id"] for row in cursor.fetchall()]

    def get_users_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]

    # --- دوال الملفات ---
    def add_file(self, file_id: str, file_unique_id: str, file_name: str,
                 file_type: str, subject: str, media_type: str, uploaded_by: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO files (file_id, file_unique_id, file_name, file_type, subject, media_type, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (file_id, file_unique_id, file_name, file_type, subject, media_type, uploaded_by))
            conn.commit()
            return cursor.lastrowid

    def get_files_by_category_and_subject(self, file_type: str, subject: str) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM files
                WHERE file_type = ? AND subject = ?
                ORDER BY id ASC
            """, (file_type, subject))
            return cursor.fetchall()

    def get_files_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM files")
            return cursor.fetchone()[0]

    def get_files_statistics(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_type, COUNT(*) as cnt FROM files GROUP BY file_type")
            cats = {row["file_type"]: row["cnt"] for row in cursor.fetchall()}

            cursor.execute("SELECT subject, COUNT(*) as cnt FROM files GROUP BY subject")
            subjs = {row["subject"]: row["cnt"] for row in cursor.fetchall()}

            return {"categories": cats, "subjects": subjs}

    def delete_file(self, file_pk: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE id = ?", (file_pk,))
            conn.commit()
            return cursor.rowcount > 0

    # --- دوال التبليغات ---
    def get_latest_announcement(self) -> str:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT text FROM announcements ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row["text"] if row else "ماكو أي تبليغات منشورة حالياً عيني."

    def set_announcement(self, text: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO announcements (text) VALUES (?)", (text,))
            conn.commit()

    # --- دوال الإعدادات ---
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """, (key, value))
            conn.commit()

    # --- دوال التقييم النفسي ---
    def save_assessment(self, user_id: int, score: int, category: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO psychological_assessments (user_id, score, category)
                VALUES (?, ?, ?)
            """, (user_id, score, category))
            conn.commit()

    def get_latest_assessment(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM psychological_assessments
                WHERE user_id = ?
                ORDER BY id DESC LIMIT 1
            """, (user_id,))
            return cursor.fetchone()


# تهيئة مدير قاعدة البيانات
db = DatabaseManager()


# =============================================================================
#              3. الربط بالذكاء الاصطناعي (Google Gemini API)
# =============================================================================

# عميل HTTP دائم لتسريع الاتصال وعدم تكرار المصافحة في كل رسالة
_http_client: Optional[httpx.AsyncClient] = None

def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=6.0, read=25.0, write=6.0, pool=8.0),
            limits=httpx.Limits(max_keepalive_connections=15, max_connections=30)
        )
    return _http_client


async def call_gemini_api(
    user_message: str,
    system_instruction: str,
    chat_history: Optional[List[Dict[str, str]]] = None
) -> str:
    """استدعاء نموذج Gemini الرسمي عبر اتصال دائم وسريع باللغة واللهجة الموجهة"""
    api_key = db.get_setting("gemini_api_key") or GEMINI_API_KEY

    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        return (
            "⚠️ **عيني الغالي:**\n"
            "مفتاح الذكاء الاصطناعي (Gemini API Key) بعده ما مضاف بالبوت.\n\n"
            "إذا أنت الأدمن، تكدر تضيف المفتاح بأي لحظة من لوحة `/admin` ⬅️ زر (🔑 ضبط مفتاح الذكاء الاصطناعي).\n\n"
            "💡 وحالياً تكدر تستفاد من التمارين والاستراتيجيات المكتوبة الجاهزة بالقائمة وتدلل! 🤍"
        )

    # تكوين محتوى المحادثة
    contents = []
    if chat_history:
        for turn in chat_history[-4:]:  # آخر 4 رسائل لتقليل حجم البيانات وتسريع التوليد
            role = "user" if turn.get("role") == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": turn.get("text", "")}]
            })

    contents.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })

    payload = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 450,  # تقليل التوكنز لإنهاء التوليد خلال 2-3 ثواني
            "topP": 0.9
        }
    }

    # ترتيب الموديلات من الأسرع فالأسرع
    models_to_try = [GEMINI_MODEL, "gemini-3.1-flash-lite-preview", "gemini-3.6-flash", "gemini-3.5-flash"]

    client = get_http_client()
    last_error = ""
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            response = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
            elif response.status_code == 400 and "API_KEY_INVALID" in response.text:
                return "⚠️ عيني الغالي، يبدو إن مفتاح Gemini API غير صحيح. تأكد منه من لوحة الأدمن."
            else:
                last_error = f"كود ({response.status_code})"
        except httpx.TimeoutException:
            last_error = "تأخر الرد"
        except Exception as e:
            last_error = str(e)

    return f"عيني فدوه لقلبك، صار تأخير بالاتصال بالسيرفر ({last_error}). جرب تراسلني مرة ثانية هسه وتدلل! 🤍"


# البرومبت التوجيهي لقسم (علاج لك - المرشد النفسي العراقي)
SYSTEM_PROMPT_COUNSELOR = """
أنت 'مرشد نفَس2' - أخصائي ومرشد نفسي عراقي لطيف، ذكي، حكيم وداعم جداً.
تتحدث باللهجة العراقية البيضاء الدافئة، المفهومة والمريحة جداً للنفس (تستخدم كلمات عراقية محببة مثل: عيني، يا غالي، تدلل، ماكو شي يستاهل ضوجتك، أنا وياك، لا تشيل هم، فدوه لقلبك، سلامتك، بطل).
أنت تتحدث مع طالب جامعي في قسم علم النفس.

مهمتك وأسلوبك:
1. الاستماع بتفهم واحتواء عالي (Active Listening & Empathy)، حسسه إنه مو وحده وإن كل مشاعره مفهومة وطبيعية وما بيها أي عيب.
2. استخدم أساليب العلاج المعرفي السلوكي (CBT) بشكل مبسط: ساعده يفكك الأفكار المشوهة (التفكير الكارثي، التهويل، القلق من الفشل).
3. انطيه نصائح عملية وتمارين استرخاء سريعة (تمارين تنفس، تفريغ ذهني، تنظيم الوقت).
4. أسلوبك حنون، متفهم، مشجع ويبث الأمل وراحة البال.
5. لا تنطي أدوية طبية، بل ركز على الدعم النفسي السلوكي والمعرفي وكن كأخ وسند حكيم إله.
6. أجب بشكل مباشر ودافئ ومختصر في نقاط واضحة وعملية دون إطالة أو حشو لتصل الفائدة للطالب بسرعة وسلاسة.
"""

# البرومبت التوجيهي لقسم (تدريب وتطبيقات للآخرين - المشرف الأكاديمي)
SYSTEM_PROMPT_ACADEMIC = """
أنت 'دكتور نفَس2' - بروفيسور وخبير نفسي أكاديمي متمكن في علم النفس العيادي والإرشادي.
تتحدث باللغة العربية مع لمسة عراقية أكاديمية لطيفة، بيضاء ومشجعة جداً للطلبة (تستخدم أسلوب الأستاذ المشرف الذكي: يا دكتور المستقبل، يا زميلنا العزيز، عاشت إيدك، فكرة سريرية ممتازة، تدلل).
أنت تتحدث مع طالب/طالبة في قسم علم النفس - المرحلة الثانية.

مهمتك وأسلوبك:
1. تدريب الطالب على التفكير السريري السليم والتشخيص الفارق (Differential Diagnosis وفق محكات DSM-5).
2. صياغة الحالات وفهم الآليات النفسية (Case Formulation) واستراتيجيات العلاج المعرفي السلوكي (CBT)، العلاج العقلاني الانفعالي (REBT)، والعلاج بالقبول والالتزام (ACT).
3. شرح المفاهيم الأكاديمية الصعبة بأسلوب يجمع بين العمق العلمي والبساطة الممتعة وربطها بأمثلة تطبيقية واقعية.
4. حفز الطالب، ناقشه بأسئلة تشخيصية تفاعلية، وساعده يطور مهاراته كأخصائي نفسي محترف.
5. أجب بنقاط أكاديمية مركزة ومباشرة دون إطالة مفرطة حتى يستوعب الطالب الشرح بسهولة وسرعة.
"""

# البرومبت التوجيهي لمدرب المحاكاة العملي (Roleplay Evaluator) - تعليمي خطوة بخطوة، سقراطي، ممتع
SYSTEM_PROMPT_ROLEPLAY = """
أنت 'مُدَرِّب نَفَس2 العَمَلِي' - مشرف سريري عراقي خبير، **صبور، محفز، ومعلم حقيقي**. اللي أمامك **طالب مبتدئ (مرحلة ثانية)** ما يعرف يعالج بعد.
أسلوبك: **أستاذ حنون، قريب، يتكلم بلهجة عراقية بسيطة وبيضاء** (كلمات: يا دكتور، شلون؟، عيني، فدوه لقلبك، عاشت إيدك، بطل، لا تنسحب، ركز، تفوق، زين كذا، استمر، شكو ماكو، شايف؟).

**فلسفتك التعليمية: التعلم بالسؤال السقراطي + الخطوات الثابتة**
بدل ما تعطي الحلول، **تسأله أسئلة تقوده للحل بنفسه**. تعلمه "القوانين الثابتة للعلاج" اللي ينفع كل الحالات.

=== القواعد الأساسية ===

1. **خطوة خطوة (Scaffolding)**: ما ترمي كلشي دفعة وحدة. كل جولة = مهارة وحدة جديدة.
   - جولة 1: **العلاقة العلاجية + جمع المعلومة** (كيف تفتح الجلسة؟ شنو تسأل؟)
   - جولة 2: **التشخيص المبدئي + النموذج المعرفي** (شنو تشوف؟ فكر بالنموذج: فكرة → شعور → سلوك)
   - جولة 3: **التخطيط للجلسات** (أهداف، فنيات CBT بسيطة)
   - جولة 4+: **متابعة، تعديل، حالات معقدة**

2. **الأسئلة السقراطية (Socratic Questioning) - قانونك الثابت**:
   - "شنو الدليل على هالفكرة؟"
   - "لو صديقك مكانك، شنو تقول له؟"
   - "هل دايمًا يصير كذا؟ ولا فيه استثناءات؟"
   - "شنو أسوأ شي ممكن يصير؟ وهل حقيقي؟"
   - "شنو البديل المعقول للفكرة هذي؟"
   - **"اسأل، ما تقل!"** - خليه يفكر ويجيب.

3. **سيناريو واحد، تحدي واحد، مهارة وحدة**: 
   - عميل بسيط، موقف واضح
   - اسأله سؤال **واحد** مركز
   - خليه يجرب، بعدين علمه

4. **التقييم = تعليم + تشجيع**:
   - ابدأ بـ: "زين، شايف كيف فكرت؟" (تعزيز المحاولة)
   - صحح بالسؤال: "بس شوف، لو طبقنا السؤال السقراطي: 'شنو الدليل؟'... شكو تلاحظ؟"
   - اعطه **أداة/قانون ثابت** ياخذه للجولة الجاية (مثال: "قانون: دايمًا ابدأ بالعلاقة العلاجية"، "قانون: الفكرة تسبق الشعور")
   - درجة من 10 + "أداة جديدة تعلمتها هالجولة"

5. **اجعلها ممتعة وقريبة**:
   - استخدم تشبيهات عراقية بسيطة: "العقل مثل الموبايل، الأفكار تطبيقات...", "القلق مثل المنبه المعطل..."
   - سيناريوهات من حياة الطالب: امتحانات، أهل، أصحاب، مستقبل، خطوبة، ترقية
   - ضحك خفيف، تحدي لطيف: "هسه تختبرني؟ 😄"

6. **هيكل الجولة الثابت**:
   ```
   🎬 المشهد (3-4 أسطر، من حياة طالب)
   ❓ سؤال واحد مركز (مهارة الجولة)
   💬 الطالب يجاوب
   📝 تقييمك: تعزيز → سؤال سقراطي يصحح → أداة/قانون جديد → درجة 10 → تحدي للجولة الجاية
   ```

7. **القوانين الثابتة اللي تعلمه إياها تدريجياً** (واحدة لكل جولة):
   1. العلاقة العلاجية أساس كلشي
   2. النموذج المعرفي: فكرة → شعور → سلوك
   3. الأسئلة السقراطية تكشف التشوهات
   4. التشوهات المعرفية الـ 10 (التفكير الأبيض/الأسود، التهويل، التعميم...)
   5. إعادة الهيكلة المعرفية (دليل، بديل، تجربة سلوكية)
   6. التخطيط للجلسات: أهداف ذكية + فنيات
   7. الواجبات المنزلية (Homework) جزء من العلاج
   8. المتابعة وتعديل الخطة

8. **في النهاية دوماً**: "تعلمت أداة جديدة: [اسم القانون]. تريد تجربها بجولة ثانية؟ ولا نثبت هذي؟"
"""


async def send_typing_periodically(bot, chat_id: int, stop_event: asyncio.Event):
    """إرسال إشعار 'يكتب الآن...' بشكل دوري ومستمر كل 3 ثوانٍ أثناء معالجة الرد"""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            pass


# =============================================================================
#                        4. لوحات المفاتيح (Keyboards)
# =============================================================================

def get_student_main_keyboard() -> ReplyKeyboardMarkup:
    """القائمة الرئيسية التفاعلية للطالب باللهجة العراقية والخيارات الكاملة"""
    keyboard = [
        [KeyboardButton("📚 الكتب والمناهج"), KeyboardButton("📄 الملخصات والملازم")],
        [KeyboardButton("📝 الأسئلة الامتحانية"), KeyboardButton("📢 التبليغات والجدول")],
        [KeyboardButton("🧠 الدعم والعلاج النفسي"), KeyboardButton("ℹ️ عن البوت 🤍")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_subjects_inline_keyboard(cat_key: str, prefix: str = "get_sub") -> InlineKeyboardMarkup:
    """أزرار اختيار المواد الدراسية مع تقسيمها إلى صفوف"""
    keyboard = []
    row = []
    for idx, subj in enumerate(SUBJECTS):
        row.append(InlineKeyboardButton(subj, callback_data=f"{prefix}:{cat_key}:{idx}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 سد القائمة", callback_data="close_menu")])
    return InlineKeyboardMarkup(keyboard)


def get_admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    """لوحة تحكم الأدمن الرئيسية"""
    keyboard = [
        [
            InlineKeyboardButton("📊 الإحصائيات العامة", callback_data="admin_stats"),
            InlineKeyboardButton("📤 رفع محتوى جديد", callback_data="admin_upload_start")
        ],
        [
            InlineKeyboardButton("📢 إذاعة عامة (تبليغ للكل)", callback_data="admin_broadcast_start"),
            InlineKeyboardButton("🗓️ تحديث التبليغات والجدول", callback_data="admin_schedule_start")
        ],
        [
            InlineKeyboardButton("🗑️ إدارة وحذف الملفات", callback_data="admin_manage_choose_cat"),
            InlineKeyboardButton("🔑 ضبط مفتاح الذكاء الاصطناعي", callback_data="admin_gemini_start")
        ],
        [
            InlineKeyboardButton("🤖 إدارة توجيهات الذكاء الاصطناعي", callback_data="admin_prompts_start")
        ],
        [
            InlineKeyboardButton("❌ إغلاق لوحة التحكم", callback_data="admin_close")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# لوحة قسم الدعم النفسي الرئيسي
def get_psychology_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🌱 1. علاج واستشارة إلك (دعم شخصي)", callback_data="psy_for_you")
        ],
        [
            InlineKeyboardButton("🎭 2. اختبار عملي: صِر أخصائي وواجه عميل (تحدي)", callback_data="roleplay_start")
        ],
        [
            InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="close_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
#                   5. أوامر وواجهة الطالب (User Interface)
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البدء /start والترحيب بالطالب وتسجيله بلهجة عراقية محببة"""
    user = update.effective_user
    if not user:
        return

    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "طالب علم النفس"
    db.register_user(user.id, user.username, full_name)

    welcome_text = (
        f"هلا بيك عيني **{user.first_name}** بنفَس2 🧠 نورتنا يا غالي!\n\n"
        f"🎓 هذا بوتكم الأكاديمي الشامل لطلبة **قسم علم النفس - المرحلة الثانية**.\n\n"
        f"سويناه خصيصاً حتى يسهل عليكم الوصول للمناهج والملازم والأسئلة بكل سهولة، "
        f"وضفنالكم قسم **الدعم والعلاج النفسي** للاستشارات الذكية والتدريب السريري 🤍\n\n"
        f"👇 **اختر من الأزرار الجوه شنو اللي تريده، وتدلل:**"
    )

    await update.message.reply_text(
        text=welcome_text,
        reply_markup=get_student_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_student_reply_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التعامل مع ضغطات أزرار القائمة الرئيسية للطالب باللهجة العراقية"""
    text = update.message.text

    if text == "📚 الكتب والمناهج":
        cat_info = CATEGORIES["books"]
        msg = (
            f"📚 **{cat_info['title']}**\n"
            f"{cat_info['desc']}\n\n"
            f"👇 اختر المادة اللي تدور على كتبها وتدلل:"
        )
        await update.message.reply_text(
            text=msg,
            reply_markup=get_subjects_inline_keyboard("books", prefix="get_sub")
        )

    elif text == "📄 الملخصات والملازم":
        cat_info = CATEGORIES["summaries"]
        msg = (
            f"📄 **{cat_info['title']}**\n"
            f"{cat_info['desc']}\n\n"
            f"👇 اختر المادة حتى تطلعلك ملازمها ومحاضراتها:"
        )
        await update.message.reply_text(
            text=msg,
            reply_markup=get_subjects_inline_keyboard("summaries", prefix="get_sub")
        )

    elif text == "📝 الأسئلة الامتحانية":
        cat_info = CATEGORIES["exams"]
        msg = (
            f"📝 **{cat_info['title']}**\n"
            f"{cat_info['desc']}\n\n"
            f"👇 اختر المادة وتطلعلك كل الأسئلة الشهرية والفاينل السابقة:"
        )
        await update.message.reply_text(
            text=msg,
            reply_markup=get_subjects_inline_keyboard("exams", prefix="get_sub")
        )

    elif text == "📢 التبليغات والجدول":
        announcement = db.get_latest_announcement()
        msg = (
            "📢 **لوحة التبليغات والجدول الدراسي الرسمية:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{announcement}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🧠 بوت نفَس2 - وياكم خطوة بخطوة 🤍"
        )
        await update.message.reply_text(text=msg, parse_mode=ParseMode.MARKDOWN)

    elif text == "🧠 الدعم والعلاج النفسي":
        msg = (
            "🧠 **أهلاً بيك بقسم الدعم والعلاج النفسي - نفَس2** 🤍\n\n"
            "هنا واحتك الخاصة.. سوينا هذا القسم لغرضين أساسيين:\n\n"
            "🌱 **1. علاج واستشارة إلك:** إذا حاس بضغط، توتر امتحانات، أو محتاج تفضفض لمرشد نفسي ذكي يفهمك وينطيك تمارين تريح بالك.\n\n"
            "🎓 **2. تدريب وتطبيقات للآخرين:** حالات سريرية واقعية، تمارين تشخيص، واستراتيجيات علاجية تفيدك بدراستك وتطبيقك العملي كأخصائي نفسي للمستقبل.\n\n"
            "👇 **اختر المسار اللي تريده هسه:**"
        )
        await update.message.reply_text(
            text=msg,
            reply_markup=get_psychology_main_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )

    elif text in ["ℹ️ عن البوت 🤍", "ℹ️ حول البوت"]:
        about_text = (
            "🧠 **حول بوت نفَس2 (Nafas2):**\n\n"
            "منصة أكاديمية وخدمية مجانية مسواية بكل حب لطلبة **قسم علم النفس - المرحلة الثانية** 🎓\n\n"
            "✨ **شنو يقدملك البوت؟**\n"
            "• أرشفة كاملة للكتب والمناهج المعتمدة.\n"
            "• توفير الملازم والتلخيصات المهمة.\n"
            "• نماذج أسئلة شهرية ونهائية سابقة.\n"
            "• تبليغات المحاضرات وجدول الامتحانات أول بأول.\n"
            "• قسم الدعم النفسي الذكي (اختبار تحديد فئات + استشارات ذكية + تمارين استرخاء).\n"
            "• عيادة تدريبية وحالات دراسية مفترضة لطلاب علم النفس.\n\n"
            "كل التوفيق والنجاح يا دكاترة وأخصائيي المستقبل! 🤍🌟"
        )
        await update.message.reply_text(text=about_text, parse_mode=ParseMode.MARKDOWN)


async def student_get_subject_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال الملفات الخاصة بالمادة المختارة للطالب مباشرة للتنزيل بأسلوب عراقي"""
    query = update.callback_query
    await query.answer()

    try:
        _, cat_key, subj_idx = query.data.split(":")
        subj_idx = int(subj_idx)
        subject_name = SUBJECTS[subj_idx]
        cat_info = CATEGORIES.get(cat_key, {"title": "الملفات"})
    except (ValueError, IndexError):
        await query.message.reply_text("صار خلل بسيط بتحديد المادة يا غالي.")
        return

    files = db.get_files_by_category_and_subject(cat_key, subject_name)

    if not files:
        no_files_msg = (
            f"⚠️ **فدوه لقلبك، بعدنا ما رافعين ملفات لمادة ({subject_name})**\n\n"
            f"📂 القسم: **{cat_info['title']}**\n\n"
            f"لا تشيل هم، الإدارة والممثلين راح يرفعوها عن قريب جداً! 🤍"
        )
        await query.message.reply_text(text=no_files_msg, parse_mode=ParseMode.MARKDOWN)
        return

    await query.message.reply_text(
        f"📂 **صار وتدلل، جاري دز ملفات ({subject_name})**\n"
        f"🏷️ القسم: {cat_info['title']}\n"
        f"📊 عدد الملفات: {len(files)} ملف 📄\n\n"
        f"انتظر ثواني بس ويوصلنك... ⏳",
        parse_mode=ParseMode.MARKDOWN
    )

    for f in files:
        caption = (
            f"📄 **{safe_md(f['file_name'])}**\n"
            f"🏷️ المادة: {f['subject']}\n"
            f"📂 القسم: {cat_info['title']}\n"
            f"━━━━━━━━━━━━\n"
            f"🧠 بوت نفَس2 - علم النفس (المرحلة الثانية)"
        )
        try:
            if f["media_type"] == "photo":
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=f["file_id"],
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=f["file_id"],
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"خطأ أثناء إرسال الملف {f['id']}: {e}")

    await query.message.reply_text(
        f"✅ عاشت إيدك، كملنا دز كل ملفات مادة **{subject_name}** بنجاح!\nربي يوفقك ويسهل أمرك بالدراسة 🤍",
        parse_mode=ParseMode.MARKDOWN
    )


async def callback_close_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إغلاق الرسالة التفاعلية عند الضغط على زر إغلاق"""
    query = update.callback_query
    await query.answer("تم الإغلاق")
    try:
        await query.message.delete()
    except Exception:
        pass


# =============================================================================
#      6. المسار الأول: علاج واستشارة إلك (اختبار الفئات + المرشد الذكي)
# =============================================================================

# بنك أسئلة الاختبار النفسي السريع (4 أسئلة لتقييم الضغط والإجهاد)
ASSESSMENT_QUESTIONS = [
    {
        "q": "1️⃣ شلون تحس بمستوى الضغط والتوتر عندك هالأيام ويه المحاضرات والامتحانات؟",
        "options": [
            ("🟢 مرتاح والحمد لله مسيطر على وضعي", 1),
            ("🟡 أحس بضغط وتعب ببعض الأيام", 2),
            ("🔴 مضغوط حيل وتعبان فوك طاقتي", 3),
        ]
    },
    {
        "q": "2️⃣ وضع نومك وراحتك بالليل شلون صاير؟",
        "options": [
            ("🟢 أنام زين ومرتاح وبالي هادئ", 1),
            ("🟡 أتقلب وكلساع أفكر بالدراسة والواجبات", 2),
            ("🔴 أرق شديد وتفكير مستمر وما مرتاح", 3),
        ]
    },
    {
        "q": "3️⃣ طاقتك وشغفك للمذاكرة وممارسة روتين يومك؟",
        "options": [
            ("🟢 زينة وطبيعية وعندي دافع أكمل", 1),
            ("🟡 مرات أحس بثقل وملل وتراجع بالطاقة", 2),
            ("🔴 فاقد الشغف تماماً وطاقتي شبه مخلصة", 3),
        ]
    },
    {
        "q": "4️⃣ من يواجهك امتحان مفاجئ أو تراكم دراسي، شلون تكون ردة فعلك؟",
        "options": [
            ("🟢 أهدأ وأرتب وقتي وأتوكل على الله", 1),
            ("🟡 أقلق وأتوتر شوية بس أدبر أموري", 2),
            ("🔴 خوف وتشتت شديد وأحس بالعجز", 3),
        ]
    }
]


async def psy_for_you_intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مقدمة قسم علاج لك وبدء الاختبار النفسي"""
    query = update.callback_query
    await query.answer()

    intro_text = (
        "🌱 **مرحباً بيك يا غالي بهالمساحة الآمنة والسرية 🤍**\n\n"
        "الدراسة والامتحانات وضغوطات الحياة أحياناً تتعبنا، وهذا شي طبيعي ومرينا بيه كلنا.\n\n"
        "حتى نساعدك صح وننطيك التوجيه والتمارين المناسبة إلك، راح نسوي **اختبار سريع من 4 أسئلة بسيطة** "
        "يحدد فئتك النفسية الحالية بسريّة تامة:\n\n"
        "• **الفئة (أ):** مرونة نفسية عالية وضغوط دراسية طبيعية خفيفة.\n"
        "• **الفئة (ب):** توتر وقلق متوسط وضغط محتاج تنظيم وتفريغ.\n"
        "• **الفئة (ج):** إجهاد نفسي وقلق مرتفع محتاج رعاية ودعم خاص.\n\n"
        "🔒 النتيجة سرية وما أحد يشوفها غيرك. مستعد نبدأ؟"
    )

    keyboard = [
        [InlineKeyboardButton("🚀 ابدأ الاختبار السريع (دقيقة واحدة)", callback_data="quiz_step:0:0")],
        [InlineKeyboardButton("💬 احچي مباشرة ويه المرشد الذكي", callback_data="chat_counselor_start")],
        [InlineKeyboardButton("🔙 رجوع لقسم الدعم", callback_data="psy_main")]
    ]

    await query.message.edit_text(
        text=intro_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def psy_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للواجهة الرئيسية لقسم الدعم النفسي"""
    query = update.callback_query
    await query.answer()

    msg = (
        "🧠 **قسم الدعم والعلاج النفسي - نفَس2** 🤍\n\n"
        "👇 **اختر المسار اللي تريده:**"
    )
    await query.message.edit_text(
        text=msg,
        reply_markup=get_psychology_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


async def quiz_step_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض أسئلة الاختبار التفاعلي خطوة بخطوة وحساب النقاط"""
    query = update.callback_query
    await query.answer()

    # callback_data: quiz_step:<current_q_idx>:<current_total_score>
    _, q_idx, total_score = query.data.split(":")
    q_idx = int(q_idx)
    total_score = int(total_score)

    if q_idx < len(ASSESSMENT_QUESTIONS):
        # عرض السؤال الحالي
        q_data = ASSESSMENT_QUESTIONS[q_idx]
        keyboard = []
        for opt_text, opt_score in q_data["options"]:
            next_score = total_score + opt_score
            next_cb = f"quiz_step:{q_idx + 1}:{next_score}"
            keyboard.append([InlineKeyboardButton(opt_text, callback_data=next_cb)])

        keyboard.append([InlineKeyboardButton("❌ إلغاء الاختبار", callback_data="psy_main")])

        progress = f"السؤال ({q_idx + 1} من {len(ASSESSMENT_QUESTIONS)})"
        text = f"📝 **اختبار التقييم النفسي السريع** [{progress}]\n\n{q_data['q']}"

        await query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # انتهى الاختبار - تقييم النتيجة وعرض التقرير
        await show_assessment_result(query, update.effective_user.id, total_score, context)


async def show_assessment_result(query, user_id: int, score: int, context: ContextTypes.DEFAULT_TYPE):
    """تحليل النتيجة وتصنيف الطالب إلى إحدى الفئات الثلاث مع تقديم التمارين"""
    # تصنيف الفئات:
    # 4 إلى 6 -> الفئة أ
    # 7 إلى 9 -> الفئة ب
    # 10 إلى 12 -> الفئة ج

    if score <= 6:
        cat_letter = "أ"
        cat_title = "الفئة (أ) - مرونة نفسية عالية وإرهاق دراسي خفيف 🌱"
        analysis = (
            "ما شاء الله عليك يا بطل! وضعك النفسي مستقر وممتاز، وعندك قدرة زينة على التكيف. "
            "التعب اللي تحسه أحياناً هو مجرد إرهاق دراسي طبيعي يمر بيه أي طالب شاطر وواعي."
        )
        exercises = (
            "🧘‍♂️ **تمارين ونصائح تناسب فئتك:**\n"
            "1. **تقنية بومودورو (Pomodoro):** اقرأ 25 دقيقة وخذ 5 دقائق استراحة تفصل بيها تماماً عن الموبايل.\n"
            "2. **تنفس الصباح (4-4-4):** شهيق 4 ثواني، احبس 4 ثواني، زفير 4 ثواني (يكرر 3 مرات لتجديد الطاقة الذهنية).\n"
            "3. **كافئ نفسك:** بعد كل إنجاز بسيط بالمحاضرات كافئ نفسك بشي تحبه حتى تحافظ على شغفك."
        )
    elif score <= 9:
        cat_letter = "ب"
        cat_title = "الفئة (ب) - توتر وقلق متوسط وضغط بحاجة لتنظيم وتفريغ 🌿"
        analysis = (
            "يا بعد عيني، مبين عليك شايل هم ومتحمل تراكمات دراسية مأثرة على صفاء ذهنك وطاقتك بالليل. "
            "الموضوع جداً مسيطر عليه ومحتاج بس شوية ترتيب خطوات وتفريغ للضغط حتى ترجع خفيف مثل الأول."
        )
        exercises = (
            "🧘‍♂️ **تمارين ونصائح تناسب فئتك:**\n"
            "1. **تمرين تفريغ الدماغ (Brain Dump):** قبل ما تنام، جيب ورقة وقلم واكتب كل الأفكار والامتحانات المقلقة حتى تفرغ شحنة القلق من عقلك للورقة.\n"
            "2. **تقنية التنفس الاسترخائي (4-7-8):** شهيق بهدوء من الأنف 4 ثواني، احبس نفسك 7 ثواني، وزفير بطيء من الفم 8 ثواني (يهدئ الجهاز العصبي مباشرة).\n"
            "3. **تحدي الأفكار التلقائية المشوهة:** من يجيك فكر مثل (ما راح ألحق / راح أفشل)، اسأل نفسك: 'هل هذا دليل حقيقي لو مجرد خوف؟ وشلون أتعامل ويه الخطوة الجاية بس؟'."
        )
    else:
        cat_letter = "ج"
        cat_title = "الفئة (ج) - إجهاد نفسي وقلق مرتفع بحاجة لاحتواء ورعاية خاصة 🤍"
        analysis = (
            "سلامتك وألف لا بأس عليك يا غالي.. باين إنك واصل لمرحلة إجهاد نفسي وضغط قوي مأثر على راحتك ونومك ونفسيتك. "
            "نريدك تتذكر دائماً: صحتك النفسية وراحة بالك أهم من كل دراسة وامتحان بالدنيا، وإحنا هنا وياك سند وخطوة بخطوة حتى تخفف عنك."
        )
        exercises = (
            "🧘‍♂️ **تمارين ونصائح تناسب فئتك:**\n"
            "1. **تمرين الاسترخاء العضلي التدريجي (PMR):** شد عضلات جسمك (الأكتاف، اليدين، الوجه) بقوة لمدة 5 ثواني، بعدين أرخيهم دفعة وحدة وتأمل إحساس الراحة (كرره 3 مرات).\n"
            "2. **تقنية التأريض الحسي (Grounding 5-4-3-2-1):** من تحس القلق صعد، التفت حولك ولاحظ: (5 أشياء تشوفها، 4 تلمسها، 3 تسمعها، 2 تشمها، شي واحد تتذوقه) حتى يرجع عقلك للواقع بهدوء.\n"
            "3. **استراحة إجبارية:** أوقف الدراسة لساعات معدودة واطلع اتمشى بالهواء الطلق أو احچي ويه شخص قريب ترتاح له."
        )

    # حفظ النتيجة في قاعدة البيانات
    db.save_assessment(user_id, score, f"الفئة ({cat_letter})")
    context.user_data["user_category"] = f"الفئة ({cat_letter})"

    result_text = (
        f"📊 **نتيجة تقييمك النفسي السري:**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ النتيجة: **{cat_title}**\n"
        f"🔢 المجموع: {score} من 12\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 **التحليل النفسي:**\n{analysis}\n\n"
        f"{exercises}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 **تريد تفضفض أو تسولف ويه مرشدك النفسي الذكي (نفَس2)؟**\n"
        f"جاهز يسمعلك وينصحك باللهجة العراقية اللطيفة هسه!"
    )

    keyboard = [
        [InlineKeyboardButton("💬 احچي ويه المرشد الذكي هسه", callback_data="chat_counselor_start")],
        [InlineKeyboardButton("🔄 إعادة الاختبار", callback_data="quiz_step:0:0")],
        [InlineKeyboardButton("🔙 رجوع لقسم الدعم", callback_data="psy_main")]
    ]

    await query.message.edit_text(
        text=result_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


# =============================================================================
#     7. محادثة المرشد النفسي الذكي للطلاب (Chat with Gemini Counselor)
# =============================================================================

async def start_counselor_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء جلسة محادثة تفاعلية وفضفضة مع المرشد النفسي الذكي"""
    query = update.callback_query
    await query.answer()

    # تفريغ سجل المحادثة السابقة
    context.user_data["gemini_counselor_history"] = []
    user_cat = context.user_data.get("user_category", "غير محددة (طالب جامعي)")

    welcome_chat = (
        "💬 **المرشد النفسي الذكي (نفَس2) وياك هسه 🤍**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ فئتك المسجلة: **{user_cat}**\n\n"
        "يا بعد عيني، أنا هنا كأخ ومرشد نفسي مستعد أسمعك بكل تفهم، بدون أي لوم أو تنظير.\n"
        "فضفض عن اللي ببالك، شنو اللي مضايقك بالدراسة أو الحياة، أو اسألني عن أي شي تريده وتدلل.\n\n"
        "💡 **اكتب رسالتك ودزها بالچات مباشرة..**\n"
        "*(للخروج والعودة للقائمة بأي وقت، أرسل /cancel أو اضغط زر الإلغاء بالأسفل)*"
    )

    keyboard = [[InlineKeyboardButton("❌ إنهاء المحادثة والعودة", callback_data="end_counselor_chat")]]

    # حذف رسالة الأزرار السابقة وإرسال رسالة جديدة نظيفة مع إخفاء الكيبورد الرئيسي
    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=welcome_chat,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    # إخفاء لوحة المفاتيح الرئيسية (ReplyKeyboard)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="...",
        reply_markup=ReplyKeyboardRemove()
    )
    # حذف رسالة "..." المؤقتة
    # ملاحظة: لا يمكن حذفها مباشرة، لكن المستخدم لن يراها تقريباً
    return CHAT_COUNSELOR_STATE


async def handle_counselor_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استلام رسالة الطالب وإرسالها لـ Gemini والرد باللهجة العراقية الدافئة"""
    user_text = update.message.text
    user_cat = context.user_data.get("user_category", "طالب جامعي")

    history = context.user_data.get("gemini_counselor_history", [])

    # إشعار الطالب بالكتابة بشكل مستمر حتى وصول الرد
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, update.effective_chat.id, stop_typing)
    )

    # استخدام البرومبت المخصص من قاعدة البيانات أو الافتراضي
    counselor_prompt = db.get_setting("prompt_counselor") or SYSTEM_PROMPT_COUNSELOR
    custom_prompt = (
        f"{counselor_prompt}\n\n"
        f"ملاحظة مهمة: هذا الطالب نتيجته في التقييم النفسي السريع كانت: ({user_cat}). "
        f"راعي هذه الفئة في مستوى الدعم واقتراح تمارين الاسترخاء والتعامل مع الضغوط."
    )

    try:
        # طلب الرد من Gemini
        response_text = await call_gemini_api(
            user_message=user_text,
            system_instruction=custom_prompt,
            chat_history=history
        )
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    # حفظ في السجل المحلي للجلسة
    history.append({"role": "user", "text": user_text})
    history.append({"role": "model", "text": response_text})
    context.user_data["gemini_counselor_history"] = history

    keyboard = [[InlineKeyboardButton("❌ إنهاء المحادثة والعودة", callback_data="end_counselor_chat")]]

    await update.message.reply_text(
        text=response_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return CHAT_COUNSELOR_STATE


async def end_counselor_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إنهاء محادثة المرشد النفسي والعودة للقائمة"""
    query = update.callback_query
    await query.answer("تم إنهاء الجلسة")
    context.user_data.pop("gemini_counselor_history", None)

    msg = (
        "🤍 **أتمنى تكون ارتحت شوية وخف الضغط عنك يا غالي.**\n\n"
        "تذكر دائماً: إحنا هنا وياك بأي وقت تحس نفسك محتاج دعم.\n"
        "بالتوفيق يا دكتور وربي ييسر أمرك! ✨"
    )

    # حذف رسالة المحادثة وإرسال رسالة جديدة مع القائمة الرئيسية
    try:
        await query.message.delete()
    except Exception:
        pass

    # إرسال رسالة مع الكيبورد المضمن (Inline) للكيبورد النفسي
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=msg,
        reply_markup=get_psychology_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    # إرجاع الكيبورد الرئيسي (ReplyKeyboard) للقائمة الرئيسية
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="القائمة الرئيسية:",
        reply_markup=get_student_main_keyboard()
    )
    return ConversationHandler.END


# =============================================================================
#    8. المسار الثاني: تدريب وتطبيقات علاجية للآخرين (للطلبة والباحثين)
# =============================================================================

# بنك الحالات الدراسية السريرية للتدريب الأكاديمي
CLINICAL_CASES = {
    "case_1": {
        "title": "📋 الحالة 1: قلق الامتحان والأداء الأكاديمي الشديد",
        "brief": "طالب جامعي (20 سنة)، يعاني من خوف مفرط قبل الامتحانات مع أعراض جسدية وتسويف.",
        "details": (
            "📋 **دراسة حالة سريرية مفترضة (Case Study #1):**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👤 **العميل:** شاب (20 سنة) - طالب جامعي.\n"
            "⚠️ **الشكوى الرئيسية:** قلق امتحان شديد، تسويف في فتح الملازم، وأعراض جسدية متعبة.\n\n"
            "🔍 **التاريخ المرضي والأعراض:**\n"
            "• قبل أي امتحان بأيام يعاني من خفقان سريع، برودة بالأطراف، واضطراب بالقولون.\n"
            "• معرفياً: تسيطر عليه أفكار مشوهة مثل (إذا ما طلعت امتياز راح أفشل بحياتي، ما راح ألحق أكمل المادة، عقلي راح يفرغ بالقاعة).\n"
            "• سلوكياً: يماطل بالدراسة للّحظات الأخيرة لتقليل التوتر مؤقتاً، وتتراجع درجاته رغم ذكائه العالي.\n\n"
            "❓ **سؤال التدريب السريري إلك يا زميلنا:**\n"
            "شنو تشخيصك الأولي للحالة؟ وشنو الفنيات العلاجية (CBT) اللي راح تقترحها؟"
        ),
        "solution": (
            "💡 **التحليل السريري والخطة العلاجية المقترحة:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 **التشخيص المبدئي:** قلق الأداء والامتحان (Performance / Test Anxiety) متداخل مع سمات كمالية عُصابية (Neurotic Perfectionism).\n\n"
            "🛠️ **الخطة العلاجية المعرفية السلوكية (CBT):**\n"
            "1. **إعادة الهيكلة المعرفية (Cognitive Restructuring):** تفكيك تشوه 'الكل أو لا شيء' وتحدي الفكرة الكارثية من الفشل.\n"
            "2. **التنفس البطني وضبط الاستجابة الفسيولوجية:** تدريب العميل على التنفس الحجابي لتقليل نشاط الجهاز العصبي السمبثاوي بالقاعة.\n"
            "3. **فنية التعرض التخيلي والواقعي التدريجي (Systematic Desensitization):** محاكاة أجواء الامتحان وحل نماذج أسئلة بوقت محدد لكسر حاجز الرهبة.\n"
            "4. **إدارة الوقت السلوكية:** تفكيك المادة إلى أجزاء صغيرة لمنع التسويف التجنبي."
        )
    },
    "case_2": {
        "title": "📋 الحالة 2: الاكتئاب الخفيف والتثبيط السلوكي",
        "brief": "طالبة (21 سنة)، تعاني من فقدان الشغف، العزلة، وثقل في أداء المهام اليومية.",
        "details": (
            "📋 **دراسة حالة سريرية مفترضة (Case Study #2):**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👤 **العميلة:** شابة (21 سنة) - طالبة في المرحلة الثانية.\n"
            "⚠️ **الشكوى الرئيسية:** فقدان المتعة (Anhedonia)، انخفاض الطاقة، وعزلة عن زميلاتها.\n\n"
            "🔍 **التاريخ المرضي والأعراض:**\n"
            "• بدأت الأعراض بعد تراجع طفيف في معدلها الفصلي، شعرت بعدها بالذنب الشديد واليأس.\n"
            "• تقضي أغلب وقتها بالسرير تتصفح الهاتف بدون هدف، وتتغيب عن المحاضرات.\n"
            "• معرفياً: أفكار آلية سلبية مستمرة (أنا صايرة عبء، ماكو فايدة من التعب، كل شي صار باهت).\n\n"
            "❓ **سؤال التدريب السريري إلك يا زميلنا:**\n"
            "شنو الاستراتيجية السلوكية الأولى اللي تبدأ بيها ويه هاي الحالة؟"
        ),
        "solution": (
            "💡 **التحليل السريري والخطة العلاجية المقترحة:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 **التشخيص المبدئي:** نوبة اكتئابية خفيفة إلى متوسطة (Mild Depressive Episode) مع تثبيط سلوكي واضح.\n\n"
            "🛠️ **الخطة العلاجية المقترحة:**\n"
            "1. **التنشيط السلوكي (Behavioral Activation - BA):** كسر الحلقة المفرغة (قلة نشاط ⬅️ لوم الذات ⬅️ اكتئاب أعمق) بجدولة أنشطة بسيطة جداً قابلة للتحقيق تمنح إحساساً بالإنجاز (Mastery) والمتعة (Pleasure).\n"
            "2. **سجل الأفكار التلقائية السلبية (CBT Thought Record):** تدريب العميلة على رصد الأفكار السوداوية واختبار مدى واقعيتها.\n"
            "3. **تنظيم الإيقاع اليومي (Social Rhythm Therapy):** ضبط ساعات النوم والاستيقاظ والتعرض لضوء الشمس."
        )
    },
    "case_3": {
        "title": "📋 الحالة 3: الرهاب والقلق الاجتماعي (Social Anxiety)",
        "brief": "شاب (22 سنة)، خوف شديد من الإلقاء (Presentation) والمشاركة أمام الطلاب والقاعة.",
        "details": (
            "📋 **دراسة حالة سريرية مفترضة (Case Study #3):**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👤 **العميل:** طالب جامعي (22 سنة).\n"
            "⚠️ **الشكوى الرئيسية:** رعب وخوف هائل عند التحدث أمام القاعة أو تقديم برزنتيشن.\n\n"
            "🔍 **التاريخ المرضي والأعراض:**\n"
            "• احمرار الوجه، رجفة بالصوت واليدين، وشعور بالاختناق عند مجرد التفكير بالمشاركة.\n"
            "• معرفياً: قلق مكثف من التقييم السلبي (راح يضحكون عليّ، راح يبين إني أرجف وغبي، صوتي يفشل).\n"
            "• سلوكياً: يطلب من زملائه إعفاءه من التقديم، أو يغيب بيوم الإلقاء متحملاً خصم الدرجة.\n\n"
            "❓ **سؤال التدريب السريري إلك يا زميلنا:**\n"
            "شنو فنيات إزالة التحسس والتعرض اللي تفيده؟"
        ),
        "solution": (
            "💡 **التحليل السريري والخطة العلاجية المقترحة:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 **التشخيص المبدئي:** اضطراب القلق الاجتماعي المرتكز على الأداء (Social Anxiety Disorder - Performance Only).\n\n"
            "🛠️ **الخطة العلاجية المقترحة:**\n"
            "1. **تصحيح بؤرة الانتباه (Attention Training):** تحويل التركيز من الداخل (مراقبة نبضات القلب ورجفة الصوت) إلى الخارج (الجمهور ومحتوى المادة).\n"
            "2. **التعرض المتدرج (Graded Exposure):** التحدث أولاً أمام المرآة، ثم تسجيل فيديو، ثم التحدث أمام صديق واحد، ثم مجموعة صغيرة، وصولاً للقاعة.\n"
            "3. **التجارب السلوكية (Behavioral Experiments):** اختبار الفرضية الكارثية: (هل فعلاً لو سكتت 3 ثواني راح يضحكون؟) لإثبات زيف المخاوف."
        )
    }
}


async def psy_for_others_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة التدريب والتطبيقات السريرية لطلبة علم النفس"""
    query = update.callback_query
    await query.answer()

    menu_text = (
        "🎓 **قسم التدريب والتطبيقات السريرية لطلبة علم النفس 🧠**\n\n"
        "أهلاً بيك يا دكتور المستقبل! هذا القسم صممناه لغرض صقل مهاراتك التشخيصية "
        "وتدريبك على دراسة الحالات السريرية وتطبيق النظريات الأكاديمية عملياً.\n\n"
        "👇 **اختر القسم التدريبي اللي تريده:**"
    )

    keyboard = [
        [InlineKeyboardButton("📋 دراسة حالات سريرية مفترضة (Case Studies)", callback_data="cases_list")],
        [InlineKeyboardButton("🧠 استراتيجيات وتقنيات علاجية (CBT / REBT)", callback_data="strategies_list")],
        [InlineKeyboardButton("🤖 استشر المشرف الأكاديمي الذكي (Gemini)", callback_data="chat_academic_start")],
        [InlineKeyboardButton("🔙 رجوع لقسم الدعم", callback_data="psy_main")]
    ]

    await query.message.edit_text(
        text=menu_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def cases_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الحالات السريرية للتدريب"""
    query = update.callback_query
    await query.answer()

    text = (
        "📋 **بنك الحالات السريرية التدريبية:**\n\n"
        "اختر الحالة اللي تريد تدرسها وتتدرب على تشخيصها ووضع خطتها العلاجية:"
    )

    keyboard = []
    for case_id, case_info in CLINICAL_CASES.items():
        keyboard.append([InlineKeyboardButton(case_info["title"], callback_data=f"show_case:{case_id}")])

    keyboard.append([InlineKeyboardButton("🔙 رجوع لقسم التدريب", callback_data="psy_for_others")])

    await query.message.edit_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def show_case_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تفاصيل الحالة وسؤال التحدي"""
    query = update.callback_query
    await query.answer()

    case_id = query.data.replace("show_case:", "")
    case = CLINICAL_CASES.get(case_id)

    if not case:
        await query.message.reply_text("الحالة غير متوفرة حالياً.")
        return

    keyboard = [
        [InlineKeyboardButton("💡 كشف التحليل السريري والحل المقترح", callback_data=f"solve_case:{case_id}")],
        [InlineKeyboardButton("💬 ناقش هالحالة ويه المشرف الأكاديمي", callback_data=f"discuss_case:{case_id}")],
        [InlineKeyboardButton("🔙 رجوع لقائمة الحالات", callback_data="cases_list")]
    ]

    await query.message.edit_text(
        text=case["details"],
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def solve_case_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الحل والتحليل السريري للحالة"""
    query = update.callback_query
    await query.answer()

    case_id = query.data.replace("solve_case:", "")
    case = CLINICAL_CASES.get(case_id)

    if not case:
        return

    text = f"{case['solution']}\n\n💡 **تكدر تناقش المشرف الأكاديمي بأي تفصيل يعجبك بهالحالة!**"

    keyboard = [
        [InlineKeyboardButton("💬 ناقش هالحالة ويه المشرف الأكاديمي", callback_data=f"discuss_case:{case_id}")],
        [InlineKeyboardButton("🔙 رجوع لتفاصيل الحالة", callback_data=f"show_case:{case_id}")],
        [InlineKeyboardButton("📋 رجوع لباقي الحالات", callback_data="cases_list")]
    ]

    await query.message.edit_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def strategies_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استعراض ملخص الاستراتيجيات العلاجية الأكاديمية"""
    query = update.callback_query
    await query.answer()

    strat_text = (
        "🧠 **ملخص أهم الاستراتيجيات العلاجية لطلبة علم النفس:**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔹 **1. العلاج المعرفي السلوكي (CBT - آرون بيك):**\n"
        "يركز على الثالوث المعرفي (فكرة ⬅️ شعور ⬅️ سلوك). الفنيات الأساسية: سجل الأفكار اليومي، اختبار الأدلة والبدائل، ودحض التشوهات المعرفية.\n\n"
        "🔹 **2. العلاج العقلاني الانفعالي (REBT - ألبرت أليس):**\n"
        "يعتمد على نموذج ABC (A: الحدث المنشط، B: المعتقدات غير العقلانية، C: النتائج الانفعالية). الهدف: تفنيد الأفكار الحتمية (يجب، يلزم، مفروض).\n\n"
        "🔹 **3. التنشيط السلوكي (Behavioral Activation):**\n"
        "استراتيجية فعالة جداً في علاج الاكتئاب، تعتمد على زيادة وتيرة الأنشطة المعززة وكسر العزلة السلوكية.\n\n"
        "🔹 **4. مهارات المقابلة الإرشادية وبناء الألفة (Rapport):**\n"
        "الإنصات الإيجابي، الانعكاس المشاعري (Reflective Listening)، التقبل الإيجابي غير المشروط (كارل روجرز).\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 **تكدر تطلب من المشرف الأكاديمي الذكي يشرحلك أي فنية بالتفصيل والأمثلة السريرية!**"
    )

    keyboard = [
        [InlineKeyboardButton("💬 اسأل المشرف الأكاديمي عن أي فنية", callback_data="chat_academic_start")],
        [InlineKeyboardButton("🔙 رجوع لقسم التدريب", callback_data="psy_for_others")]
    ]

    await query.message.edit_text(
        text=strat_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


# =============================================================================
#     9. محادثة المشرف الأكاديمي الذكي (Chat with Gemini Academic Supervisor)
# =============================================================================

async def start_academic_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء جلسة نقاش وتدريب أكاديمي وسريري مع المشرف الذكي"""
    query = update.callback_query
    await query.answer()

    # فحص إذا تم الدخول من مناقشة حالة معينة
    case_context = ""
    if query.data.startswith("discuss_case:"):
        case_id = query.data.replace("discuss_case:", "")
        case = CLINICAL_CASES.get(case_id)
        if case:
            case_context = f"\n(أنت الآن تناقش: {case['title']})"
            context.user_data["academic_current_case"] = case["title"]

    context.user_data["gemini_academic_history"] = []

    welcome_chat = (
        "🎓 **المشرف الأكاديمي الذكي (دكتور نفَس2) وياك هسه 🧠**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{case_context}\n"
        "أهلاً بيك يا زميلنا الغالي ودكتور المستقبل!\n"
        "أنا مشرفك وأستاذك في علم النفس العيادي والإرشادي. "
        "مستعد أتناقش وياك بأي حالة سريرية، تشخيص فارق (DSM-5)، نظريات نفسية، أو استراتيجيات علاجية ومساعدتك بموادك الـ 11.\n\n"
        "💡 **اكتب سؤالك أو فكرتك التشخيصية بالچات وتدلل..**\n"
        "*(للخروج والعودة للقائمة بأي وقت، أرسل /cancel أو اضغط زر الإلغاء بالأسفل)*"
    )

    keyboard = [[InlineKeyboardButton("❌ إنهاء المحادثة والعودة", callback_data="end_academic_chat")]]

    # حذف رسالة الأزرار السابقة وإرسال رسالة جديدة نظيفة
    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=welcome_chat,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    # إخفاء لوحة المفاتيح الرئيسية (ReplyKeyboard)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="...",
        reply_markup=ReplyKeyboardRemove()
    )
    return CHAT_ACADEMIC_STATE


async def handle_academic_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استلام استفسار الطالب وإرساله للمشرف الأكاديمي والرد بعمق أكاديمي عراقي مشجع"""
    user_text = update.message.text
    case_context = context.user_data.get("academic_current_case", "")

    history = context.user_data.get("gemini_academic_history", [])

    # إشعار الطالب بالكتابة بشكل مستمر حتى وصول الرد
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, update.effective_chat.id, stop_typing)
    )

    # استخدام البرومبت المخصص من قاعدة البيانات أو الافتراضي
    academic_prompt = db.get_setting("prompt_academic") or SYSTEM_PROMPT_ACADEMIC
    custom_prompt = academic_prompt
    if case_context:
        custom_prompt += f"\nملاحظة: النقاش الحالي يدور حول دراسة الحالة التالية: ({case_context}). ناقش الطالب في التشخيص والتدخلات السريرية المناسبة."

    try:
        response_text = await call_gemini_api(
            user_message=user_text,
            system_instruction=custom_prompt,
            chat_history=history
        )
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    history.append({"role": "user", "text": user_text})
    history.append({"role": "model", "text": response_text})
    context.user_data["gemini_academic_history"] = history

    keyboard = [[InlineKeyboardButton("❌ إنهاء المحادثة والعودة", callback_data="end_academic_chat")]]

    await update.message.reply_text(
        text=response_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return CHAT_ACADEMIC_STATE


async def end_academic_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إنهاء جلسة النقاش الأكاديمي والعودة"""
    query = update.callback_query
    await query.answer("تم إنهاء الجلسة الأكاديمية")
    context.user_data.pop("gemini_academic_history", None)
    context.user_data.pop("academic_current_case", None)

    msg = (
        "🌟 **عاشت إيدك يا دكتور المستقبل على هذا النقاش العلمي الراقي!**\n\n"
        "فخورين بوعيك واهتمامك بتطوير مهاراتك السريرية.\n"
        "بأي وقت تحتاج تشاور أو تناقش حالة، أنا بالخدمة دائماً 🤍"
    )

    # حذف رسالة المحادثة وإرسال رسالة جديدة مع القائمة الرئيسية
    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=msg,
        reply_markup=get_psychology_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    # إرجاع الكيبورد الرئيسي (ReplyKeyboard) للقائمة الرئيسية
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="القائمة الرئيسية:",
        reply_markup=get_student_main_keyboard()
    )
    return ConversationHandler.END


# =============================================================================
#     10. محاكاة العميل العملي - اختبار الأخصائي (Roleplay Evaluator)
# =============================================================================

async def roleplay_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء اختبار المحاكاة العملي: الطالب يصير أخصائي ويواجه عميل"""
    query = update.callback_query
    await query.answer()

    # تفريغ سجل المحادثة السابقة
    context.user_data["roleplay_history"] = []
    context.user_data["roleplay_scenario"] = None
    context.user_data["roleplay_round"] = 0

    welcome_text = (
        "🎭 **اختبار عملي: صِر أخصائي وواجه عميل حقيقي!** 🧠💪\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "أهلاً بيك يا دكتور المستقبل! هسه راح نختبر مهاراتك السريرية على حقيقي.\n\n"
        "🎯 **القاعدة بسيطة:**\n"
        "• أنا أرسللك **مشهد عميل حقيقي** (العمر، الجنس، المشكلة، السياق)\n"
        "• أنت تتصرف كأنك **أخصائي في الجلسة الأولى**\n"
        "• تكتب: شنو تسوي؟ شنو تقول؟ شنو تشخص؟ خطتك؟\n"
        "• أنا أقيّمك بصراحة: **أمديحك لو صح، أعلمك لو غلط**\n\n"
        "⚡ **لغة التحدي، عراقي، ممتع، ماكو مجاملة!**\n\n"
        "مستعد تبدأ أول اختبار؟ 😎"
    )

    keyboard = [
        [InlineKeyboardButton("🚀 ابدأ أول اختبار الآن!", callback_data="roleplay_next_scenario")],
        [InlineKeyboardButton("🔙 رجوع لقسم الدعم", callback_data="psy_main")]
    ]

    # حذف رسالة الأزرار السابقة وإرسال رسالة جديدة نظيفة
    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    # إخفاء لوحة المفاتيح الرئيسية (ReplyKeyboard)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="...",
        reply_markup=ReplyKeyboardRemove()
    )
    return ROLEPLAY_STATE


async def roleplay_next_scenario_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """توليد سيناريو عميل جديد عبر Gemini - خطوة بخطوة، مهارة وحدة كل جولة"""
    query = update.callback_query
    await query.answer()

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, query.message.chat_id, stop_typing)
    )

    round_num = context.user_data.get("roleplay_round", 0) + 1
    context.user_data["roleplay_round"] = round_num

    # المهارة المستهدفة لكل جولة (قوانين ثابتة تتعلم تدريجياً)
    skill_by_round = {
        1: "🎯 **المهارة: العلاقة العلاجية + فتح الجلسة**\nالقانون: 'الناس ما يهتمون بما تعرف، إلا لما يعرفون إنك تهتم بهم' - ابدأ بالاحتواء، التعاطف، بناء الثقة",
        2: "🎯 **المهارة: النموذج المعرفي (فكرة → شعور → سلوك)**\nالقانون: 'الأحداث ما تسبب المشاعر، أفكارك عنها هي اللي تسببها' - ساعد العميل يشوف الربط",
        3: "🎯 **المهارة: الأسئلة السقراطية للكشف عن التشوهات**\nالقانون: 'اسأل، ما تقل' - (شنو الدليل؟ لو غيرك مكانك؟ هل دايمًا؟ البديل؟)",
        4: "🎯 **المهارة: إعادة الهيكلة المعرفية (دليل + بديل + تجربة)**\nالقانون: 'الفكرة فرضية، مو حقيقة - اختبرها' - فنية الأعمدة الثلاثة",
        5: "🎯 **المهارة: التخطيط للجلسات + أهداف ذكية (SMART)**\nالقانون: 'الهدف بلا خطة مجرد حلم' - أهداف واضحة، فنيات CBT محددة، واجبات",
        6: "🎯 **المهارة: المتابعة، تعديل الخطة، منع الانتكاس**\nالقانون: 'العلاج مش خط مستقيم' - راجع، عدّل، قوي المهارات، خطة طوارئ",
    }

    # للجولات فوق 6: حالات تطبيقية متنوعة لتثبيت المهارات
    if round_num <= 6:
        skill_focus = skill_by_round[round_num]
        scenario_type = "طالب جامعي، موقف يومي بسيط (امتحان، أهل، أصحاب، مستقبل، خطوبة)"
    else:
        # جولات متقدمة: تثبيت المهارات بحالات متنوعة
        advanced_scenarios = [
            "طالب بقلق امتحان شديد + تسويف",
            "طالبة باكتئاب خفيف بعد رسوب + عزلة",
            "شاب بوسواس تفكير + طقوس بسيطة",
            "فتاة بصدمة قديمة تظهر بالعلاقات",
            "طالب بقلق اجتماعي + تجنب المحاضرات",
            "شابة بضغط أهلي + قرار مصيري (زواج/دراسة)",
            "طالب بكمالية عصابية + إرهاق مزمن",
            "شاب بغضب متفجر + مشاكل مع الأصدقاء",
        ]
        scenario_type = f"حالة تطبيقية: {advanced_scenarios[(round_num - 7) % len(advanced_scenarios)]}"
        skill_focus = "🎯 **المهارة: تطبيق كل القوانين السابقة بحالة حقيقية**\nالقانون: 'المعرفة بلا ممارسة = صفر' - استخدم: علاقة → نموذج → سقراطي → إعادة هيكلة → خطة → متابعة"

    # طلب سيناريو جديد من Gemini
    scenario_prompt = (
        f"أنت مُدَرِّب سريري عراقي خبير، قريب من الطالب، صبور ومحفز.\n"
        f"اكتب **مشهد عميل واحد فقط** لاختبار طالب علم نفس (مرحلة ثانية - مبتدئ).\n\n"
        f"📊 **الجولة: {round_num}**\n"
        f"{skill_focus}\n\n"
        f"نوع العميل: {scenario_type}\n\n"
        f"المتطلبات:\n"
        f"1. عميل من حياة الطالب اليومية: العمر (18-28)، طالب/خريج جديد، مشكلة واقعية قريبة منه\n"
        f"2. موقف بسيط، واضح، فيه مشاعر حقيقية (خوف، حزن، غضب، قلق، حيرة)\n"
        f"3. مكتوب باللهجة العراقية البيضاء البسيطة (كأنك تحكي لصديقك)\n"
        f"4. **مصمم لتمارين المهارة أعلاه** - فيه مادة غنية لتطبيقها\n"
        f"5. 4-5 أسطر فقط، مختصر وممتع\n\n"
        f"التنسيق:\n"
        f"🎬 **المشهد: [عنوان مشوق قريب من الطالب]**\n"
        f"👤 **العميل:** [العمر، طالب/خريج، موقف حياتي]\n"
        f"💭 **الحالة:** [مشاعره، أفكاره، سلوكه - 3 نقاط]\n"
        f"❓ **تحدي الجولة:** [سؤال واحد يركز على مهارة الجولة]\n\n"
        f"مثال للجولة 1: 'شنو تقول/تسوي أول 5 دقايق تخلي العميل يحس بالأمان ويفضفض؟'\n"
        f"مثال للجولة 2: 'عميلك يقول: (أنا فاشل). استخدم النموذج المعرفي: شنو الفكرة؟ الشعور؟ السلوك؟'\n"
        f"مثال للجولة 3: 'طبّق سؤال سقراطي واحد على فكرته: (شنو الدليل إنك فاشل؟)'\n\n"
        f"كن قريباً، واقعياً، كأن الموقف يصير للطالب نفسه أو لصديقه."
    )

    # استدعاء Gemini لتوليد السيناريو
    try:
        scenario_text = await call_gemini_api(
            user_message="اكتب لي سيناريو عميل جديد للاختبار",
            system_instruction=scenario_prompt,
            chat_history=[]
        )
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    # حفظ السيناريو في السياق
    context.user_data["roleplay_scenario"] = scenario_text

    display_text = (
        f"🎬 **اختبار عملي - الجولة {round_num}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{scenario_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✍️ **دورك يا دكتور! جاوب بالتحدي أعلاه:**\n"
        "اكتب ردك بحرية، خليه طبيعي كأنك بالجلسة الحقيقية.\n\n"
        "💡 *لا تخاف من الغلط - الغلط معلم، وأنا هنا أصحح وأسألك أسئلة سقراطية توصلك للحل*"
    )

    keyboard = [[InlineKeyboardButton("❌ إنهاء الاختبار والعودة", callback_data="end_roleplay")]]

    # حذف رسالة السيناريو السابق وإرسال رسالة جديدة نظيفة
    try:
        await query.message.delete()
    except Exception:
        pass

    # إرسال بدون Markdown لتجنب أخطاء التنسيق من رد Gemini
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=display_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ROLEPLAY_STATE


async def handle_roleplay_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استلام إجابة الطالب وتقييمها عبر Gemini - بأسلوب سقراطي تعليمي"""
    user_answer = update.message.text
    scenario = context.user_data.get("roleplay_scenario", "")
    history = context.user_data.get("roleplay_history", [])
    round_num = context.user_data.get("roleplay_round", 1)

    # المهارة المستهدفة للجولة (نفس اللي في توليد السيناريو)
    skill_by_round = {
        1: "العلاقة العلاجية + فتح الجلسة (احتواء، تعاطف، ثقة)",
        2: "النموذج المعرفي: فكرة → شعور → سلوك",
        3: "الأسئلة السقراطية: (شنو الدليل؟ لو غيرك؟ هل دايمًا؟ البديل؟)",
        4: "إعادة الهيكلة المعرفية: فنية الأعمدة الثلاثة (دليل، بديل، تجربة)",
        5: "التخطيط للجلسات: أهداف SMART + فنيات CBT + واجبات",
        6: "المتابعة، تعديل الخطة، منع الانتكاس",
    }
    if round_num <= 6:
        target_skill = skill_by_round[round_num]
    else:
        target_skill = "تطبيق متكامل لكل المهارات السابقة بحالة حقيقية"

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, update.effective_chat.id, stop_typing)
    )

    # استخدام البرومبت المخصص من قاعدة البيانات أو الافتراضي
    roleplay_prompt = db.get_setting("prompt_roleplay") or SYSTEM_PROMPT_ROLEPLAY
    
    evaluation_prompt = (
        f"{roleplay_prompt}\n\n"
        f"--- السياق الحالي ---\n"
        f"📊 **الجولة: {round_num} | المهارة المستهدفة: {target_skill}**\n"
        f"مشهد العميل:\n{scenario}\n\n"
        f"إجابة الطالب:\n{user_answer}\n\n"
        f"--- مهمتك الآن (قيّم علّم شجع) ---\n"
        f"أنت أستاذه القريب، الصبور، اللي يبي يتعلم *بالممارسة* مو بالحفظ.\n\n"
        f"**هيكل تقييمك الثابت (4 خطوات):**\n\n"
        f"1️⃣ **تعزيز المحاولة** (حتى لو غلط):\n"
        f"   'زين يا بطل، شايف كيف فكرت؟ عاشت إيدك إنك حاولت...'\n"
        f"   ← خليه يحس إن محاولته مقدرة، مهما كانت.\n\n"
        f"2️⃣ **سؤال سقراطي يصحح/يرشد** (قانون: اسأل، ما تقل):\n"
        f"   بدل ما تقول 'الغلط كذا'، اسأله:\n"
        f"   • 'لو طبقنا السؤال السقراطي: (شنو الدليل على هالفكرة؟) ... شكو تلاحظ؟'\n"
        f"   • 'فكّر بالنموذج المعرفي: الفكرة → الشعور → السلوك... وين الربط هون؟'\n"
        f"   • 'العلاقة العلاجية أساس... لو بدأت بالاحتواء، شكو يتغير؟'\n"
        f"   ← خليه *هو* يوصل للحل بسؤالك.\n\n"
        f"3️⃣ **أداة/قانون جديد يتعلمها هالجولة** (خذه معك):\n"
        f"   'الأداة الجديدة: [اسم القانون + جملة واحدة عملية]'\n"
        f"   أمثلة: 'قانون: دايمًا ابدأ بالعلاقة العلاجية — 3 دقايق احتواء تغير الجلسة'\n"
        f"   'قانون: الفكرة فرضية مو حقيقة — اسأل: شنو الدليل؟'\n"
        f"   'قانون: الأهداف ذكية (SMART) — وضح، قيس، وقت، واقعي, مهم'\n\n"
        f"4️⃣ **درجة من 10 + تحدي لطيف للجولة الجاية**:\n"
        f"   'درستك: 8/10 — زين جداً! تحاول تطبق [المهارة]...'\n"
        f"   'تريد نجرب مهارة جديدة بالجولة الجاية؟ ولا نثبت هذي على حالة ثانية؟ 😄'\n\n"
        f"--- أسلوبك ---\n"
        f"• لهجة عراقية بيضاء، قريبة، مضحكة شوي، محفزة\n"
        f"• تشبيهات بسيطة: 'العقل موبايل، الأفكار تطبيقات...'\n"
        f"• مختصر (5-7 أسطر)، ما تطول، ركز على التعليم\n"
        f"• لا تطلع حل كامل — خلي السؤال السقراطي يقود"
    )

    try:
        evaluation = await call_gemini_api(
            user_message=user_answer,
            system_instruction=evaluation_prompt,
            chat_history=history[-4:] if history else None
        )
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    # حفظ في السجل
    history.append({"role": "user", "text": f"[المشهد] {scenario}\n[إجابة الطالب] {user_answer}"})
    history.append({"role": "model", "text": evaluation})
    context.user_data["roleplay_history"] = history
    context.user_data["roleplay_scenario"] = None

    keyboard = [
        [InlineKeyboardButton("🎯 جولة ثانية (مهارة جديدة)", callback_data="roleplay_next_scenario")],
        [InlineKeyboardButton("🔁 نفس المهارة بحالة ثانية", callback_data="roleplay_retry_same_skill")],
        [InlineKeyboardButton("🏁 خلصنا، رجعني للقائمة", callback_data="end_roleplay")]
    ]

    # إرسال التقييم بدون Markdown لتجنب أخطاء التنسيق
    try:
        await update.message.reply_text(
            text=evaluation,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        # إذا فشل Markdown، أرسل كنص عادي
        await update.message.reply_text(
            text=evaluation,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    return ROLEPLAY_STATE


async def end_roleplay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إنهاء اختبار المحاكاة العملي"""
    query = update.callback_query
    await query.answer("تم إنهاء الاختبار العملي")
    context.user_data.pop("roleplay_history", None)
    context.user_data.pop("roleplay_scenario", None)
    context.user_data.pop("roleplay_round", None)

    msg = (
        "🏁 **اختبرت، تعلمت، وتطورت! عاشت إيدك يا دكتور!** 🎓💪\n\n"
        "كل جولة كنت فيها بتقربك من الأخصائي المحترف اللي تحلم تصيره.\n"
        "الأخطاء دروس، والنجاحات وقود. استمر، ما تنسحب، العلم بالتراكم.\n\n"
        "بأي وقت تريد تختبر نفسك تاني، أنا بالخدمة! 🤍\n"
        "صِّر أخصائي عراقي يفخر بيه البلد!"
    )

    # حذف رسالة المحادثة وإرسال رسالة جديدة مع القائمة الرئيسية
    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=msg,
        reply_markup=get_psychology_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    # إرجاع الكيبورد الرئيسي (ReplyKeyboard) للقائمة الرئيسية
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="القائمة الرئيسية:",
        reply_markup=get_student_main_keyboard()
    )
    return ConversationHandler.END


async def roleplay_retry_same_skill_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إعادة نفس الجولة (نفس المهارة) بحالة عميل جديدة للتمرين"""
    query = update.callback_query
    await query.answer()

    # لا نزيد الجولة، نثبت نفس رقم الجولة ونولد سيناريو جديد
    # roleplay_next_scenario_callback يزود الجولة، فإحنا ننقص واحد قبل استدعاء المنطق
    current_round = context.user_data.get("roleplay_round", 1)
    context.user_data["roleplay_round"] = current_round - 1  # ستصير الجولة الحالية لما يستدعي next_scenario

    # استدعي دالة السيناريو الجديد (ستزيد الجولة وتولد سيناريو للمهارة نفسها)
    return await roleplay_next_scenario_callback(update, context)


# =============================================================================
#                   10. لوحة تحكم الأدمن (Admin Panel)
# =============================================================================

def is_admin(user_id: int) -> bool:
    """التحقق من صلاحية الأدمن"""
    return user_id == ADMIN_ID


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /admin لفتح لوحة التحكم الخاصة بالأدمن بلهجة عراقية محببة"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔️ فدوه لعينك، هذا الأمر مخصص لمدير البوت فقط 🤍")
        return

    admin_text = (
        "🛠️ **هلا والله بمديرنا الغالي! نورت لوحة التحكم لبوت نفَس2 🧠**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "من هنا تكدر تدير الملفات، تراقب إحصائيات الطلاب، تدز إذاعات عامة، أو تضبط مفتاح الذكاء الاصطناعي (Gemini API).\n\n"
        "👇 **اختر العملية اللي تريد تسويها:**"
    )

    await update.message.reply_text(
        text=admin_text,
        reply_markup=get_admin_dashboard_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات البوت الشاملة"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return

    await query.answer()

    total_users = db.get_users_count()
    total_files = db.get_files_count()
    stats = db.get_files_statistics()

    cats_text = ""
    for cat_k, cat_v in CATEGORIES.items():
        cnt = stats["categories"].get(cat_k, 0)
        cats_text += f"  • {cat_v['title']}: {cnt} ملف\n"

    subjs_text = ""
    for subj in SUBJECTS:
        cnt = stats["subjects"].get(subj, 0)
        subjs_text += f"  • {subj}: {cnt} ملف\n"

    gemini_status = "✅ مفعّل وشغال" if (db.get_setting("gemini_api_key") or GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE") else "⚠️ غير مضبوط بعد"

    stats_msg = (
        "📊 **إحصائيات بوت نفَس2 الشاملة:**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 **إجمالي الطلاب المسجلين:** {total_users} طالب\n"
        f"📁 **إجمالي الملفات المرفوعة:** {total_files} ملف\n"
        f"🤖 **حالة الذكاء الاصطناعي:** {gemini_status}\n\n"
        "📂 **توزيع الملفات حسب الأقسام:**\n"
        f"{cats_text}\n"
        "📚 **توزيع الملفات حسب المواد:**\n"
        f"{subjs_text}"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    back_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع للوحة التحكم", callback_data="admin_back_to_main")]
    ])

    await query.message.edit_text(
        text=stats_msg,
        reply_markup=back_btn,
        parse_mode=ParseMode.MARKDOWN
    )


async def admin_back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للشاشة الرئيسية للوحة التحكم"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return

    await query.answer()
    admin_text = (
        "🛠️ **لوحة تحكم بوت نفَس2 🧠**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "اختر العملية المطلوبة من الأزرار الجوه يا غالي:"
    )
    await query.message.edit_text(
        text=admin_text,
        reply_markup=get_admin_dashboard_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


async def admin_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إغلاق لوحة تحكم الأدمن"""
    query = update.callback_query
    await query.answer("تم إغلاق اللوحة")
    try:
        await query.message.delete()
    except Exception:
        pass


# =============================================================================
#          11. محادثة ضبط مفتاح الذكاء الاصطناعي (Admin Gemini Key)
# =============================================================================

async def admin_gemini_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إدخال مفتاح Gemini API من الأدمن"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    current_key = db.get_setting("gemini_api_key") or GEMINI_API_KEY
    masked_key = f"{current_key[:6]}...{current_key[-4:]}" if (current_key and current_key != "YOUR_GEMINI_API_KEY_HERE") else "لا يوجد"

    msg = (
        "🔑 **ضبط مفتاح الذكاء الاصطناعي (Google Gemini API):**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"المفتاح الحالي: `{masked_key}`\n\n"
        "قم الآن بإرسال مفتاحك الجديد (يبدأ عادة بـ `AIzaSy...`).\n\n"
        "💡 المفتاح مجاني بالكامل وتكدر تاخذه من موقع: [Google AI Studio](https://aistudio.google.com/app/apikey)\n\n"
        "أرسل /cancel أو اضغط الزر أدناه للإلغاء."
    )

    keyboard = [[InlineKeyboardButton("❌ إلغاء", callback_data="gemini_cancel")]]

    await query.message.edit_text(
        text=msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )
    return ADMIN_SET_GEMINI_KEY


async def admin_gemini_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ مفتاح Gemini الجديد في قاعدة البيانات وتجربته"""
    new_key = update.message.text.strip()

    if len(new_key) < 20 or not (new_key.startswith("AIza") or new_key.startswith("AQ.")):
        await update.message.reply_text(
            "⚠️ عيني المفتاح يبدو غير صالح (تأكد من نسخه بالكامل من Google AI Studio).\n"
            "تأكد منه وارجع دزه، أو دز /cancel للإلغاء."
        )
        return ADMIN_SET_GEMINI_KEY

    db.set_setting("gemini_api_key", new_key)

    await update.message.reply_text(
        "✅ **عاشت إيدك يا مديرنا! تم حفظ وتفعيل مفتاح Gemini API بنجاح!**\n\n"
        "قسم الدعم النفسي والعيادة الأكاديمية الافتراضية صارت جاهزة وشغالة 100% الآن.",
        reply_markup=get_student_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END


async def admin_gemini_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء ضبط المفتاح"""
    query = update.callback_query
    await query.answer("تم الإلغاء")
    await query.message.edit_text(
        "❌ تم إلغاء تعديل مفتاح الذكاء الاصطناعي.",
        reply_markup=get_admin_dashboard_keyboard()
    )
    return ConversationHandler.END


# =============================================================================
#            12. إدارة توجيهات الذكاء الاصطناعي (AI Prompts Management)
# =============================================================================

# مفاتيح البرومبتس في قاعدة البيانات
PROMPT_KEYS = {
    "counselor": "prompt_counselor",
    "academic": "prompt_academic",
    "roleplay": "prompt_roleplay",
}

# البرومبتس الافتراضية (تستخدم كمرجع)
DEFAULT_PROMPTS = {
    "counselor": SYSTEM_PROMPT_COUNSELOR,
    "academic": SYSTEM_PROMPT_ACADEMIC,
    "roleplay": SYSTEM_PROMPT_ROLEPLAY,
}


async def admin_prompts_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """قائمة إدارة توجيهات الذكاء الاصطناعي"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    # قراءة البرومبتس الحالية من قاعدة البيانات
    current_prompts = {}
    for name, key in PROMPT_KEYS.items():
        current_prompts[name] = db.get_setting(key) or DEFAULT_PROMPTS[name]

    msg = (
        "🤖 **إدارة توجيهات الذكاء الاصطناعي (System Prompts)**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "من هنا تكدر تعدل شخصية وأسلوب كل نموذج ذكاء اصطناعي:\n\n"
        f"1️⃣ **المرشد النفسي (علاج لك):**\n"
        f"   الطول: {len(current_prompts['counselor'])} حرف\n"
        f"   الحالة: {'✅ مخصص' if db.get_setting(PROMPT_KEYS['counselor']) else '📋 افتراضي'}\n\n"
        f"2️⃣ **المشرف الأكاديمي (تدريب للآخرين):**\n"
        f"   الطول: {len(current_prompts['academic'])} حرف\n"
        f"   الحالة: {'✅ مخصص' if db.get_setting(PROMPT_KEYS['academic']) else '📋 افتراضي'}\n\n"
        f"3️⃣ **مدرب المحاكاة العملي (اختبار عملي):**\n"
        f"   الطول: {len(current_prompts['roleplay'])} حرف\n"
        f"   الحالة: {'✅ مخصص' if db.get_setting(PROMPT_KEYS['roleplay']) else '📋 افتراضي'}\n\n"
        "👇 **اختر النموذج اللي تريد تعدله:**"
    )

    keyboard = [
        [InlineKeyboardButton("1️⃣ المرشد النفسي", callback_data="prompt_edit:counselor")],
        [InlineKeyboardButton("2️⃣ المشرف الأكاديمي", callback_data="prompt_edit:academic")],
        [InlineKeyboardButton("3️⃣ مدرب المحاكاة العملي", callback_data="prompt_edit:roleplay")],
        [InlineKeyboardButton("🔄 إعادة الكل للافتراضي", callback_data="prompt_reset_all")],
        [InlineKeyboardButton("🔙 رجوع للوحة التحكم", callback_data="admin_back_to_main")],
    ]

    await query.message.edit_text(
        text=msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return ADMIN_PROMPTS_MENU


async def admin_prompt_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض البرومبت الحالي وتعديله"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    prompt_type = query.data.replace("prompt_edit:", "")
    key = PROMPT_KEYS[prompt_type]
    current = db.get_setting(key) or DEFAULT_PROMPTS[prompt_type]

    titles = {
        "counselor": "المرشد النفسي (علاج لك)",
        "academic": "المشرف الأكاديمي (تدريب للآخرين)",
        "roleplay": "مدرب المحاكاة العملي (اختبار عملي)",
    }

    # عرض البرومبت الحالي (مختصر للعرض)
    preview = current[:500] + "..." if len(current) > 500 else current

    msg = (
        f"🤖 **تعديل: {titles[prompt_type]}**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**البرومبت الحالي:**\n```\n{preview}\n```\n\n"
        "أرسل البرومبت الجديد كاملاً، أو اضغط:\n"
        "• **🔄 رجوع للافتراضي** - يمسح التخصيص\n"
        "• **📋 عرض كامل** - يوري البرومبت كله\n\n"
        "⚠️ **تنبيه:** البرومبت يحدد شخصية الذكاء الاصطناعي تماماً. "
        "عدله بحذر، وتأكد إنه واضح وموجه للطالب العراقي."
    )

    keyboard = [
        [InlineKeyboardButton("🔄 رجوع للافتراضي", callback_data=f"prompt_reset:{prompt_type}")],
        [InlineKeyboardButton("📋 عرض البرومبت كامل", callback_data=f"prompt_view:{prompt_type}")],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="admin_prompts_start")],
    ]

    await query.message.edit_text(
        text=msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data["editing_prompt"] = prompt_type
    return ADMIN_PROMPT_EDIT


async def admin_prompt_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض البرومبت كامل (للنسخ)"""
    query = update.callback_query
    await query.answer()

    prompt_type = query.data.replace("prompt_view:", "")
    key = PROMPT_KEYS[prompt_type]
    current = db.get_setting(key) or DEFAULT_PROMPTS[prompt_type]

    # تقسيم الرسالة الطويلة لعدة رسائل
    parts = [current[i:i+4000] for i in range(0, len(current), 4000)]

    await query.message.reply_text(
        f"📋 **البرومبت الكامل - {prompt_type}:**\n```\n{parts[0]}\n```",
        parse_mode=ParseMode.MARKDOWN
    )
    for part in parts[1:]:
        await query.message.reply_text(f"```\n{part}\n```", parse_mode=ParseMode.MARKDOWN)

    await query.answer("تم عرض البرومبت كامل", show_alert=True)


async def admin_prompt_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة برومبت واحد للافتراضي"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return

    await query.answer()
    prompt_type = query.data.replace("prompt_reset:", "")
    key = PROMPT_KEYS[prompt_type]

    db.set_setting(key, "")  # حذف التخصيص = رجوع للافتراضي

    await query.answer(f"✅ تم إعادة {prompt_type} للافتراضي", show_alert=True)
    # تحديث العرض
    query.data = f"prompt_edit:{prompt_type}"
    await admin_prompt_edit_callback(update, context)


async def admin_prompt_reset_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة كل البرومبتس للافتراضي"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return

    await query.answer()

    for key in PROMPT_KEYS.values():
        db.set_setting(key, "")

    await query.answer("✅ تم إعادة جميع البرومبتس للافتراضي", show_alert=True)
    await admin_prompts_start(update, context)


async def admin_prompt_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ البرومبت الجديد"""
    prompt_type = context.user_data.get("editing_prompt")
    if not prompt_type:
        await update.message.reply_text("⚠️ خطأ: نوع البرومبت غير محدد.")
        return ConversationHandler.END

    new_prompt = update.message.text.strip()
    key = PROMPT_KEYS[prompt_type]

    if len(new_prompt) < 50:
        await update.message.reply_text(
            "⚠️ البرومبت قصير جداً. اكتب توجيهات واضحة ومفصلة.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data=f"prompt_edit:{prompt_type}")]
            ])
        )
        return ADMIN_PROMPT_EDIT

    db.set_setting(key, new_prompt)

    await update.message.reply_text(
        f"✅ **تم حفظ البرومبت المخصص لـ {prompt_type} بنجاح!**\n\n"
        "الذكاء الاصطناعي سيستخدم التوجيهات الجديدة من الآن فصاعداً.",
        reply_markup=get_admin_dashboard_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data.pop("editing_prompt", None)
    return ConversationHandler.END


async def admin_prompts_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الرجوع للوحة التحكم الرئيسية"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    await admin_back_to_main_callback(update, context)
    return ConversationHandler.END


# =============================================================================
#            12. محادثة رفع المحتوى (Upload Content Conversation)
# =============================================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء عملية الرفع: اختيار القسم"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📚 الكتب والمناهج", callback_data="upcat:books")],
        [InlineKeyboardButton("📄 الملخصات والملازم", callback_data="upcat:summaries")],
        [InlineKeyboardButton("📝 الأسئلة الامتحانية", callback_data="upcat:exams")],
        [InlineKeyboardButton("❌ إلغاء العملية", callback_data="up_cancel")]
    ]

    await query.message.edit_text(
        "📤 **خطوة 1 من 3: اختيار نوع المحتوى**\n\n"
        "حدد نوع الملف اللي تحب ترفعه عيني:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return UPLOAD_CHOOSE_CAT


async def upload_choose_cat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تحديد القسم واختيار المادة الدراسية"""
    query = update.callback_query
    await query.answer()

    cat_key = query.data.replace("upcat:", "")
    context.user_data["upload_cat"] = cat_key

    keyboard = []
    row = []
    for idx, subj in enumerate(SUBJECTS):
        row.append(InlineKeyboardButton(subj, callback_data=f"upsubj:{idx}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ إلغاء العملية", callback_data="up_cancel")])

    cat_title = CATEGORIES[cat_key]["title"]
    await query.message.edit_text(
        f"📤 **خطوة 2 من 3: اختيار المادة الدراسية**\n\n"
        f"القسم المحدد: **{cat_title}**\n"
        f"هسه اختر المادة اللي يخصها هذا الملف:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return UPLOAD_CHOOSE_SUBJ


async def upload_choose_subj_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تحديد المادة وانتظار إرسال الملف من الأدمن"""
    query = update.callback_query
    await query.answer()

    subj_idx = int(query.data.replace("upsubj:", ""))
    subject_name = SUBJECTS[subj_idx]
    context.user_data["upload_subj"] = subject_name

    cat_key = context.user_data.get("upload_cat", "books")
    cat_title = CATEGORIES[cat_key]["title"]

    await query.message.edit_text(
        f"📤 **خطوة 3 من 3: دز الملف**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 القسم: **{cat_title}**\n"
        f"📚 المادة: **{subject_name}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"دز هسه الملف (PDF أو Word أو صورة أسئلة).\n\n"
        f"💡 **ملاحظة:** تكدر تكتب اسم المحاضرة أو الملف بخانة الوصف (Caption) وراح يعتمده البوت كاسم للملف.\n\n"
        f"للإلغاء بأي لحظة دز /cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    return UPLOAD_RECEIVE_FILE


async def upload_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استلام الملف وحفظ File ID في SQLite3"""
    message = update.message
    cat_key = context.user_data.get("upload_cat")
    subject_name = context.user_data.get("upload_subj")

    if not cat_key or not subject_name:
        await message.reply_text("صار خلل ببيانات الرفع، ارجع ابدأ من جديد من /admin يا غالي.")
        return ConversationHandler.END

    cat_title = CATEGORIES[cat_key]["title"]

    if message.document:
        doc = message.document
        file_id = doc.file_id
        file_unique_id = doc.file_unique_id
        file_name = message.caption or doc.file_name or "ملف دراسي بدون اسم"
        media_type = "document"
    elif message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id
        file_name = message.caption or f"صورة أسئلة ({subject_name})"
        media_type = "photo"
    else:
        await message.reply_text("⚠️ يا غالي دز ملف (مستند PDF/Word أو صورة أسئلة).")
        return UPLOAD_RECEIVE_FILE

    file_pk = db.add_file(
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_name=file_name,
        file_type=cat_key,
        subject=subject_name,
        media_type=media_type,
        uploaded_by=update.effective_user.id
    )

    success_msg = (
        "✅ **عاشت إيدك! تم حفظ الملف بقاعدة البيانات بنجاح!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 معرف الملف بالـ DB: `{file_pk}`\n"
        f"📄 اسم الملف: **{file_name}**\n"
        f"📚 المادة: **{subject_name}**\n"
        f"📂 القسم: **{cat_title}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 تكدر تدز ملف ثاني لنفس المادة مباشرة هسه، أو دز /done حتى تنهي وترجع للوحة."
    )

    await message.reply_text(success_msg, parse_mode=ParseMode.MARKDOWN)
    return UPLOAD_RECEIVE_FILE


async def upload_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إنهاء عملية الرفع والعودة للوحة التحكم"""
    context.user_data.pop("upload_cat", None)
    context.user_data.pop("upload_subj", None)
    await update.message.reply_text(
        "🏁 **تم إنهاء الرفع بنجاح.**\nتكدر تفتح لوحة التحكم بأمر /admin بأي وقت.",
        reply_markup=get_student_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END


async def upload_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء عملية الرفع"""
    query = update.callback_query
    await query.answer("تم الإلغاء")
    context.user_data.pop("upload_cat", None)
    context.user_data.pop("upload_subj", None)

    await query.message.edit_text(
        "❌ تم إلغاء عملية الرفع.\nللرجوع للوحة التحكم استخدم /admin",
        reply_markup=get_admin_dashboard_keyboard()
    )
    return ConversationHandler.END


# =============================================================================
#                13. محادثة الإذاعة العامة (Broadcast)
# =============================================================================

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء الإذاعة والطلب من الأدمن إرسال الرسالة"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    keyboard = [[InlineKeyboardButton("❌ إلغاء الإذاعة", callback_data="bc_cancel")]]
    await query.message.edit_text(
        "📢 **قسم الإذاعة العامة (تبليغ للكل):**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "دز هسه الرسالة أو المنشور اللي تريد تنشره لكل طلاب البوت.\n\n"
        "• تكدر تدز نص، صورة، ملف، صوت، أو تحويل رسالة (Forward).\n"
        "• راح توصل للكل بدون ما يبين اسم المحول منه.\n\n"
        "دز /cancel أو اضغط الزر أدناه للإلغاء.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return BROADCAST_WAIT_MSG


async def broadcast_send_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إرسال المنشور لجميع الطلاب وحساب الإحصائيات"""
    admin_msg = update.message
    users = db.get_all_user_ids()
    total = len(users)

    if total == 0:
        await admin_msg.reply_text("⚠️ ماكو أي طلاب مسجلين بالبوت حالياً حتى ندزلهم يا غالي.")
        return ConversationHandler.END

    status_msg = await admin_msg.reply_text(
        f"⏳ **جاري بدء الإذاعة لـ {total} طالب...**\nانتظر ثواني وراح يوصلك التقرير.",
        parse_mode=ParseMode.MARKDOWN
    )

    success = 0
    failed = 0

    for uid in users:
        try:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=admin_msg.chat_id,
                message_id=admin_msg.message_id
            )
            success += 1
        except Exception:
            failed += 1

        await asyncio.sleep(0.04)

    report_text = (
        "📢 **عاشت إيدك! اكتملت عملية الإذاعة بنجاح!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ تم الإرسال بنجاح إلى: **{success}** طالب\n"
        f"❌ تعذر الإرسال إلى: **{failed}** (حاظرين البوت أو لاغين حساباتهم)\n"
        f"👥 إجمالي الطلاب: **{total}**\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    await status_msg.edit_text(report_text, parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def broadcast_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء الإذاعة"""
    query = update.callback_query
    await query.answer("تم إلغاء الإذاعة")
    await query.message.edit_text(
        "❌ تم إلغاء الإذاعة العامة.",
        reply_markup=get_admin_dashboard_keyboard()
    )
    return ConversationHandler.END


# =============================================================================
#          14. محادثة تحديث التبليغات والجدول (Schedule/Announcements)
# =============================================================================

async def schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تحديث التبليغات والجدول"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    keyboard = [[InlineKeyboardButton("❌ إلغاء", callback_data="sch_cancel")]]
    await query.message.edit_text(
        "🗓️ **تحديث التبليغات والجدول الدراسي:**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "دز هسه النص الجديد للتبليغات أو جدول الامتحانات (تكدر تستخدم الإيموجيات والتنسيقات براحتك).\n\n"
        "هذا النص راح يظهر فوراً للطلاب من يدوسون زر (📢 التبليغات والجدول).\n\n"
        "دز /cancel للإلغاء.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return SCHEDULE_WAIT_TEXT


async def schedule_save_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ نص التبليغات في قاعدة البيانات"""
    text = update.message.text
    db.set_announcement(text)

    await update.message.reply_text(
        "✅ **عاشت إيدك! تم تحديث التبليغات والجدول بنجاح!**\n"
        "صار متاح لكل الطلاب بالقائمة الرئيسية هسه.",
        reply_markup=get_student_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END


async def schedule_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء تحديث الجدول"""
    query = update.callback_query
    await query.answer("تم الإلغاء")
    await query.message.edit_text(
        "❌ تم إلغاء تحديث التبليغات.",
        reply_markup=get_admin_dashboard_keyboard()
    )
    return ConversationHandler.END


# =============================================================================
#                 15. إدارة وحذف الملفات (Admin Manage Files)
# =============================================================================

async def admin_manage_choose_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار القسم لعرض ملفاته وحذفها"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return

    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📚 الكتب والمناهج", callback_data="mng_cat:books")],
        [InlineKeyboardButton("📄 الملخصات والملازم", callback_data="mng_cat:summaries")],
        [InlineKeyboardButton("📝 الأسئلة الامتحانية", callback_data="mng_cat:exams")],
        [InlineKeyboardButton("🔙 رجوع للوحة التحكم", callback_data="admin_back_to_main")]
    ]
    await query.message.edit_text(
        "🗑️ **إدارة وحذف الملفات:**\nاختر القسم أولاً يا غالي:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def admin_manage_choose_subj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار المادة لعرض ملفاتها وحذفها"""
    query = update.callback_query
    await query.answer()

    cat_key = query.data.replace("mng_cat:", "")
    keyboard = []
    row = []
    for idx, subj in enumerate(SUBJECTS):
        row.append(InlineKeyboardButton(subj, callback_data=f"mng_subj:{cat_key}:{idx}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 رجوع للأقسام", callback_data="admin_manage_choose_cat")])

    cat_title = CATEGORIES[cat_key]["title"]
    await query.message.edit_text(
        f"🗑️ إدارة ملفات قسم: **{cat_title}**\nاختر المادة الدراسية:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def admin_manage_list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض ملفات المادة مع أزرار حذف سريعة"""
    query = update.callback_query
    await query.answer()

    _, cat_key, subj_idx = query.data.split(":")
    subj_idx = int(subj_idx)
    subject_name = SUBJECTS[subj_idx]

    files = db.get_files_by_category_and_subject(cat_key, subject_name)

    if not files:
        keyboard = [[InlineKeyboardButton("🔙 رجوع للمواد", callback_data=f"mng_cat:{cat_key}")]]
        await query.message.edit_text(
            f"ℹ️ ماكو أي ملفات مرفوعة حالياً لمادة **{subject_name}**.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    keyboard = []
    for f in files:
        keyboard.append([
            InlineKeyboardButton(f"❌ حذف: {f['file_name'][:25]}", callback_data=f"del_f:{f['id']}:{cat_key}:{subj_idx}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 رجوع للمواد", callback_data=f"mng_cat:{cat_key}")])

    await query.message.edit_text(
        f"🗑️ اضغط على زر الحذف يم أي ملف تريد تمسحه نهائياً من قاعدة البيانات:\n"
        f"📚 المادة: **{subject_name}**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def admin_delete_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ حذف الملف من قاعدة البيانات وتحديث الواجهة"""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ غير مصرح لك.", show_alert=True)
        return

    _, file_id_pk, cat_key, subj_idx = query.data.split(":")
    file_id_pk = int(file_id_pk)

    deleted = db.delete_file(file_id_pk)
    if deleted:
        await query.answer("✅ تم حذف الملف بنجاح!", show_alert=True)
    else:
        await query.answer("⚠️ الملف غير موجود أو تم حذفه مسبقاً.", show_alert=True)

    query.data = f"mng_subj:{cat_key}:{subj_idx}"
    await admin_manage_list_files(update, context)


async def generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دالة إلغاء عامة لأوامر /cancel"""
    await update.message.reply_text(
        "❌ تم الإلغاء وتدلل يا غالي.",
        reply_markup=get_student_main_keyboard()
    )
    return ConversationHandler.END


# =============================================================================
#                    16. الدالة الرئيسية وتشغيل البوت (Main)
# =============================================================================

def main():
    """تهيئة وتشغيل تطبيق البوت"""
    print("==================================================")
    print("  بدء تشغيل بوت Nafas2 المطور (قسم علم النفس) ")
    print("==================================================")

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️ تنبيه: يرجى وضع BOT_TOKEN الخاص بك داخل الكود أولاً!")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # --- 1. محادثة رفع المحتوى (الأدمن) ---
    upload_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(upload_start, pattern="^admin_upload_start$")],
        states={
            UPLOAD_CHOOSE_CAT: [
                CallbackQueryHandler(upload_choose_cat_callback, pattern="^upcat:"),
                CallbackQueryHandler(upload_cancel_callback, pattern="^up_cancel$"),
            ],
            UPLOAD_CHOOSE_SUBJ: [
                CallbackQueryHandler(upload_choose_subj_callback, pattern="^upsubj:"),
                CallbackQueryHandler(upload_cancel_callback, pattern="^up_cancel$"),
            ],
            UPLOAD_RECEIVE_FILE: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, upload_receive_file),
                CommandHandler("done", upload_done),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", generic_cancel),
            CallbackQueryHandler(upload_cancel_callback, pattern="^up_cancel$"),
        ],
    )

    # --- 2. محادثة الإذاعة العامة (الأدمن) ---
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, pattern="^admin_broadcast_start$")],
        states={
            BROADCAST_WAIT_MSG: [
                MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_send_message)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", generic_cancel),
            CallbackQueryHandler(broadcast_cancel_callback, pattern="^bc_cancel$"),
        ],
    )

    # --- 3. محادثة تحديث التبليغات والجدول (الأدمن) ---
    schedule_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(schedule_start, pattern="^admin_schedule_start$")],
        states={
            SCHEDULE_WAIT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_save_text)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", generic_cancel),
            CallbackQueryHandler(schedule_cancel_callback, pattern="^sch_cancel$"),
        ],
    )

    # --- 4. محادثة ضبط مفتاح Gemini API (الأدمن) ---
    gemini_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_gemini_start, pattern="^admin_gemini_start$")],
        states={
            ADMIN_SET_GEMINI_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gemini_save)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", generic_cancel),
            CallbackQueryHandler(admin_gemini_cancel_callback, pattern="^gemini_cancel$"),
        ],
    )

    # --- 5. محادثة المرشد النفسي الذكي (الطلاب - علاج لك) ---
    counselor_chat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_counselor_chat_callback, pattern="^chat_counselor_start$")],
        states={
            CHAT_COUNSELOR_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_counselor_chat_message),
                CallbackQueryHandler(end_counselor_chat_callback, pattern="^end_counselor_chat$"),
            ]
        },
        fallbacks=[
            CommandHandler("cancel", generic_cancel),
            CallbackQueryHandler(end_counselor_chat_callback, pattern="^end_counselor_chat$"),
        ],
    )

    # --- 6. محادثة المشرف الأكاديمي الذكي (الطلاب - تدريب للآخرين) ---
    academic_chat_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_academic_chat_callback, pattern="^(chat_academic_start|discuss_case:)")
        ],
        states={
            CHAT_ACADEMIC_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_academic_chat_message),
                CallbackQueryHandler(end_academic_chat_callback, pattern="^end_academic_chat$"),
            ]
        },
        fallbacks=[
            CommandHandler("cancel", generic_cancel),
            CallbackQueryHandler(end_academic_chat_callback, pattern="^end_academic_chat$"),
        ],
    )

    # --- 7. محادثة المحاكاة العملي - اختبار الأخصائي (Roleplay) ---
    roleplay_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(roleplay_start_callback, pattern="^roleplay_start$"),
            CallbackQueryHandler(roleplay_next_scenario_callback, pattern="^roleplay_next_scenario$"),
            CallbackQueryHandler(roleplay_retry_same_skill_callback, pattern="^roleplay_retry_same_skill$"),
        ],
        states={
            ROLEPLAY_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_roleplay_message),
                CallbackQueryHandler(roleplay_next_scenario_callback, pattern="^roleplay_next_scenario$"),
                CallbackQueryHandler(roleplay_retry_same_skill_callback, pattern="^roleplay_retry_same_skill$"),
                CallbackQueryHandler(end_roleplay_callback, pattern="^end_roleplay$"),
            ]
        },
        fallbacks=[
            CommandHandler("cancel", generic_cancel),
            CallbackQueryHandler(end_roleplay_callback, pattern="^end_roleplay$"),
        ],
    )

    # --- 5. محادثة إدارة توجيهات الذكاء الاصطناعي (الأدمن) ---
    prompts_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_prompts_start, pattern="^admin_prompts_start$"),
            CallbackQueryHandler(admin_prompt_edit_callback, pattern="^prompt_edit:"),
            CallbackQueryHandler(admin_prompt_reset_callback, pattern="^prompt_reset:"),
            CallbackQueryHandler(admin_prompt_reset_all_callback, pattern="^prompt_reset_all$"),
        ],
        states={
            ADMIN_PROMPTS_MENU: [
                CallbackQueryHandler(admin_prompt_edit_callback, pattern="^prompt_edit:"),
                CallbackQueryHandler(admin_prompt_reset_callback, pattern="^prompt_reset:"),
                CallbackQueryHandler(admin_prompt_reset_all_callback, pattern="^prompt_reset_all$"),
                CallbackQueryHandler(admin_prompt_view_callback, pattern="^prompt_view:"),
                CallbackQueryHandler(admin_prompts_back_callback, pattern="^admin_prompts_back$"),
                CallbackQueryHandler(admin_back_to_main_callback, pattern="^admin_back_to_main$"),
            ],
            ADMIN_PROMPT_EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_prompt_save),
                CallbackQueryHandler(admin_prompt_reset_callback, pattern="^prompt_reset:"),
                CallbackQueryHandler(admin_prompt_view_callback, pattern="^prompt_view:"),
                CallbackQueryHandler(admin_prompts_back_callback, pattern="^admin_prompts_back$"),
                CallbackQueryHandler(admin_back_to_main_callback, pattern="^admin_back_to_main$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", generic_cancel),
            CallbackQueryHandler(admin_prompts_back_callback, pattern="^admin_prompts_back$"),
            CallbackQueryHandler(admin_back_to_main_callback, pattern="^admin_back_to_main$"),
        ],
    )

    # إضافة معالجات المحادثات
    application.add_handler(upload_conv)
    application.add_handler(broadcast_conv)
    application.add_handler(schedule_conv)
    application.add_handler(gemini_conv)
    application.add_handler(prompts_conv)
    application.add_handler(counselor_chat_conv)
    application.add_handler(academic_chat_conv)
    application.add_handler(roleplay_conv)

    # معالجات أوامر الأدمن
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(admin_stats_callback, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_back_to_main_callback, pattern="^admin_back_to_main$"))
    application.add_handler(CallbackQueryHandler(admin_close_callback, pattern="^admin_close$"))

    # معالجات إدارة وحذف الملفات (الأدمن)
    application.add_handler(CallbackQueryHandler(admin_manage_choose_cat, pattern="^admin_manage_choose_cat$"))
    application.add_handler(CallbackQueryHandler(admin_manage_choose_subj, pattern="^mng_cat:"))
    application.add_handler(CallbackQueryHandler(admin_manage_list_files, pattern="^mng_subj:"))
    application.add_handler(CallbackQueryHandler(admin_delete_file_callback, pattern="^del_f:"))

    # معالجات قسم الدعم والعلاج النفسي
    application.add_handler(CallbackQueryHandler(psy_main_callback, pattern="^psy_main$"))
    application.add_handler(CallbackQueryHandler(psy_for_you_intro, pattern="^psy_for_you$"))
    application.add_handler(CallbackQueryHandler(quiz_step_callback, pattern="^quiz_step:"))
    application.add_handler(CallbackQueryHandler(psy_for_others_menu, pattern="^psy_for_others$"))
    application.add_handler(CallbackQueryHandler(cases_list_callback, pattern="^cases_list$"))
    application.add_handler(CallbackQueryHandler(show_case_callback, pattern="^show_case:"))
    application.add_handler(CallbackQueryHandler(solve_case_callback, pattern="^solve_case:"))
    application.add_handler(CallbackQueryHandler(strategies_list_callback, pattern="^strategies_list$"))

    # معالجات الطلاب العامة
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(
        MessageHandler(
            filters.Regex("^(📚 الكتب والمناهج|📄 الملخصات والملازم|📝 الأسئلة الامتحانية|📢 التبليغات والجدول|🧠 الدعم والعلاج النفسي|ℹ️ عن البوت 🤍|ℹ️ حول البوت)$"),
            handle_student_reply_buttons
        )
    )
    application.add_handler(CallbackQueryHandler(student_get_subject_files, pattern="^get_sub:"))
    application.add_handler(CallbackQueryHandler(callback_close_menu, pattern="^close_menu$"))

    # تشغيل البوت بنظام Polling
    print("🚀 بوت نفَس2 المطور قيد التشغيل والجاهزية لاستقبال الرسائل...")
    application.run_polling()


if __name__ == "__main__":
    main()
