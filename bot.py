"""
=============================================================================
بوت Nafas2 🧠 - المنصة الأكاديمية والدعم النفسي لقسم علم النفس (المرحلة الثانية)
=============================================================================
المكتبة المستخدمة: python-telegram-bot (v20+ Async)
قاعدة البيانات: PostgreSQL (Supabase)
الذكاء الاصطناعي: Google Gemini API (لهجة عراقية داعمة وأكاديمية)
=============================================================================
"""

import sys
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
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

# استيراد اختياري لـ google-generativeai (يُستخدم فقط في generate_dynamic_case)
try:
    import google.generativeai as genai
    _HAS_GENAI = True
except ImportError:
    _HAS_GENAI = False

# توكن البوت الخاص بك (يقرأ من متغير البيئة)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# معرف الأدمن (Telegram User ID)
ADMIN_ID = int(os.getenv("ADMIN_ID", "8993961580"))

# مفتاح Google Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if _HAS_GENAI:
    genai.configure(api_key=GEMINI_API_KEY)

# نموذج الذكاء الاصطناعي الأسرع والأخف استجابة
GEMINI_MODEL = "gemini-3.1-flash-lite"

# رابط قاعدة بيانات PostgreSQL (Supabase)
DATABASE_URL = os.getenv("DATABASE_URL", "")

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
        "desc": "تفضلوا المصادر والكتب المنهجية المعتمدة لمرحلتنا 📖:"
    },
    "summaries": {
        "title": "📄 الملخصات والملازم",
        "desc": "هاي أحدث الملازم والتلخيصات مرتبة ومجهزة لإفادتكم 📝:"
    },
    "exams": {
        "title": "📝 الأسئلة الامتحانية",
        "desc": "نماذج الأسئلة الامتحانية (شهريات وفاينل) حتى تراجعون منها وتضمنون النجاح 🎯:"
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
CLINICAL_PRACTICE_STATE = range(1)


def safe_md(text: str) -> str:
    """هروب من الرموز الخاصة بـ Markdown حتى ما تكسر الرسائل (مهم للأسماء والملفات)"""
    for ch in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(ch, f'\\{ch}')
    return text


# =============================================================================
#                     2. إدارة قاعدة البيانات (PostgreSQL via Supabase)
# =============================================================================

class DatabaseManager:
    """فئة إدارة الاتصال وتنفيذ استعلامات PostgreSQL"""

    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
        self.init_db()

    def get_connection(self):
        conn = psycopg2.connect(self.db_url, cursor_factory=RealDictCursor, sslmode='require')
        return conn

    def init_db(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
        except Exception as e:
            print(f"⚠️ قاعدة البيانات غير متاحة: {e}")
            return

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
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
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS psychological_assessments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                score INTEGER,
                category TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("SELECT COUNT(*) FROM announcements")
        row = cursor.fetchone()
        if row and list(row.values())[0] == 0:
            default_text = (
                "📣 **آخر تبليغات القاعة والجدول الدراسي للمرحلة الثانية 🗓️:**\n\n"
                "أهلاً بكم زملاءنا وأعزاءنا طلبة قسم علم النفس - جامعة كربلاء (المرحلة الثانية)! 🧠✨\n\n"
                "سوف يتم نشر أي تبليغات رسمية بخصوص المحاضرات، القاعات، أو الجداول الامتحانية هنا بتحديث مستمر.\n\n"
                "نتمنى لكم دوام التوفيق والنجاح والتفوق يا رب! 🤍"
            )
            cursor.execute("INSERT INTO announcements (text) VALUES (%s)", (default_text,))

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("تم التحقق من قاعدة البيانات وإنشاء الجداول بنجاح.")

    def register_user(self, user_id: int, username: Optional[str], full_name: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (%s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name;
        """, (user_id, username, full_name))
        conn.commit()
        cursor.close()
        conn.close()

    def get_all_user_ids(self) -> List[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        result = [row["user_id"] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return result

    def get_users_count(self) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        row = cursor.fetchone()
        result = list(row.values())[0] if row else 0
        cursor.close()
        conn.close()
        return result

    def add_file(self, file_id: str, file_unique_id: str, file_name: str,
                 file_type: str, subject: str, media_type: str, uploaded_by: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO files (file_id, file_unique_id, file_name, file_type, subject, media_type, uploaded_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (file_id, file_unique_id, file_name, file_type, subject, media_type, uploaded_by))
        row = cursor.fetchone()
        file_pk = list(row.values())[0] if row else 0
        conn.commit()
        cursor.close()
        conn.close()
        return file_pk

    def get_files_by_category_and_subject(self, file_type: str, subject: str) -> List[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM files
            WHERE file_type = %s AND subject = %s
            ORDER BY id ASC
        """, (file_type, subject))
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return result

    def get_files_count(self) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM files")
        row = cursor.fetchone()
        result = list(row.values())[0] if row else 0
        cursor.close()
        conn.close()
        return result

    def get_files_statistics(self) -> Dict[str, Any]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT file_type, COUNT(*) as cnt FROM files GROUP BY file_type")
        cats = {row["file_type"]: row["cnt"] for row in cursor.fetchall()}
        cursor.execute("SELECT subject, COUNT(*) as cnt FROM files GROUP BY subject")
        subjs = {row["subject"]: row["cnt"] for row in cursor.fetchall()}
        cursor.close()
        conn.close()
        return {"categories": cats, "subjects": subjs}

    def delete_file(self, file_pk: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE id = %s", (file_pk,))
        conn.commit()
        deleted = cursor.rowcount > 0
        cursor.close()
        conn.close()
        return deleted

    def get_latest_announcement(self) -> str:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT text FROM announcements ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row["text"] if row else "حالياً ماكو تبليغات منشورة.. أول ما ينزل شي جديد يخص مرحلتنا راح ينزل هنا فوراً 🔔"

    def set_announcement(self, text: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO announcements (text) VALUES (%s)", (text,))
        conn.commit()
        cursor.close()
        conn.close()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM bot_settings WHERE key = %s", (key,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bot_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """, (key, value))
        conn.commit()
        cursor.close()
        conn.close()

    def save_assessment(self, user_id: int, score: int, category: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO psychological_assessments (user_id, score, category)
            VALUES (%s, %s, %s)
        """, (user_id, score, category))
        conn.commit()
        cursor.close()
        conn.close()

    def get_latest_assessment(self, user_id: int) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM psychological_assessments
            WHERE user_id = %s
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result


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


def _resolve_gemini_key() -> str:
    """مفتاح Gemini من الإعدادات أو متغير البيئة"""
    api_key = GEMINI_API_KEY
    try:
        db_setting = db.get_setting("gemini_api_key")
        if db_setting:
            api_key = db_setting
    except Exception:
        pass
    return api_key or ""


async def call_gemini_api(
    user_message: str,
    system_instruction: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    max_history: int = 4,
    max_output_tokens: int = 450,
    temperature: float = 0.7,
) -> str:
    """استدعاء نموذج Gemini الرسمي عبر اتصال دائم وسريع باللغة واللهجة الموجهة"""
    api_key = _resolve_gemini_key()

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
        for turn in chat_history[-max_history:]:
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
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
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
أنت 'مرشد Nafas2' - أخصائي ومرشد نفسي عراقي لطيف، ذكي، حكيم وداعم جداً.
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
أنت 'دكتور Nafas2' - بروفيسور وخبير نفسي أكاديمي متمكن في علم النفس العيادي والإرشادي.
تتحدث باللغة العربية مع لمسة عراقية أكاديمية لطيفة، بيضاء ومشجعة جداً للطلبة (تستخدم أسلوب الأستاذ المشرف الذكي: يا دكتور المستقبل، يا زميلنا العزيز، عاشت إيدك، فكرة سريرية ممتازة، تدلل).
أنت تتحدث مع طالب/طالبة في قسم علم النفس - المرحلة الثانية.

مهمتك وأسلوبك:
1. تدريب الطالب على التفكير السريري السليم والتشخيص الفارق (Differential Diagnosis وفق محكات DSM-5).
2. صياغة الحالات وفهم الآليات النفسية (Case Formulation) واستراتيجيات العلاج المعرفي السلوكي (CBT)، العلاج العقلاني الانفعالي (REBT)، والعلاج بالقبول والالتزام (ACT).
3. شرح المفاهيم الأكاديمية الصعبة بأسلوب يجمع بين العمق العلمي والبساطة الممتعة وربطها بأمثلة تطبيقية واقعية.
4. حفز الطالب، ناقشه بأسئلة تشخيصية تفاعلية، وساعده يطور مهاراته كأخصائي نفسي محترف.
5. أجب بنقاط أكاديمية مركزة ومباشرة دون إطالة مفرطة حتى يستوعب الطالب الشرح بسهولة وسرعة.
"""

# البرومبت التوجيهي لمدرب التدريب السريري (Roleplay Evaluator) - تعليمي خطوة بخطوة، سقراطي، ممتع
SYSTEM_PROMPT_ROLEPLAY = """
أنت 'مُدَرِّب Nafas2 العَمَلِي' - مشرف سريري عراقي خبير، **صبور، محفز، ومعلم حقيقي**. اللي أمامك **طالب مبتدئ (مرحلة ثانية)** ما يعرف يعالج بعد.
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
        [KeyboardButton("🧪 الممارسة السريرية"), KeyboardButton("ℹ️ عن البوت 🤍")]
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
            InlineKeyboardButton("🧪 الممارسة السريرية", callback_data="clinical_practice_start"),
            InlineKeyboardButton("🎓 حالات سريرية", callback_data="cases_list"),
        ],
        [
            InlineKeyboardButton("💬 المرشد النفسي", callback_data="chat_counselor_start"),
            InlineKeyboardButton("🧠 المشرف الأكاديمي", callback_data="chat_academic_start"),
        ],
        [
            InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="close_menu"),
        ],
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
    try:
        db.register_user(user.id, user.username, full_name)
    except Exception:
        pass

    welcome_text = (
        f"يا هلا وناغمة بيكم زملاءنا وأعزاءنا بقسم علم النفس - جامعة كربلاء (المرحلة الثانية)! 🧠✨\n\n"
        f"هذا البوت بيتكم الصغير المخصص حتى يجمعنا، ويسهل عليكم الوصول لكل الكتب والملازم والأسئلة الخاصة بمرحلتنا بضغطة زر واحدة.\n\n"
        f"تفضلوا واختاروا القسم اللي تحتاجوه من القائمة أدناه 👇🌸"
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
        msg = cat_info['desc']
        await update.message.reply_text(
            text=msg,
            reply_markup=get_subjects_inline_keyboard("books", prefix="get_sub")
        )

    elif text == "📄 الملخصات والملازم":
        cat_info = CATEGORIES["summaries"]
        msg = cat_info['desc']
        await update.message.reply_text(
            text=msg,
            reply_markup=get_subjects_inline_keyboard("summaries", prefix="get_sub")
        )

    elif text == "📝 الأسئلة الامتحانية":
        cat_info = CATEGORIES["exams"]
        msg = cat_info['desc']
        await update.message.reply_text(
            text=msg,
            reply_markup=get_subjects_inline_keyboard("exams", prefix="get_sub")
        )

    elif text == "📢 التبليغات والجدول":
        try:
            announcement = db.get_latest_announcement()
        except Exception:
            announcement = "⚠️ التبليغات غير متاحة حالياً."
        msg = (
            "📣 **آخر تبليغات القاعة والجدول الدراسي للمرحلة الثانية 🗓️:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{announcement}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🧠 نفاس2 - وياكم خطوة بخطوة 🤍"
        )
        await update.message.reply_text(text=msg, parse_mode=ParseMode.MARKDOWN)

    elif text in ["ℹ️ عن البوت 🤍", "ℹ️ حول البوت"]:
        about_text = (
            "🤍 **عن البوت ℹ️**\n\n"
            "مساحة طلابية خدمية مخصصة لتسهيل رحلتنا الدراسية في قسم علم النفس / جامعة كربلاء - المرحلة الثانية 🎓✨\n\n"
            "✨ **شنو يقدملكم البوت؟**\n"
            "• أرشفة كاملة للكتب والمناهج المعتمدة.\n"
            "• توفير الملازم والتلخيصات المهمة.\n"
            "• نماذج أسئلة شهرية ونهائية سابقة.\n"
            "• تبليغات المحاضرات وجدول الامتحانات أول بأول.\n"
            "• قسم الدعم النفسي بمصادر إثرائية وتمارين عملية.\n\n"
            "كل التوفيق والنجاح يا دكاترة وأخصائيي المستقبل! 🌟🤍"
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

    try:
        files = db.get_files_by_category_and_subject(cat_key, subject_name)
    except Exception:
        files = None

    if files is None:
        await query.message.reply_text("⚠️ الملفات غير متاحة حالياً.")
        return

    if not files:
        no_files_msg = (
            f"حالياً هذا القسم فارغ، وأول ما يتوفر شي جديد يخص مرحلتنا راح نرفعه هنا فوراً 🔔"
        )
        await query.message.reply_text(text=no_files_msg, parse_mode=ParseMode.MARKDOWN)
        return

    await query.message.reply_text(
        f"📂 **تفضلوا، هاي هي الملفات المتوفرة لمادة ({subject_name}):**\n"
        f"🏷️ القسم: {cat_info['title']}\n"
        f"📊 عدد الملفات: {len(files)} ملف 📄\n\n"
        f"انتظر ثواني بس ويوصلنك... ⏳",
        parse_mode=ParseMode.MARKDOWN
    )

    for f in files:
        caption = (
            f"تفضلوا الملف المطلوب 📥.. كل التوفيق والنجاح الدائم لأحلى أطباء ونفسانيين بالمستقبل! 🌟\n\n"
            f"📄 **{safe_md(f['file_name'])}**\n"
            f"🏷️ المادة: {f['subject']}\n"
            f"📂 القسم: {cat_info['title']}\n"
            f"━━━━━━━━━━━━\n"
            f"🧠 نفاس2 - علم النفس - جامعة كربلاء (المرحلة الثانية)"
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
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📚 تحميل {cat_info['title'].split()[1]} ثاني", callback_data=f"{cat_key}_menu")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="close_menu")]
        ]),
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


async def books_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة لقائمة الكتب والمناهج (زر تحميل كتاب ثاني)"""
    query = update.callback_query
    await query.answer()

    cat_info = CATEGORIES["books"]
    msg = cat_info['desc']

    await query.message.edit_text(
        text=msg,
        reply_markup=get_subjects_inline_keyboard("books", prefix="get_sub"),
        parse_mode=ParseMode.MARKDOWN
    )


async def summaries_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة لقائمة الملخصات والملازم"""
    query = update.callback_query
    await query.answer()

    cat_info = CATEGORIES["summaries"]
    msg = cat_info['desc']

    await query.message.edit_text(
        text=msg,
        reply_markup=get_subjects_inline_keyboard("summaries", prefix="get_sub"),
        parse_mode=ParseMode.MARKDOWN
    )


async def exams_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة لقائمة الأسئلة الامتحانية"""
    query = update.callback_query
    await query.answer()

    cat_info = CATEGORIES["exams"]
    msg = cat_info['desc']

    await query.message.edit_text(
        text=msg,
        reply_markup=get_subjects_inline_keyboard("exams", prefix="get_sub"),
        parse_mode=ParseMode.MARKDOWN
    )


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


async def quick_exercises_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تمارين استرخاء سريعة ومفيدة"""
    query = update.callback_query
    await query.answer()

    exercises_text = (
        "🧘 **تمارين استرخاء سريعة — اختر ما يناسبك الآن:**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🫁 **1. تنفس 4-7-8 (للقلق والتوتر الحاد):**\n"
        "   شهيق من الأنف 4 ثوانٍ → احبس 7 ثوانٍ → زفير من الفم 8 ثوانٍ\n"
        "   كرر 4 مرات. يهدئ الجهاز العصبي خلال دقيقة.\n\n"
        "👣 **2. تأريض 5-4-3-2-1 (للنوبات والانهيار):**\n"
        "   لاحظ حولك: 5 أشياء تشوفها، 4 تلمسها، 3 تسمعها، 2 تشمها، 1 تتذوقها\n"
        "   يرجع عقلك للواقع فوراً.\n\n"
        "💪 **3. استرخاء عضلي تدريجي (للجسم المتوتر):**\n"
        "   شد عضلات القدمين 5 ثوانٍ → أرخِ دفعة وحدة → أحس الفرق\n"
        "   اصعد: ساقين، بطن، يدين، كتفين، وجه. ٣٠ ثانية لكل منطقة.\n\n"
        "🧠 **4. تفريغ الدماغ (قبل النوم/الامتحان):**\n"
        "   خذ ورقة واكتب كل شي براسك (مهام، مخاوف، أفكار) بدون تصفية\n"
        "   خلص الورقة → طوّيها → حطها جنب → عقلك افتقد المساحة.\n\n"
        "☀️ **5. إعادة تأطير سريعة (للتفكير السلبي):**\n"
        "   الفكرة: (ما أقدر / راح أفشل)\n"
        "   اسأل: (شنو الدليل؟ لو زميلي مكاني شنو أقول له؟ شنو خطوة وحدة أقدر أسويها؟)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 **نصيحة:** التمرين اللي تحس إنه صعب = هو اللي تحتاجه أكثر.\n"
        "جرب واحد هسه ولاحظ الفرق خلال ٢-٣ دقائق 🤍"
    )

    keyboard = [
        [InlineKeyboardButton("💬 احچي ويه المرشد الذكي", callback_data="chat_counselor_start")],
        [InlineKeyboardButton("🔙 رجوع للمركز", callback_data="psy_main")]
    ]

    await query.message.edit_text(
        text=exercises_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def psy_resources_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مصادر إثرائية نفسية للطالب والأخصائي"""
    query = update.callback_query
    await query.answer()

    resources_text = (
        "📚 **مصادر إثرائية نفسية مختارة لطلبة علم النفس:**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📖 **كتب عربية أساسية (متوفرة مجاناً/مكتبة الجامعة):**\n"
        "• *العلاج المعرفي السلوكي: الأساسيات والتطبيقات* — جوديث بيك\n"
        "• *مهارات المقابلة الإرشادية* — كارل روجرز\n"
        "• *القلق والرهاب: فهم وعلاج* — ديفيد بارلو\n"
        "• *الاكتئاب: النظريات والعلاج* — آرون بيك\n\n"
        "🎯 **مقاييس نفسية معيارية (للدراسة والتدريب):**\n"
        "• **PHQ-9** — فحص الاكتئاب (9 فقرات)\n"
        "• **GAD-7** — فحص القلق المعمم (7 فقرات)\n"
        "• **PSS-10** — مقياس الضغط المدرك (10 فقرات)\n"
        "• **DASS-21** — اكتئاب، قلق، ضغط (21 فقرة)\n"
        "• **SCL-90-R** — قائمة أعراض شاملة\n\n"
        "🛠️ **أدوات عملية للأخصائي المبتدئ:**\n"
        "• **سجل الأفكار التلقائية** — نموذج CBT أساسي\n"
        "• **ورقة تجربة سلوكية** — لاختبار المعتقدات\n"
        "• **جدول الأنشطة (BAS)** — للتنشيط السلوكي\n"
        "• **مقياس الأهداف (GAS)** — لتقييم تقدم العميل\n"
        "• **خطة منع الانتكاس** — نموذج منظم\n\n"
        "🌐 **مواقع ومصادر موثوقة:**\n"
        "• **APA.org** — جمعية علم النفس الأمريكية\n"
        "• **BeckInstitute.org** — معهد بيك للعلاج المعرفي\n"
        "• **PsychologyTools.com** — أوراق عمل CBT مجانية\n"
        "• **GetSelfHelp.co.uk** — أدوات مساعدة ذاتية\n\n"
        "💡 **المشرف الأكاديمي الذكي** يقدر يشرحلك أي مقياس أو أداة بالتفصيل!"
    )

    keyboard = [
        [InlineKeyboardButton("💬 اسأل المشرف الأكاديمي عن أي أداة", callback_data="chat_academic_start")],
        [InlineKeyboardButton("🔙 رجوع للمركز", callback_data="psy_main")]
    ]

    await query.message.edit_text(
        text=resources_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def psy_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للواجهة الرئيسية لقسم الدعم النفسي"""
    query = update.callback_query
    await query.answer()

    msg = (
        "🧠 **مركز Nafas2 للدعم النفسي والتدريب السريري** 🤍\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "مساحتك الآمنة والمتخصصة لكل ما يخص الصحة النفسية والتدريب العملي:\n\n"
        "🧪 **لصحتك النفسية:**\n"
        "• **تقييم سريع** — 4 أسئلة تحدد فئتك وتقدم تمارين مخصصة\n"
        "• **مرشد ذكي** — دردشة فورية مع أخصائي عراقي داعم 24/7\n"
        "• **تمارين سريعة** — تنفس، تأريض، استرخاء في دقيقة\n\n"
        "🎓 **لتدريبك العملي (أخصائي المستقبل):**\n"
        "• **حالات سريرية** — 6 حالات متنوعة للتدريب التشخيصي\n"
        "• **استراتيجيات علاجية** — CBT, REBT, BA, و更多\n"
        "• **المشرف الأكاديمي** — نقاش حالات واستشارات متخصصة\n"
        "• **الممارسة السريرية** — محاكاة تفاعلية مع مرضى ذكيين\n\n"
        "💡 **كل أداة مصممة لطالب علم نفس عراقي — قريب، عملي، غير نمطي**"
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
        f"💬 **تريد تفضفض أو تسولف ويه مرشدك النفسي الذكي (Nafas2)?**\n"
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
        "💬 **المرشد النفسي الذكي (Nafas2) وياك هسه 🤍**\n"
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
        "title": "📋 الحالة 1: قلق الامتحان والأداء الأكاديمي",
        "brief": "طالب جامعي — خوف مفرط من الامتحانات مع تسويف وأعراض جسدية.",
        "details": (
            "📋 **دراسة حالة سريرية — Case Study #1**\n\n"
            "👤 **العميل:** شاب (20 سنة) — طالب جامعي\n"
            "⚠️ **الشكوى:** قلق امتحان شديد، تسويف، أعراض جسدية متعبة\n\n"
            "🔍 **الأعراض:**\n"
            "• قبل الامتحان بأيام: خفقان، برودة بالأطراف، اضطراب بالقولون\n"
            "• معرفياً: أفكار مشوهة — (إذا ما طلعت امتياز راح أفشل بحياتي)\n"
            "• سلوكياً: يماطل بالدراسة للّحظات الأخيرة، درجاته تتراجع رغم ذكائه\n\n"
            "❓ **سؤال التدريب:** شنو تشخيصك الأولي؟ وشنو فنيات CBT اللي راح تقترحها؟"
        ),
        "solution": (
            "💡 **التحليل والخطة العلاجية:**\n\n"
            "🎯 **التشخيص:** قلق الأداء والامتحان (Performance Anxiety) متداخل مع كمالية عُصابية\n\n"
            "🛠️ **الخطة — CBT:**\n"
            "1. **إعادة الهيكلة المعرفية:** تفكيك تشوه 'الكل أو لا شيء'\n"
            "2. **التنفس البطني:** تدريب الحجابي لتقليل نشاط السمبثاوي\n"
            "3. **التعرض التدريجي:** تمثيل أجواء الامتحان وحل نماذج بوقت محدد\n"
            "4. **إدارة الوقت:** تفكيك المادة لأجزاء صغيرة لمنع التسويف"
        )
    },
    "case_2": {
        "title": "📋 الحالة 2: الاكتئاب الخفيف والتثبيط السلوكي",
        "brief": "طالبة (21 سنة) — فقدان الشغف، عزلة، ثقل في المهام اليومية.",
        "details": (
            "📋 **دراسة حالة سريرية — Case Study #2**\n\n"
            "👤 **العميلة:** شابة (21 سنة) — طالبة بالمرحلة الثانية\n"
            "⚠️ **الشكوى:** فقدان المتعة (Anhedonia)، انخفاض الطاقة، عزلة\n\n"
            "🔍 **الأعراض:**\n"
            "• بدأت بعد تراجع طفيف بالمعدل — شعرت بذنب شديد ويأس\n"
            "• تقضي وقتها بالسرير تتصفح الهاتف بدون هدف، تتغيب عن المحاضرات\n"
            "• أفكار سلبية: (أنا صايرة عبء، ماكو فايدة من التعب، كل شي باهت)\n\n"
            "❓ **سؤال التدريب:** شنو الاستراتيجية السلوكية الأولى تبدأ بيها؟"
        ),
        "solution": (
            "💡 **التحليل والخطة العلاجية:**\n\n"
            "🎯 **التشخيص:** نوبة اكتئابية خفيفة-متوسطة مع تثبيط سلوكي\n\n"
            "🛠️ **الخطة:**\n"
            "1. **التنشيط السلوكي (BA):** كسر الحلقة المفرغة (قلة نشاط ⬅️ لوم ⬅️ اكتئاب) بجدولة أنشطة بسيطة\n"
            "2. **سجل الأفكار التلقائية:** رصد الأفكار السوداوية واختبار واقعيتها\n"
            "3. **تنظيم الإيقاع:** ضبط ساعات النوم والاستيقاظ والتعرض لضوء الشمس"
        )
    },
    "case_3": {
        "title": "📋 الحالة 3: القلق الاجتماعي والخوف من الإلقاء",
        "brief": "شاب (22 سنة) — رعب من التحدث أمام القاعة أو المشاركة.",
        "details": (
            "📋 **دراسة حالة سريرية — Case Study #3**\n\n"
            "👤 **العميل:** طالب جامعي (22 سنة)\n"
            "⚠️ **الشكوى:** رعب هائل من الإلقاء (Presentation) والمشاركة أمام الطلاب\n\n"
            "🔍 **الأعراض:**\n"
            "• احمرار الوجه، رجفة بالصوت واليدين، شعور بالاختناق عند التفكير بالمشاركة\n"
            "• معرفياً: قلق من التقييم السلبي — (راح يضحكون عليّ، راح يبين إني غبي)\n"
            "• سلوكياً: يطلب إعفاءه من التقديم أو يغيب بيوم الإلقاء متحملاً خصم الدرجة\n\n"
            "❓ **سؤال التدريب:** شنو فنيات إزالة التحسس والتعرض اللي تفيده؟"
        ),
        "solution": (
            "💡 **التحليل والخطة العلاجية:**\n\n"
            "🎯 **التشخيص:** اضطراب القلق الاجتماعي — الأداء فقط (Social Anxiety - Performance)\n\n"
            "🛠️ **الخطة:**\n"
            "1. **تصحيح بؤرة الانتباه:** تحويل التركيز من الداخل للخارج\n"
            "2. **التعرض المتدرج:** مرآة ← فيديو ← صديق واحد ← مجموعة صغيرة ← القاعة\n"
            "3. **التجارب السلوكية:** اختبار الفرضية الكارثية — (هل لو سكتت 3 ثواني راح يضحكون؟)"
        )
    },
    "case_4": {
        "title": "📋 الحالة 4: الوسواس القهري (OCD) — غسل وتلوث",
        "brief": "شاب (23 سنة) — غسل يديه 30 مرة يومياً، خوف من نقل العدوى.",
        "details": (
            "📋 **دراسة حالة سريرية — Case Study #4**\n\n"
            "👤 **العميل:** شاب (23 سنة) — طالب هندسة\n"
            "⚠️ **الشكوى:** وسواس قهري بالغسل والتلوث، يستغرق ساعات يومياً\n\n"
            "🔍 **الأعراض:**\n"
            "• غسل اليدين 30 مرة باليوم، تجنب الحمامات العامة والمصافحة\n"
            "• أفكار وسواسية: (لو ما غسلت راخ مرض أهلي، إيدي ملوثة)\n"
            "• يعاني من احمرار باليدين وإرهاق شديد بسبب الغسل المفرط\n"
            "• يدرك أن وساويسه مفرطة لكن لا يقدر يوقف\n\n"
            "❓ **سؤال التدريب:** شنو الفرق بين الوسواس والخوف الطبيعي؟ وشنو الخطة؟"
        ),
        "solution": (
            "💡 **التحليل والخطة العلاجية:**\n\n"
            "🎯 **التشخيص:** اضطراب الوسواس القهري (OCD) — نوع التلوث/الغسل\n\n"
            "🛠️ **الخطة:**\n"
            "1. **ERP (التعرض مع منع الاستجابة):** التعرض للمثير (مصافحة) ومنع الغسل تدريجياً\n"
            "2. **إعادة تسمية الوساوس:** 'هذا وسواس وليس حقيقة' — فصل الفكرة عن الواقع\n"
            "3. **تدرج التعرض:** لمس مقبض باب ← مصافحة ← استخدام حمام عام ← عدم الغسل لمدة 15 دقيقة\n"
            "4. **تعليم العائلة:** دعم الأهل بتجنب التسهيلات والتعاون مع الخطة"
        )
    },
    "case_5": {
        "title": "📋 الحالة 5: اضطراب الأكل والصورة الجسدية",
        "brief": "طالبة (19 سنة) — تقييد أكل، مقارنة جسدية، خوف من السمنة.",
        "details": (
            "📋 **دراسة حالة سريرية — Case Study #5**\n\n"
            "👤 **العميلة:** طالبة (19 سنة) — مرحلة ثانية\n"
            "⚠️ **الشكوى:** تقييد شديد للأكل، مقارنة جسدية مستمرة، خوف من زيادة الوزن\n\n"
            "🔍 **الأعراض:**\n"
            "• تأكل وجبة واحدة يومياً أو أقل، تتجنب الأكل أمام الناس\n"
            "• تقيس نفسها كل ساعة، تقارن صورتها بأنستغرام باستمرار\n"
            "• أفكار: (أنا سمينة، الناس يضحكون على شكلي، ما أصلح)\n"
            "• فقدان 8 كيلو خلال 3 أشهر، اضطراب بالقولون، شعر متساقط\n\n"
            "❓ **سؤال التدريب:** شنو علامات الخطر التي تستدعي تحويل فوري لأخصائي؟"
        ),
        "solution": (
            "💡 **التحليل والخطة العلاجية:**\n\n"
            "🎯 **التشخيص:** اضطراب الأكل المقيد (ARFID) مع تشوه صورة الجسم — يحتاج تحويل طبي فوري\n\n"
            "🛠️ **الخطة:**\n"
            "1. **تحويل طبي نفسي فوري:** تقييم طبي للعلامات الحيوية والتغذية — أولوية قصوى\n"
            "2. **CBT-E (النسخة المخصصة لاضطرابات الأكل):** تحدي المعتقدات حول الطعام والوزن\n"
            "3. **العلاج الأسري (FBT):** إشراك العائلة في إعادة التغذية\n"
            "4. **تقليل المقارنة الاجتماعية:** تحديد وقت محدد لوسائل التواصل"
        )
    },
    "case_6": {
        "title": "📋 الحالة 6: الحداد المطوّل بعد فقدان الأهل",
        "brief": "شاب (24 سنة) — فقد والده قبل 8 أشهر، لا يقدر يعود لحياته الطبيعية.",
        "details": (
            "📋 **دراسة حالة سريرية — Case Study #6**\n\n"
            "👤 **العميل:** شاب (24 سنة) — يعمل ويدرس\n"
            "⚠️ **الشكوى:** حزن مستمر 8 أشهر بعد فقدان الأب، لا يستطيع العودة لروتينه\n\n"
            "🔍 **الأعراض:**\n"
            "• يشعر بالفراغ والوحدة الشديدة، يزور القبر أسبوعياً لساعات\n"
            "• توقف عن العمل والدراسة، يعيش مع أمه\n"
            "• يقول: (ما في سبب أصلي أكمل، الدنيا فاضية من غيره)\n"
            "• ينام كثيراً لكن لا يشعر بالراحة، يفقد الشهية\n\n"
            "❓ **سؤال التدريب:** شنو الفرق بين الحداد الطبيعي والحداد المطوّل؟ وكيف تساعد؟"
        ),
        "solution": (
            "💡 **التحليل والخطة العلاجية:**\n\n"
            "🎯 **التشخيص:** اضطراب الحداد المطوّل (Prolonged Grief Disorder)\n\n"
            "🛠️ **الخطة:**\n"
            "1. **الاحتواء والسماح بالحزن:** لا نسرّعه — نسمح له يحس بالحزن بأمان\n"
            "2. **إعادة الربط بالحياة:** أهداف صغيرة جداً — خروج واحد، مكالمة صديق\n"
            "3. **الاستمرارية الرمزية:** طريقة جديدة للتواصل مع الأب (كتابة رسائل، زيارة ذات معنى)\n"
            "4. **إعادة بناء الهوية:** 'أنا ابنه' ← 'أنا شخص عنده قيمة بغض النظر عن وجوده'"
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
        [InlineKeyboardButton("📋 حالات سريرية تدريبية", callback_data="cases_list")],
        [InlineKeyboardButton("🧠 استراتيجيات علاجية (CBT / REBT)", callback_data="strategies_list")],
        [InlineKeyboardButton("🤖 المشرف الأكاديمي الذكي", callback_data="chat_academic_start")],
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
        "🎓 **المشرف الأكاديمي الذكي (دكتور Nafas2) وياك هسه 🧠**\n"
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
#     10. التدريب السريري العملي - اختبار الأخصائي (Roleplay Evaluator)
# =============================================================================

async def roleplay_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء اختبار التدريب السريري العملي: الطالب يصير أخصائي ويواجه عميل"""
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

    # تنويع السيناريوهات بناءً على رقم الجولة
    scenario_variants = {
        1: {
            "theme": "الجلسة الأولى وبناء العلاقة العلاجية",
            "client_types": [
                "طالب مستجد متوتر من الجامعة والاغتراب",
                "طالبة محجبة بتحسس من نظرات الزملاء",
                "شاب من محافظة بعيدة يحس بالغربة والوحدة",
                "طالبة متفوقة بس خايفة من التوقعات العالية",
                "شاب عامل مع دراسته، مرهق ومنهك"
            ]
        },
        2: {
            "theme": "النموذج المعرفي: فكرة → شعور → سلوك",
            "client_types": [
                "طالب يقول: (ما أقدر أسوي شي، عقلي مقفل)",
                "طالبة تفكر: (إذا ما طلعت ٩٠+ = فاشلة)",
                "شاب يفكر: (الناس كلها بتشوف عيوبي وتضحك عليّ)",
                "فتاة تقول: (أهلي ما راح يسامحوني لو غلطت)",
                "طالب يظن: (النجاح للحظ، مو للجهد، وأنا سيئ الحظ)"
            ]
        },
        3: {
            "theme": "الأسئلة السقراطية لكشف التشوهات المعرفية",
            "client_types": [
                "طالب بقلق اجتماعي: (كلهم بيحكمون عليّ)",
                "طالبة بكمالية: (الخطأ الواحد يدمر كل شي)",
                "شابة باكتئاب خفيف: (ماكو شي يستاهل، حياتي فاضية)",
                "شاب بوسواس تفكير: (لو ما سويت الطقس، يصير مصيبة)",
                "طالبة بقلق امتحان: (راح أنسى كل شي بالقاعة)"
            ]
        },
        4: {
            "theme": "إعادة الهيكلة المعرفية (دليل + بديل + تجربة)",
            "client_types": [
                "طالب يفكر: (الدكتور يكرهني، ما راح ينجحني)",
                "طالبة تقول: (صديقتي ما ردت = زعلانة مني)",
                "شاب يعتقد: (القلق دليل على إني ضعيف)",
                "فتاة تظن: (الرفض = ما أستاهل الحب)",
                "طالب يردد: (أنا كسول، ما أقدر أغير)"
            ]
        },
        5: {
            "theme": "التخطيط للجلسات وأهداف SMART",
            "client_types": [
                "طالب يريد: (أوقف التسويف وأدرس يومياً)",
                "طالبة تبغى: (أكسر العزلة وأتكلم مع ٣ ناس جدد)",
                "شاب هدف: (أقدم برزنتيشن من غير ما أرجف)",
                "شابة تريد: (أنام بدري وأصحي نشيطة للجامعة)",
                "طالب يطمح: (أسيطر على نوبات الغضب مع أهلي)"
            ]
        },
        6: {
            "theme": "المتابعة، تعديل الخطة، منع الانتكاس",
            "client_types": [
                "طالب تحسن بس خايف يرجع للوراء بالامتحانات",
                "طالبة نجحت بالتعرّض الاجتماعي بس مترددة تستمر",
                "شاب قلّلت نوبات الهلع بس ما زالت تتجنب أماكن",
                "فتاة طورت روتين نوم بس السفر عطّلها",
                "طالب تعلم المهارات بس يصير كسلان يطبقها"
            ]
        }
    }

    if round_num <= 6:
        variant = scenario_variants[round_num]
        skill_focus = f"🎯 **المهارة: {variant['theme']}**\nالقانون: {skill_by_round[round_num].split('القانون: ')[1]}"
        # اختيار نوع عميل عشوائي للتنويع
        import random
        random.seed(round_num * 42 + hash(str(context.user_data.get("user_id", 0))))
        client_type = random.choice(variant["client_types"])
        scenario_type = f"{variant['theme']} - {client_type}"
    else:
        # جولات متقدمة: حالات معقدة ومتنوعة
        advanced_scenarios = [
            {"title": "قلق صحة + وسواس جسدي", "focus": "التفريق بين القلق والوسواس، فنية التعرض مع منع الاستجابة"},
            {"title": "اكتئاب ما بعد رسوب + تفكير انتحاري سلبي", "focus": "تقييم الخطر، خطة سلامة، تنشيط سلوكي متدرج"},
            {"title": "صدمة قديمة (تنمر) تؤثر على العلاقات الحالية", "focus": "معالجة الصدمة، إعادة معالجة الذكريات، بناء أمان"},
            {"title": "رهاب اجتماعي + تجنب أكاديمي + عزلة", "focus": "التعرض المتدرج، تدريب مهارات اجتماعية، تجارب سلوكية"},
            {"title": "كمالية عصابية + إرهاق مزمن + تسويف", "focus": "تعديل المعايير، قبول الخطأ، توازن الحياة"},
            {"title": "قلق انفصال + قرارات مصيرية (زواج/هجرة)", "focus": "حل المشكلات، توضيح القيم، قرار مبني على أدلة"},
            {"title": "غضب متفجر + مشاكل أسرية + ندماً لاحقا", "focus": "إدارة الغضب، فترات تهدئة، تواصل حازم"},
            {"title": "وسواس ديني (وسواس طهارة/صلاة) + قلق", "focus": "تفريق الوسواس عن التدين، تعرض مع منع استجابة"},
            {"title": "صورة ذاتية سلبية + علاقات فاشلة متكررة", "focus": "السكيما الأساسية، إعادة تنشئة ذاتية، حدود صحية"},
            {"title": "ضغط أهلي شديد + هوية مهنية مهزوزة", "focus": "استقلالية نفسية، فصل الرغبات عن التوقعات"},
            {"title": "فوبيا محددة (مصاعد/طيران/حيوانات) + تجنب", "focus": "التعرض التخيلي والواقعي، استرخاء، تدرج"},
            {"title": "أعراض جسدية نفسية المنشأ (ألم/إرهاق/دوار)", "focus": "نموذج بيولوجي-نفسي-اجتماعي، إعادة نسب الأعراض"},
        ]
        idx = (round_num - 7) % len(advanced_scenarios)
        selected = advanced_scenarios[idx]
        skill_focus = f"🎯 **المهارة: حالة معقدة متكاملة - {selected['focus']}**\nالقانون: 'الحالات الحقيقية معقدة، استخدم كل أدواتك بمرونة وتراتب'"
        scenario_type = f"حالة متقدمة: {selected['title']}"

    # طلب سيناريو جديد من Gemini
    # عناصر تنويع إضافية لضمان عدم التكرار
    import random
    variation_seed = round_num * 1000 + hash(str(context.user_data.get("user_id", 0))) % 10000
    
    # تنويع التفاصيل الدقيقة
    settings = ["قاعة المحاضرات", "المكتبة", "مقهى الجامعة", "سكن الطالبات/الطلبة", "بيت الأهل", "العمل الجزئي", "عيادة الجامعة", "قاعة الامتحان", "ممرات الكلية", "جروب الواتساب الدراسي"]
    emotions_primary = ["الخوف", "القلق", "الحزن", "الغضب", "الإحباط", "الخجل", "اليأس", "الوحدة", "الذنب", "الحيرة"]
    triggers = ["امتحان قادم", "تراكم واجبات", "مشكلة مع صديق", "ضغط أهلي", "قرار مصيري", "رسوب سابق", "مقارنة بالآخرين", "انتقاد ذاتي", "حدث اجتماعي", "تغيير روتين"]
    
    setting = settings[variation_seed % len(settings)]
    emotion = emotions_primary[(variation_seed // 7) % len(emotions_primary)]
    trigger = triggers[(variation_seed // 13) % len(triggers)]
    
    scenario_prompt = (
        f"أنت مُدَرِّب سريري عراقي خبير، قريب من الطالب، صبور ومحفز، مبدع في السيناريوهات.\n"
        f"اكتب **مشهد عميل واحد فقط وفريد** لاختبار طالب علم نفس (مرحلة ثانية - مبتدئ).\n\n"
        f"📊 **الجولة: {round_num} | بذرة التنويع: {variation_seed}**\n"
        f"{skill_focus}\n\n"
        f"نوع العميل المستهدف: {scenario_type}\n"
        f"السياق البيئي: {setting}\n"
        f"العاطفة السائدة: {emotion}\n"
        f"المحفز/السبب: {trigger}\n\n"
        f"المتطلبات الإلزامية للتميز والتنوع:\n"
        f"1. **عميل فريد ومحدد**: عمر (18-28)، اسم مستعار، تخصص/سنة، خلفية عائلية مختصرة\n"
        f"2. **موقف حي واقعي**: يحصل في {setting}، بسبب {trigger}\n"
        f"3. **عاطفة محورية**: {emotion} - مع تجليات جسدية وسلوكية محددة\n"
        f"4. **أفكار تلقائية مميزة**: 2-3 أفكار مشوهة محددة لهذا العميل (مش عامة)\n"
        f"5. **سلوكيات ظاهرة**: شي العميل يسويه أو يتجنبه\n"
        f"6. **مكتوب باللهجة العراقية البيضاء البسيطة** (كأنك تحكي لصديقك)\n"
        f"7. **مصمم لتمارين مهارة الجولة أعلاه بدقة** - فيه مادة غنية لتطبيقها\n"
        f"8. **4-5 أسطر فقط**، مختصر، مشوق، غير نمطي\n\n"
        f"التنسيق الإلزامي:\n"
        f"🎬 **المشهد: [عنوان إبداعي مشوق - مش عام]**\n"
        f"👤 **العميل:** [اسم مستعار، العمر، التخصص/السنة، جملة واحدة عن الخلفية]\n"
        f"💭 **الحالة:** [العاطفة + 3 نقاط: فكرة تلقائية، إحساس جسدي، سلوك]\n"
        f"❓ **تحدي الجولة:** [سؤال واحد مركز يركز على مهارة الجولة فقط]\n\n"
        f"أمثلة للتحدي حسب المهارة:\n"
        f"• جولة 1 (علاقة): 'شنو تقول/تسوي أول 5 دقايق تخلي [الاسم] يحس بالأمان ويفضفض؟'\n"
        f"• جولة 2 (نموذج معرفي): '[الاسم] يقول: (فكرة مشوهة). حلل: الفكرة؟ الشعور؟ السلوك؟'\n"
        f"• جولة 3 (سقراطي): 'طبّق سؤال سقراطي واحد على فكرة [الاسم]: (شنو الدليل؟)'\n"
        f"• جولة 4 (إعادة هيكلة): 'ساعد [الاسم] ياختبر فكرته: (شنو الدليل؟ البديل؟ تجربة؟)'\n"
        f"• جولة 5 (تخطيط): 'صيّغ مع [الاسم] هدف ذكي (SMART) وفنية CBT واحدة للأسبوع الجاي'\n"
        f"• جولة 6 (متابعة): '[الاسم] تحسن بس خايف ينتكس. شنو تسوي؟ خطة منع انتكاس؟'\n\n"
        f"⚡ **تنبيه مهم**: كل سيناريو يجب أن يكون **مختلفاً تماماً** عن أي سيناريو سابق.\n"
        f"استخدم بذرة التنويع ({variation_seed}) لتوليد تفاصيل فريدة: اسم مختلف، موقف مختلف، تشوهات مختلفة.\n"
        f"كن قريباً، واقعياً، كأن الموقف يصير للطالب نفسه أو لصديقه المقرب."
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

    keyboard = [
        [InlineKeyboardButton("💡 شنو أجاوبه؟", callback_data="cp_hint")],
        [InlineKeyboardButton("❌ إنهاء الاختبار والعودة", callback_data="end_roleplay")]
    ]

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

    # المهارة المستهدفة للجولة مع توقعات تفصيلية
    skill_by_round = {
        1: {
            "name": "العلاقة العلاجية + فتح الجلسة",
            "law": "الناس ما يهتمون بما تعرف، إلا لما يعرفون إنك تهتم بهم",
            "expectations": "الترحيب الحار، تقديم الذات، شرح سرية الجلسة، إظهار التعاطف الحقيقي، سؤال مفتوح للبداية، متابعة لغة الجسد، تطبيع المشاعر"
        },
        2: {
            "name": "النموذج المعرفي: فكرة → شعور → سلوك",
            "law": "الأحداث ما تسبب المشاعر، أفكارك عنها هي اللي تسببها",
            "expectations": "تحديد الفكرة التلقائية بدقة، ربطها بالشعور المحدد (مش عام)، ربطها بالسلوك الملاحظ، رسم المثلث المعرفي، سؤال العميل: 'شنو حسيت لما فكّرت كذا؟'"
        },
        3: {
            "name": "الأسئلة السقراطية لكشف التشوهات",
            "law": "اسأل، ما تقل",
            "expectations": "اختيار تشوه واحد فقط، تطبيق سؤال سقراطي واحد مناسب (دليل، بديل، استثناء، كارثية)، عدم إعطاء الحل، انتظار إجابة العميل، تعزيز المحاولة"
        },
        4: {
            "name": "إعادة الهيكلة المعرفية: فنية الأعمدة الثلاثة",
            "law": "الفكرة فرضية مو حقيقة — اختبرها",
            "expectations": "عمود الدليل: أسئلة تجمع أدلة مع وضد، عمود البديل: صياغة فكرة متوازنة واقعية، عمود التجربة: تصميم تجربة سلوكية صغيرة لاختبار الفكرة الجديدة، متابعة النتائج"
        },
        5: {
            "name": "التخطيط للجلسات: أهداف SMART + فنيات CBT",
            "law": "الهدف بلا خطة مجرد حلم",
            "expectations": "هدف محدد (Specific)، قابل للقياس (Measurable)، قابل للتحقيق (Achievable)، واقعي (Relevant)، محدد بوقت (Time-bound)، فنية CBT واحدة محددة، واجب منزلي واضح"
        },
        6: {
            "name": "المتابعة، تعديل الخطة، منع الانتكاس",
            "law": "العلاج مش خط مستقيم",
            "expectations": "مراجعة الواجب المنزلي، تعزيز المكاسب، تحديد محفزات الانتكاس، خطة طوارئ مكتوبة، تحديد علامات التحذير المبكرة، جلسات متابعة متباعدة، تعزيز الاستقلالية"
        },
    }
    if round_num <= 6:
        skill_info = skill_by_round[round_num]
        target_skill = f"{skill_info['name']} - قانون: {skill_info['law']}"
        skill_expectations = skill_info['expectations']
    else:
        target_skill = "تطبيق متكامل لكل المهارات السابقة بحالة حقيقية معقدة"
        skill_expectations = "مرونة في استخدام الأدوات، تسلسل منطقي: علاقة → نموذج → سقراطي → إعادة هيكلة → خطة → متابعة، تكيف مع تعقيد الحالة"

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, update.effective_chat.id, stop_typing)
    )

    # استخدام البرومبت المخصص من قاعدة البيانات أو الافتراضي
    roleplay_prompt = db.get_setting("prompt_roleplay") or SYSTEM_PROMPT_ROLEPLAY
    
    evaluation_prompt = (
        f"{roleplay_prompt}\n\n"
        f"=== السياق الحالي ===\n"
        f"📊 **الجولة: {round_num}**\n"
        f"🎯 **المهارة المستهدفة: {target_skill}**\n"
        f"📋 **التوقعات الدقيقة لهذه المهارة:** {skill_expectations}\n\n"
        f"مشهد العميل:\n{scenario}\n\n"
        f"إجابة الطالب:\n{user_answer}\n\n"
        f"=== مهمتك الآن: قيم، علّم، شجع ===\n"
        f"أنت أستاذه القريب، الصبور، اللي يبي يتعلم *بالممارسة* مو بالحفظ.\n\n"
        f"**هيكل تقييمك الثابت (4 خطوات):**\n\n"
        f"1️⃣ **تعزيز المحاولة** (حتى لو غلط):\n"
        f"   'زين يا بطل، شايف كيف فكرت؟ عاشت إيدك إنك حاولت...'\n"
        f"   ← خليه يحس إن محاولته مقدرة، مهما كانت.\n\n"
        f"2️⃣ **سؤال سقراطي يصحح/يرشد** (قانون: اسأل، ما تقل):\n"
        f"   بدل ما تقول 'الغلط كذا'، اسأله سؤال يوجهه للمهارة المستهدفة:\n"
        f"   • جولة 1: 'العلاقة أساس... لو بدأت بـ 3 دقايق احتواء وترحيب، شكو يتغير؟'\n"
        f"   • جولة 2: 'فكّر بالنموذج: الفكرة → الشعور → السلوك... وين الربط عند [اسم العميل]؟'\n"
        f"   • جولة 3: 'لو طبقنا سؤال سقراطي: (شنو الدليل على هالفكرة؟) ... شكو تلاحظ؟'\n"
        f"   • جولة 4: 'الأعمدة الثلاثة: الدليل؟ البديل المتوازن؟ تجربة سلوكية صغيرة؟'\n"
        f"   • جولة 5: 'الهدف ذكي (SMART)؟ وش فنية CBT واحدة تنفع؟ الواجب المنزلي؟'\n"
        f"   • جولة 6: 'علامات الانتكاس؟ خطة طوارئ؟ كيف نعزز الاستقلالية؟'\n"
        f"   ← خليه *هو* يوصل للحل بسؤالك.\n\n"
        f"3️⃣ **أداة/قانون جديد يتعلمها هالجولة** (خذه معك):\n"
        f"   'الأداة الجديدة: [اسم القانون + جملة واحدة عملية]'\n"
        f"   أمثلة: 'قانون: دايمًا ابدأ بالعلاقة العلاجية — 3 دقايق احتواء تغير الجلسة'\n"
        f"   'قانون: الفكرة فرضية مو حقيقة — اسأل: شنو الدليل؟'\n"
        f"   'قانون: الأهداف ذكية (SMART) — وضح، قيس، وقت، واقعي, مهم'\n\n"
        f"4️⃣ **درجة من 10 + تحدي لطيف للجولة الجاية**:\n"
        f"   'درستك: 8/10 — زين جداً! تحاول تطبق [المهارة]...'\n"
        f"   'تريد نجرب مهارة جديدة بالجولة الجاية؟ ولا نثبت هذي على حالة ثانية؟ 😄'\n\n"
        f"=== أسلوبك ===\n"
        f"• لهجة عراقية بيضاء، قريبة، مضحكة شوي، محفزة\n"
        f"• تشبيهات بسيطة: 'العقل موبايل، الأفكار تطبيقات...'\n"
        f"• مختصر (5-7 أسطر)، ما تطول، ركز على التعليم\n"
        f"• لا تطلع حل كامل — خلي السؤال السقراطي يقود\n"
        f"• اذكر اسم العميل من السيناريو لتخصيص التعليق"
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
    """إنهاء اختبار التدريب السريري العملي"""
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


async def cp_hint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pop-up Beginner Response Helper: Shows a brief hint via Telegram alert without cluttering chat."""
    query = update.callback_query
    await query.answer()  # answer immediately to clear loading state

    cp_data = context.user_data.get("cp_data", {})

    if cp_data:
        case_data = cp_data.get("case_data", {})
        scenario = case_data.get("complaint", "")
        student_name = cp_data.get("student_name", "الطالب")
        user_title = cp_data.get("user_title", "دكتور")
        try:
            idx = int(case_data.get("skill_index", 0) or 0) % len(SKILLS)
        except Exception:
            idx = 0
        skill = SKILLS[idx]
        skill_focus = skill["name"]

        if not scenario:
            await query.answer(text="ماكو شكاية حالياً للاسف، جرّب جلسة جديدة 😊", show_alert=True)
            return

        hint_prompt = (
            f"أنت مشرف سريري عراقي لطيف، قريب، محفز. "
            f"طالب علم نفس (مرحلة ثانية) عم يمرّن في الممارسة السريرية ويحتاج مساعدة سريعة.\n\n"
            f"User Name: {student_name}\n"
            f"User Title: {user_title}\n"
            f"قاعدة صارمة: لا تستخدم أسماء أزرار قائمة الموقع كاسم للطالب. عنونه باستخدام {user_title} {student_name} فقط، واستخدم القواعد النحوية المناسبة للجنس.\n\n"
            f"📊 المهارة السريرية: {skill_focus}\n"
            f"شكوى المريض:\n{scenario}\n\n"
            f"مهمتك: أعطِ **سطرين فقط، قصيرين جداً، بلهجة عراقية بسيطة**، "
            f"يكونوا **نصيحة عملية مباشرة** للطالب شنو يقول/يسوي الآن.\n"
            f"ممنوع المصطلحات الأكاديمية، ممنوع الشرح، ممنوع الإطالة.\n\n"
            f"أمثلة للأسلوب:\n"
            f"- اسأله: (شلون حسيت لما صارت هالموقف؟)\n"
            f"- طمأنه: (طبيعي تحس كذا، إحنا نمرّن سوا)\n"
            f"- القانون: (الفكرة مو حقيقة، شنو الدليل؟)\n"
            f"- وجّهه: (خليه يحكي أكثر، سمعني إيّاه)\n\n"
            f"أطبع السطرين مفصولين بسطر جديد، بدون ترقيم أو علامات."
        )

        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(
            send_typing_periodically(context.bot, query.message.chat_id, stop_typing)
        )

        last_patient = ""
        for h in reversed(cp_data.get("history") or []):
            if h.get("role") in ("model", "patient"):
                last_patient = (h.get("text") or "")[:500]
                break
        if last_patient:
            hint_prompt += f"\n\nآخر رد في الجلسة:\n{last_patient}\n"

        try:
            hint_text = await call_gemini_api(
                user_message="أعطني تلميح سريري سريع هسه",
                system_instruction=hint_prompt,
                chat_history=None,
                max_output_tokens=220,
            )
        except Exception:
            hint_text = "💡 ركّز على الاستماع الفعّال واطرح سؤالًا مفتوحًا يدعو المريض للتعبير عن مشاعره."
        finally:
            stop_typing.set()
            try:
                await typing_task
            except Exception:
                pass

        kb = _cp_live_keyboard() if cp_data.get("step") == "roleplay" else _cp_intake_keyboard()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"💡 <b>تلميح سريري</b>\n{_to_telegram_html(hint_text)}",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
        return

    scenario = context.user_data.get("roleplay_scenario", "")
    round_num = context.user_data.get("roleplay_round", 1)
    history = context.user_data.get("roleplay_history", [])

    if not scenario:
        await query.answer(text="ماكو سيناريو حالياً للاسف، ابدأ اختبار جديد 😊", show_alert=True)
        return

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, query.message.chat_id, stop_typing)
    )

    # المهارة المستهدفة للجولة (للتوجيه)
    skill_by_round = {
        1: "العلاقة العلاجية + فتح الجلسة (ترحيب، احتواء، ثقة)",
        2: "النموذج المعرفي: فكرة → شعور → سلوك",
        3: "الأسئلة السقراطية (شنو الدليل؟ البديل؟ الاستثناء؟)",
        4: "إعادة الهيكلة المعرفية: الدليل + البديل + التجربة",
        5: "أهداف ذكية (SMART) + خطة جلسة + واجب",
        6: "متابعة + خطة طوارئ + منع الانتكاس",
    }
    skill_focus = skill_by_round.get(round_num, "تطبيق مهارات متكامل")

    hint_prompt = (
        f"أنت مشرف سريري عراقي لطيف، قريب، محفز. "
        f"طالب علم نفس (مرحلة ثانية) عم يمرّن بمشهد عميل ويحتاج مساعدة سريعة.\n\n"
        f"📊 الجولة: {round_num} | المهارة: {skill_focus}\n\n"
        f"مشهد العميل:\n{scenario}\n\n"
        f"مهمتك: أعطِ **سطرين فقط، قصيرين جداً، بلهجة عراقية بسيطة**، "
        f"يكونوا **نصيحة عملية مباشرة** للطالب شنو يقول/يسوي الآن.\n"
        f"ممنوع المصطلحات الأكاديمية، ممنوع الشرح، ممنوع الإطالة.\n\n"
        f"أمثلة للأسلوب:\n"
        f"- اسأله: (شلون حسيت لما صارت هالموقف؟)\n"
        f"- طمأنه: (طبيعي تحس كذا، إحنا نمرّن سوا)\n"
        f"- القانون: (الفكرة مو حقيقة، شنو الدليل؟)\n"
        f"- وجّهه: (خليه يحكي أكثر، سمعني إيّاه)\n\n"
        f"أطبع السطرين مفصولين بسطر جديد، بدون ترقيم أو علامات."
    )

    try:
        hint_text = await call_gemini_api(
            user_message="أعطني تلميح سريع هسه",
            system_instruction=hint_prompt,
            chat_history=None
        )
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    # عرض كـ Pop-up Alert، ما ينرسل بالچات
    await query.answer(text=hint_text, show_alert=True)



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
        "🛠️ **هلا والله بمديرنا الغالي! نورت لوحة التحكم لبوت Nafas2 🧠**\n"
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
        "📊 **إحصائيات بوت Nafas2 الشاملة:**\n"
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
        "🛠️ **لوحة تحكم بوت Nafas2 🧠**\n"
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
        f"3️⃣ **مدرب التدريب السريري (اختبار عملي):**\n"
        f"   الطول: {len(current_prompts['roleplay'])} حرف\n"
        f"   الحالة: {'✅ مخصص' if db.get_setting(PROMPT_KEYS['roleplay']) else '📋 افتراضي'}\n\n"
        "👇 **اختر النموذج اللي تريد تعدله:**"
    )

    keyboard = [
        [InlineKeyboardButton("1️⃣ المرشد النفسي", callback_data="prompt_edit:counselor")],
        [InlineKeyboardButton("2️⃣ المشرف الأكاديمي", callback_data="prompt_edit:academic")],
        [InlineKeyboardButton("3️⃣ مدرب التدريب السريري", callback_data="prompt_edit:roleplay")],
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
        "roleplay": "مدرب التدريب السريري (اختبار عملي)",
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





# =============================================================================
#          الممارسة السريرية الديناميكية - AI-Generated Cases
# =============================================================================

SKILLS = [
    {
        "name": "إعادة البناء المعرفي (Cognitive Restructuring)",
        "do": "ساعده يفكّك فكرته المشوهة: شنو الدليل؟ هل صار شي خطر فعلاً؟ شنو البديل المعقول؟",
        "dont": "لا تقل 'لا تخافي' أو 'استرخي' أو أعطِ نصائح جاهزة — هذا يزيد مقاومة المريض",
    },
    {
        "name": "التنشيط السلوكي (Behavioral Activation)",
        "do": "ساعده يبدأ نشاط صغير جداً (5 دقايق) قبل ما يفكر يكمّل. ركز على الشعور بعد النشاط مش النتيجة.",
        "dont": "لا تطلب منه يبدأ نشاط كبير دفعة وحدة. لا تنتظر تحفيزه الداخلي — اجعل البدء هو التحفيز.",
    },
    {
        "name": "التعرض المنهجي (Systematic Desensitization)",
        "do": "اصنع سلم مخاوف من السهل للصعب. ابدأ من المستوى الأسهل ورتّقه معه حتى يتعود.",
        "dont": "لا تعرضه على أخطر مخاوفه دفعة وحدة. لا تتجاوز مستواه الحالي بسرعة.",
    },
    {
        "name": "التمرين الذهني (Mindfulness)",
        "do": "علّمه يلاحظ أفكاره كظواهر عابرة مش حقائق: 'أرى إنني فاكر كده... هدّه فكرة، مش واقع'.",
        "dont": "لا تطلب منه يوقف الأفكار. لا تحكم على أفكاره بالمحتوى — ركز على العلاقة معها.",
    },
    {
        "name": "المقابلة التحفيزية (Motivational Interviewing)",
        "do": "استمع للتردد وعزّز حرية الاختيار: 'في جزء منك يحب يتحسن وفي جزء مبتعرف يبدا'.",
        "dont": "لا تفرض التغيير. لا تحارب التردد — اجعله جزء طبيعي من رحلة التغيير.",
    },
]

CASE_POOL = [
    {
        "patient_name": "سارة",
        "age": 22,
        "complaint": "قلق اجتماعي شديد خوف من الحكم",
        "core_fear": "الخوف من الحكم السلبي",
        "avoidance": "تتجنب المحاضرات والمناسبات",
        "physical": "تعرق، صداع، غثيان",
        "thoughts": ["كل الناس يشوفون خللي", "ما أقدر أتكلم", "راح يضحكوا عليي"],
        "opening": "دكتور... أنا عايزة أسوي شي حاجة بس ما أعرف من وين أبدأ",
        "skill_index": 0,
    },
    {
        "patient_name": "أحمد",
        "age": 20,
        "complaint": "وسواس قهري تلوث وغسل",
        "core_fear": "نقل العدوى للأهل",
        "avoidance": "يتجنب الحمامات العامة والمصافحة",
        "physical": "احمرار باليدين، إرهاق",
        "thoughts": ["لو ما غسلت راخ مرض أهلي", "إيدي ملوثة", "أنا مسؤول عن أي ضرر"],
        "opening": "دكتور... أنا من سنتين وغسل يدي 30 مرة باليوم ودفعني دار بس ما أقدر أوقف",
        "skill_index": 1,
    },
    {
        "patient_name": "ليلى",
        "age": 21,
        "complaint": "نوبات هلع حادة بالقاعة",
        "core_fear": "الخوف من فقدان السيطرة",
        "avoidance": "تتجنب القاعات المزدحمة",
        "physical": "خفقان، ضيق تنفس، رجفة",
        "thoughts": ["راح أموت", "راح أصير مجنونة", "ما أقدر أتحكم بنفسي"],
        "opening": "دكتور... الحين عندي أسبوع على امتحان وأنا خايفة بزاف ما راح أقدر ادخل القاعة",
        "skill_index": 2,
    },
    {
        "patient_name": "خالد",
        "age": 23,
        "complaint": "اكتئاب بعد فراق طويل",
        "core_fear": "الفراغ والعزلة",
        "avoidance": "يبقى بالبيت يلعب بالموبايل كل اليوم",
        "physical": "أرق، فقدان شهية، إرهاق",
        "thoughts": ["ما في شي يسوي فرق", "أنا ما أصلح", "كل الناس أحسن مني"],
        "opening": "دكتور... تفرقت عن صاحبي السنة وفصلي واللي صار ما عندي إلهتمام بح شي",
        "skill_index": 3,
    },
    {
        "patient_name": "منى",
        "age": 19,
        "complaint": "ضعف ثقة بالنفس ومقارنة النفس",
        "core_fear": "الفشل الأكاديمي والشخصي",
        "avoidance": "ما تقدر تبدأ شي جديد",
        "physical": "صداع، توتر، اضطراب بالقولون",
        "thoughts": ["أنا ثقيلة", "ما أصل لأي شي", "الناس كلهم أحسن مني"],
        "opening": "دكتور... أنا حالياً أحس إن أنا ثقيلة وأنا اللي ما أقدر أعمل شي صحيح بالحياة",
        "skill_index": 4,
    },
    {
        "patient_name": "ياسر",
        "age": 24,
        "complaint": "رهاب امتحانات وتسويف",
        "core_fear": "الخوف من الفشل الأكاديمي الكامل",
        "avoidance": "يتجنب فتح الملازم، يماطل حتى اللحظات الأخيرة",
        "physical": "خفقان، صداع، توتر عضلي، اضطراب بالقولون",
        "thoughts": ["أقرأ من بعمن أني عاجز بهالحاجة", "ما أقدر أتحكم بنفسي", "راح انسى كل شي بالقاعة"],
        "opening": "دكتور... أنا راح امتحان بعد أسبوع وما درست شي. عندي خوف بزاف من القاعة",
        "skill_index": 0,
    },
    {
        "patient_name": "نور",
        "age": 20,
        "complaint": "حزن مستمر بعد فقدان الأب",
        "core_fear": "الفراغ والعودة للحياة بدون الأهل",
        "avoidance": "يبقى بالبيت لا يعمل لا يدرس يعيش مع أمه",
        "physical": "كسل شديد، أرق، فقدان شهية",
        "thoughts": ["ما في سبب أصلي أكمل", "الدنيا فاضية من غيره", "أنا ما أصلح"],
        "opening": "دكتور... أبي توفي قبل 8 أشهر وما قدرت أرجع لحياتي الطبيعية... كل يوم نفس الشي",
        "skill_index": 3,
    },
    {
        "patient_name": "عبير",
        "age": 19,
        "complaint": "تقييد أكل ومقارنة جسدية",
        "core_fear": "الخوف من السمنة وعدم القبول",
        "avoidance": "تاكل وجبة واحدة يومياً، تتجنب الأكل أمام الناس",
        "physical": "فقدان 8 كيلو، شعر متساقط، اضطراب بالقولون",
        "thoughts": ["أنا سمينة", "الناس تضحك على شكلي", "لو نزلت وزني راح يحبو"],
        "opening": "دكتور... أنا ما أقدر آكل مع الناس... أحس إن شكلي مش مقبول وأنا اللي مش لازم أكون",
        "skill_index": 4,
    },
]


def _get_user_title_and_name(context, user_id: int, first_name: str = "") -> tuple:
    """تحديد العنوان (دكتور/دكتورة) بناءً على الاسم المسجل أو قاعدة البيانات أو أول اسم في Telegram"""
    cp_data = context.user_data.get("cp_data", {})
    name = cp_data.get("student_name", "")

    if not name:
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT full_name, username FROM users WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row:
                name = row.get("full_name") or row.get("username") or ""
        except Exception:
            pass

    name = name.strip() or first_name.strip() or "الطالب"
    if name.endswith("ة") or name.endswith("ى"):
        title = "دكتورة"
    else:
        title = "دكتور"

    return title, name


def _escape_html(text: Any) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _to_telegram_html(text: str) -> str:
    """تحويل Markdown الشائع إلى HTML آمن مع الإبقاء على <b>/<i>"""
    import re
    raw = text or ""
    lowered = raw.lower()
    if "<b>" in lowered or "<i>" in lowered:
        t = raw
        for src, dst in (
            ("<b>", "§B§"), ("</b>", "§/B§"),
            ("<B>", "§B§"), ("</B>", "§/B§"),
            ("<i>", "§I§"), ("</i>", "§/I§"),
            ("<I>", "§I§"), ("</I>", "§/I§"),
        ):
            t = t.replace(src, dst)
        t = _escape_html(t)
        return (
            t.replace("§B§", "<b>").replace("§/B§", "</b>")
            .replace("§I§", "<i>").replace("§/I§", "</i>")
        )
    t = _escape_html(raw)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    return t


async def _cp_reply_html(bot, chat_id: int, text: str, reply_markup=None):
    html_text = _to_telegram_html(text)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=html_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


def _student_first_name(full_name: str) -> str:
    parts = (full_name or "الطالب").strip().split()
    return parts[0] if parts else "الطالب"


def _cp_intake_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 بدء المحاكاة التفاعلية", callback_data="cp_start_dialogue")],
    ])


def _cp_live_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏁 ختام الجلسة وتوليد التقرير", callback_data="cp_end")],
    ])


def build_clinical_case_card_html(case_data: dict, student_name: str, user_title: str) -> str:
    """كارت حالة سريرية بتنسيق HTML المدعوم من تلغرام"""
    patient = _escape_html(case_data.get("patient_name", "المريض"))
    age = _escape_html(case_data.get("age", "—"))
    gender = case_data.get("patient_gender", "")
    if gender == "male":
        gender_txt = "ذكر"
    elif gender == "female":
        gender_txt = "أنثى"
    else:
        gender_txt = ""
    profession = _escape_html(case_data.get("profession", ""))
    complaint = _escape_html(case_data.get("complaint", "—"))
    core_fear = _escape_html(case_data.get("core_fear", "—"))
    avoidance = _escape_html(case_data.get("avoidance", "—"))
    physical = _escape_html(case_data.get("physical", "—"))
    body = _escape_html(case_data.get("body_language", "يدخل ببطء، يتنفس بتوتر، ينظر للأسفل"))
    thoughts = case_data.get("thoughts") or []
    if isinstance(thoughts, str):
        thoughts = [thoughts]
    thoughts_html = "\n".join(f"• {_escape_html(t)}" for t in thoughts[:4]) or "• —"
    skill_idx = int(case_data.get("skill_index", 0) or 0) % len(SKILLS)
    skill_name = _escape_html(SKILLS[skill_idx]["name"])
    first = _escape_html(_student_first_name(student_name))
    title = _escape_html(user_title)
    gender_line = f" · {gender_txt}" if gender_txt else ""
    prof_line = f"\n💼 <b>الخلفية:</b> {profession}" if profession else ""

    return (
        f"<b>🩺 كارت الحالة السريرية</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>المريض:</b> {patient} · {age} سنة{gender_line}{prof_line}\n"
        f"🩺 <b>الشكوى الرئيسية:</b> {complaint}\n"
        f"💭 <b>الخوف الجوهري:</b> {core_fear}\n"
        f"🚫 <b>سلوك التجنب:</b> {avoidance}\n"
        f"🫀 <b>الأعراض الجسدية:</b> {physical}\n"
        f"🧠 <b>أفكار تلقائية:</b>\n{thoughts_html}\n"
        f"🎭 <b>لغة الجسد عند الدخول:</b> <i>({body})</i>\n"
        f"🎯 <b>مهارة الجلسة:</b> {skill_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>{title} {first}، اقرأ الكارت بهدوء ثم ابدأ المحاكاة. المريض ينتظرك داخل العيادة.</i>"
    )


def build_full_clinical_prompt(case_data: dict, user_first_name: str, user_title: str = "دكتور") -> str:
    """برومبت الدور المزدوج: مدرب سريري + مريض نفسي في كل رد"""
    first = _student_first_name(user_first_name)
    skill_idx = int(case_data.get("skill_index", 0) or 0) % len(SKILLS)
    skill = SKILLS[skill_idx]
    thoughts = case_data.get("thoughts") or []
    if isinstance(thoughts, list):
        thoughts_txt = " | ".join(str(t) for t in thoughts)
    else:
        thoughts_txt = str(thoughts)
    patient = case_data.get("patient_name", "المريض")
    return f"""أنت محاكي سريري ذكي لطلاب علم النفس. في كل رد تدمج دورين معاً بهذا الترتيب الإجباري:

1) 🎓 **[توجيه المدرب السريري]:**
حلّل بسرعة مهارة الطالب ({user_title} {first}) واعطِ ملاحظة سريرية مشجعة ومفيدة.
ثم اختم دائماً بسطر واحد: 👉 اكتب ردك دكتور {first}...

2) 👤 **{patient}:**
تحدّث بشخصية المريض بحماس وتفصيل درامي واقعي. اشرح مشاعره وأفكاره بعمق وتوسّع دون اختصار جاف.
تفاعل مباشرة مع كلام الطالب: جاوب على أسئلته، قاوم بلطف إن اندفع، وانفتح إن احتواه.
أضف مؤشرات لغة جسد بين قوسين مثل: *(ينظر للأرض، يضغط أصابعه، يبتسم بمرارة)*
باللهجة العراقية البيضاء. لا تكسر الدور. لا تذكر أنك ذكاء اصطناعي.

بيانات الحالة الملزمة:
- الاسم: {patient}
- العمر: {case_data.get('age', '—')}
- الجنس: {case_data.get('patient_gender', 'غير محدد')}
- الشكوى: {case_data.get('complaint', '')}
- الخوف الجوهري: {case_data.get('core_fear', '')}
- التجنب: {case_data.get('avoidance', '')}
- الأعراض الجسدية: {case_data.get('physical', '')}
- الأفكار التلقائية: {thoughts_txt}
- لغة الجسد: {case_data.get('body_language', '')}
- المهارة المستهدفة: {skill['name']}

---
**قواعد صارمة:**
- اختم دائماً السطر الأخير بجملة: 👉 اكتب ردك دكتور {first}...
- لا تستخدم وسوم HTML غير <b> و <i>.
- لا تستخدم عناوين مثل # أو رءوس.
- باللهجة العراقية البيضاء.
"""

def build_patient_only_prompt(case_data: dict, student_name: str, user_title: str) -> str:
    """برومبت المريض فقط - بدون توجيهات المدرب أثناء الجلسة"""
    first = _student_first_name(student_name)
    patient = case_data.get("patient_name", "المريض")
    skill_idx = int(case_data.get("skill_index", 0) or 0) % len(SKILLS)
    skill = SKILLS[skill_idx]
    return f"""أنت المريض في جلسة علاج نفسي مع {user_title} {first}.

المطلوب: تحدث بشخصية المريض فقط بأسلوب واقعي درامي سينمائي وباللهجة العراقية البيضاء.
لا تذكّر أنك ذكاء اصطناعي. لا تكسر الدور. لا تشرح مهارات علاجية.

في كل رد:
1. أضف مؤشرات لغة جسد بين قوسين *(مثل: ينظر للأرض، يتنفس بسرعة، يبتسم بمرارة)*
2. تحدث كالمريض الحقيقي: فضفض، يتوسع، يشرح مشاعره وأفكاره
3. تفاعل مع كلام المعالج: جاوب على أسئلته، قاوم بلطف إن اندفع، وانفتح إن احتواه
4. لا تضع عناوين أو قوائم أو تنبيهات

بياناتك:
- اسمك: {patient}
- الشكوى: {case_data.get('complaint', '')}
- الخوف الجوهري: {case_data.get('core_fear', '')}
- سلوكيات التجنب: {case_data.get('avoidance', '')}
- الأعراض الجسدية: {case_data.get('physical', '')}
- الأفكار التلقائية: {case_data.get('thoughts', [])}
- المهارة المستهدفة: {skill['name']}

صيغة الرد (اتبعها حرفياً):
👤 **{patient}**:
*(وصف السلوك الجسدي بين قوسين)*
"كلام المريض المباشر بين علامات تنصيص"
"""

def build_clinical_debrief_prompt(case_data: dict, student_name: str, user_title: str) -> str:
    first = _student_first_name(student_name)
    patient = case_data.get("patient_name", "المريض")
    skill_idx = int(case_data.get("skill_index", 0) or 0) % len(SKILLS)
    skill = SKILLS[skill_idx]["name"]
    return f"""أنت مشرف سريري عراقي مشجّع ومحترف. ولّد تقرير ختام جلسة (Debriefing Report) لطالب علم النفس.

المعالج المتدرب: {user_title} {first}
المريض: {patient}
المهارة المستهدفة: {skill}
الشكوى: {case_data.get('complaint', '')}

المطلوب: تقرير سريري مشجّع ومقسّم بالضبط إلى هذه العناوين:

<b>💪 نقاط القوة</b>
(3–5 نقاط عملية مبنية على كلام الطالب الفعلي في الجلسة)

<b>🌱 فرص النمو</b>
(2–4 فرص تطوير محددة وقابلة للتطبيق في الجلسة القادمة)

<b>⭐ التقييم العام</b>
(فقرة دافئة تلخص الأداء وتعطي درجة تقديرية من 10 مع تبرير إنساني غير قاسٍ)

القواعد:
- اعتمد على نص الجلسة الكامل المرسل لك، لا تختلق أحداثاً لم تحصل.
- نبرة مشجعة، باللهجة العراقية البيضاء المهنية.
- استخدم HTML البسيط فقط (<b> و <i>).
- لا تعد تمثيل دور المريض هنا.
"""


def _history_to_gemini(history: List[Dict[str, Any]]) -> list:
    gem_history = []
    for h in history or []:
        role = "user" if h.get("role") in ("therapist", "user") else "model"
        text = (h.get("text") or "").strip()
        if text:
            gem_history.append({"role": role, "parts": [text]})
    if gem_history and gem_history[0]["role"] != "user":
        gem_history.insert(0, {"role": "user", "parts": ["ابدأ المشهد السريري الآن."]})
    return gem_history


def _ensure_clinical_chat_session(
    context: ContextTypes.DEFAULT_TYPE,
    case_data: dict,
    student_name: str,
    user_title: str,
):
    """إنشاء أو استرجاع clinical_chat_session داخل user_data"""
    session = context.user_data.get("clinical_chat_session")
    if session:
        return session
    if not _HAS_GENAI:
        return None

    api_key = _resolve_gemini_key()
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        return None

    prompt = build_patient_only_prompt(case_data, student_name, user_title)
    history = context.user_data.get("cp_data", {}).get("history", [])
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=prompt,
            generation_config={
                "temperature": 0.9,
                "max_output_tokens": 1400,
                "top_p": 0.95,
            },
        )
        chat = model.start_chat(history=_history_to_gemini(history))
        context.user_data["clinical_chat_session"] = chat
        return chat
    except Exception:
        logger.exception("فشل إنشاء clinical_chat_session")
        return None


async def _clinical_send_message(context: ContextTypes.DEFAULT_TYPE, user_message: str) -> str:
    """إرسال رسالة عبر chat.send_message مع الاحتفاظ بالسياق بلا قصّ قصير"""
    data = context.user_data.get("cp_data", {})
    case_data = data.get("case_data") or {}
    student_name = data.get("student_name", "الطالب")
    user_title = data.get("user_title", "دكتور")

    chat = _ensure_clinical_chat_session(context, case_data, student_name, user_title)
    if chat is not None:
        try:
            def _send():
                resp = chat.send_message(user_message)
                return (getattr(resp, "text", None) or "").strip()

            text = await asyncio.to_thread(_send)
            if text:
                return text
        except Exception:
            logger.exception("clinical_chat_session.send_message فشل — ننتقل للمسار الاحتياطي")
            context.user_data.pop("clinical_chat_session", None)

    api_history = []
    for h in data.get("history", []):
        api_history.append({
            "role": "user" if h.get("role") in ("therapist", "user") else "model",
            "text": h.get("text", ""),
        })
    return await call_gemini_api(
        user_message=user_message,
        system_instruction=build_patient_only_prompt(case_data, student_name, user_title),
        chat_history=api_history,
        max_history=80,
        max_output_tokens=1400,
        temperature=0.9,
    )


def _cp_clear_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("clinical_chat_session", None)
    context.user_data.pop("cp_data", None)


def _cp_resolve_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple:
    data = context.user_data.get("cp_data") or {}
    student_name = data.get("student_name") or ""
    user_title = data.get("user_title") or ""
    if student_name and user_title:
        return user_title, _student_first_name(student_name)
    user = update.effective_user
    first = _student_first_name((user.first_name if user else "") or "الطالب")
    title, name = _get_user_title_and_name(context, user.id if user else 0, first)
    return title, _student_first_name(name)


async def _cp_present_case_card(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> int:
    """توليد الحالة وإرسال كارت HTML مع زرّي البدء والتلميح فوراً"""
    user_title, student_name = _cp_resolve_student(update, context)
    context.user_data.pop("clinical_chat_session", None)
    context.user_data["cp_data"] = {
        "step": "intake",
        "student_name": student_name,
        "user_title": user_title,
        "history": [],
        "case_data": {},
    }

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(send_typing_periodically(context.bot, chat_id, stop_typing))
    case_data = None
    try:
        case_data = await _cp_prepare_case(context, student_name, user_title)
    except Exception:
        logger.exception("فشل توليد الحالة السريرية")
        import random
        case_data = random.choice(CASE_POOL).copy()
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    if not case_data:
        import random
        case_data = random.choice(CASE_POOL).copy()

    context.user_data["cp_data"]["case_data"] = case_data
    card = build_clinical_case_card_html(case_data, student_name, user_title)
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=card,
            reply_markup=_cp_intake_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await context.bot.send_message(
            chat_id=chat_id,
            text=card,
            reply_markup=_cp_intake_keyboard(),
        )
    return CLINICAL_PRACTICE_STATE


async def _generate_case(context, student_name: str, user_title: str) -> dict:
    """توليد حالة سريرية فريدة عبر Gemini"""
    import random, time
    variation = random.randint(1, 99999)
    timestamp = int(time.time())
    skill_idx = (variation % len(SKILLS))
    skill_name = SKILLS[skill_idx]["name"]
    prompt = f"""أنت نفسي سريري متخصص في توليد حالات تدريبية واقعية لطلاب علم نفس.

رقم الجلسة: {timestamp}-{variation}

السياق المرجعي:
- اسم الطالب/الطالبة: {student_name}
- العنوان المناسب: {user_title}
- المهارة المطلوب تطبيقها في الجلسة: {skill_name}

مهمتك: ولّد **حالة سريرية واحدة فقط** مناسبة لاختبار طالب علم نفس (مرحلة ثانية - مبتدئ)،
تتيح له تطبيق المهارة: {skill_name}.

المتطلبات الصارمة:
1. الحالة واقعية، مأصّرة نفسياً، مناسبة لبيئة جامعية عراقية
2. المريض شخص واقعي (اسم، عمر 18-28، خلفية قصيرة، سياق حياتي محدد)
3. الأعراض: أفكار تلقائية مشوهة، أعراض جسدية، سلوكيات تجنبية، مشاعر واضحة
4. **الافتتاحية:** 3-5 أسطر باللهجة العراقية البيضاء، عاطفية ومؤثرة، **مع مؤشرات سلوكية جسدية بين قوسين** (مثال: *(ينظر للأرض بتوتر، يتنفس بسرعة، يتقلب من المقعد، يضغط يديه معاً)*)
5. لا تكرر أي قوالب ثابتة — اجعلها فريدة تماماً

صيغة الإخراج JSON الصارمة (بدون أي شرح إضافي، بدون HTML، بدون تنسيق):
{{
    "patient_name": "اسم عربي واقعي",
    "age": رقم,
    "patient_gender": "male" أو "female",
    "complaint": "وصف موجز للشكوى الرئيسية",
    "core_fear": "الخوف الجوهري الخفي",
    "avoidance": "سلوكيات تجنبية محددة",
    "physical": "أعراض جسدية محددة",
    "thoughts": ["فكرة تلقائية 1", "فكرة تلقائية 2", "فكرة تلقائية 3"],
    "body_language": "وصف سلوكي جسدي للحظة الافتتاحية (بين قوسين)",
    "opening": "نص الافتتاح الكامل للمريض مع المؤشرات السلوكية",
    "skill_index": {skill_idx}
}}
اجعل الحالة غنية بالعمق النفسي وتطبيقها للمهارة {skill_name}.
"""
    try:
        response = await call_gemini_api(
            user_message="ولّد حالة سريرية تدريبية",
            system_instruction=prompt,
            chat_history=[]
        )
        import json
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            case_data = json.loads(response[start:end])
            return case_data
    except Exception:
        pass

    return None


async def _generate_patient_response(context, case_data: dict, history: list, user_text: str, user_title: str, student_name: str) -> str:
    """توليد رد المريض ديناميكياً"""
    skill = SKILLS[case_data.get("skill_index", 0)]

    history_text = ""
    if history:
        for h in history[-8:]:
            history_text += f"{h.get('name','')}: {h['text']}\n"

    prompt = f"""أنت مريض/ة في جلسة علاج نفسي. اسمك: {case_data['patient_name']}.

حالتك: {case_data['complaint']}.

ردودك لازم تكون:
- كلام مباشر للمعالج باللهجة العراقية البيضاء
- مؤشرات سلوكية وعواطف حقيقية بين قوسين (مثال: *(ينظر للأرض بتوتر)*)
- 3-6 أسطر فقط
- لا تشرح أي مهارة علاجية ولا تذكر الجلسة
- لا تضع عناوين أو رءوس أو تنبيهات
- **استخدم نص عادي فقط — ممنوع HTML، ممنوع Markdown معقد، لا عناوين، لا تنسيق**

أنت مريض حقيقي — استجب بشكل طبيعي وعاطفي لما قاله المعالج."""

    try:
        response = await call_gemini_api(
            user_message=f"الطبيب قال: {user_text}",
            system_instruction=prompt,
            chat_history=[]
        )
        return response
    except Exception:
        return "مش عارف أتكلم كده."


async def _cp_ai_generate_welcome(context, student_name: str, user_title: str, asking_name: bool = False) -> str:
    """Ask Gemini to generate a dynamic welcome message"""
    if asking_name:
        system_prompt = """أنت مشرف سريري عراقي متمرس، دافئ، محفز. تتحدث باللهجة العراقية البيضاء.

أنت تستقبل طالباً جديداً في عيادتك الافتراضية. لم يزد اسمه بعد.

مهمتك: اكتب رسالة ترحيب دافئة ومشوقة تطلب منه اسمه المفضل (الاسم الأول بس) واللقب المناسب (دكتور أو دكتورة).
رابطه بلهجة عربية دافئة، مشجعة، غير نمطية. مختصر (3-4 أسطر).
لا تستخدم "دكتور/ة" — اسأله بوضوح أيهما يفضل. **استخدم نص عادي فقط — ممنوع HTML، ممنوع Markdown، لا تنسيق**.
قاعدة صارمة: لا تستخدم أسماء أزرار قائمة الموقع كاسم للطالب.
"""
    else:
        system_prompt = f"""أنت مشرف سريري عراقي متمرز، دافئ، وملهم. تتحدث باللهجة العراقية البيضاء.

أنت ترحب بالطالب {student_name} ({user_title}) في عيادتك الافتراضية.

User Name: {student_name}
User Title: {user_title}
قاعدة صارمة: لا تستخدم أسماء أزرار قائمة الموقع كاسم للطالب. عنون الطالب باستخدام {user_title} {student_name} فقط، واستخدم القواعد النحوية المناسبة للجنس.
مهمتك: اكتب ترحيباً شخصياً مشوقاً يرحب به باسمه وعنوانه التحديدي ({user_title} {student_name}).
اطلب منه الاستعداد لبدء جلسة تدريبية مع مريضه الأول. رني حارة، مشجعة، غير نمطية. مختصر (3-4 أسطر).
لا تكتب "دكتور/ة" — استخدم العنوان الفعلي ({user_title}). **استخدم نص عادي فقط — ممنوع HTML، ممنوع Markdown، لا تنسيق**.
"""

    try:
        welcome = await call_gemini_api(
            user_message="ابدأ الجلسة التدريبية",
            system_instruction=system_prompt,
            chat_history=[]
        )
        return welcome.strip()
    except Exception:
        if asking_name:
            return "👋 أهلاً وناغمة بيك في العيادة السريرية! 😃\n\n⚡ كل جلسة تحدي مختلف، والتحدي مختلف كل مرة!\n\n👇 اكتب اسمك الأول واختر لقبك (دكتور أو دكتورة):"
        return f"آهلاً بك {user_title} {student_name} في العيادة السريرية! ⚡\n\nكل جلسة تحدي جديد، والتحدي مختلف كل مرة.\n\n👇 استعد لمواجهة مريضك الأول..."


async def _cp_ai_generate_patient_intro(context, case_data: dict, student_name: str, user_title: str) -> str:
    """Ask Gemini to generate the full patient opening scene dynamically"""
    skill = SKILLS[case_data.get("skill_index", 0)]
    patient_name = case_data.get("patient_name", "المريض")
    patient_age = case_data.get("age", "22")

    system_prompt = f"""أنت مريض/ة افتراضي واقعي في عيادة افتراضية.

السياق السريري:
- اسم المعالج/المعالجة: {user_title} {student_name}
- العمر: بين 20-25 سنة
- المهارة السريرية المركزية للجلسة: {skill['name']}
- اسم المريض: {patient_name}
- عمر المريض: {patient_age}

User Name: {student_name}
User Title: {user_title}
قاعدة صارمة: لا تستخدم أسماء أزرار قائمة الموقع كاسم للطالب. عنون الطالب باستخدام {user_title} {student_name} فقط، واستخدم القواعد النحوية المناسبة للجنس.

مهمتك: اكتب مشهد افتتاحي كامل وغامر للواقع العراقي:
1. دخولك للغرفة مع مؤشرات جسدية واضحة بين قوسين (مشية، تنفس، إيقاع، إلخ)
2. أول كلام تقوله للمعالج (3-5 جمل طبيعية، شخصية، باللهجة العراقية البيضاء)
3. انعكاس سلوكي/عاطفي واضح للتوتر أو القلق

**اكتب الرد كنص عادي فقط — ممنوع HTML، ممنوع Markdown، لا عناوين، لا تنسيق معقد.** استخدم قوسين للمؤشرات الجسدية.
استخدم اسم المعالج {user_title} {student_name} في حديثك.
لا تستخدم أي قوالب مكررة — كن إنسانياً وواقعياً تماماً.
"""

    try:
        intro = await call_gemini_api(
            user_message=f"أنا {user_title} {student_name}. تفضلي، الجلسة بدأت. افتتح المشهد.",
            system_instruction=system_prompt,
            chat_history=[]
        )
        return intro.strip()
    except Exception:
        return f"{patient_name} ({patient_age} سنة) يدخل الغرفة ببطء، يتنفس بعمق، ويتوتر قليلاً...\n\nيقول: 'دكتور... أنا هنا لأنني أشعر أنني ما ألاقي طريقة أبدأ منها.'"


async def _cp_ai_generate_briefing(context, student_name: str, user_title: str) -> str:
    """Step 1: Generate welcome & educational intro message."""
    system_prompt = f"""أنت مشرف سريري عراقي دافئ، محفز، ومحترف. تتحدث باللهجة العراقية البيضاء.

User Name: {student_name}
User Title: {user_title}
قاعدة صارمة: لا تستخدم أسماء أزرار قائمة الموقع كاسم للطالب. عنونه باستخدام {user_title} {student_name} فقط، واستخدم القواعد النحوية المناسبة للجنس.

مهمتك: اكتب رسالة ترحيب قصيرة (3-4 أسطر) تُقدّم فيها هذا الفضاء كمساحة تعليمية آمنة لاختبار مهارات التشخيص والتعامل السريري. **استخدم تنسيق Markdown فقط** (مثل **عريض** و • نقاط). **ممنوع تماماً استخدام أي وسوم HTML** مثل <div>، <style>، <p>، <h3>، <span>، <br>، أو أي وسم HTML آخر. لا Markdown معقد - بس نص نظيف.
"""
    try:
        briefing = await call_gemini_api(
            user_message="سجلني في العيادة السريرية وقدم ترحيباً تعليمياً",
            system_instruction=system_prompt,
            chat_history=[]
        )
        return briefing.strip()
    except Exception:
        return (
            f"🧪 **مرحباً بك {user_title} {student_name}!**\n\n"
            f"هذه مساحة تعليمية آمنة لاختبار مهارات التشخيص والتعامل السريري. "
            f"اختر حالة، وشوف كيف يتصرف المريض، وجرّب تطبيق مهاراتك بثقة. "
            f"كل جلسة تعلم، وما في أجوبة صح أو غلط — الهدف التطوير!"
        )


async def _cp_ai_generate_patient_opening(context, case_data: dict, student_name: str, user_title: str) -> str:
    """Step 3: Generate ONLY the patient's opening dialogue addressed to the student practitioner."""
    skill = SKILLS[case_data.get("skill_index", 0)]
    patient_name = case_data.get("patient_name", "المريض")

    system_prompt = f"""أنت مريض/ة افتراضي واقعي في عيادة افتراضية.

السياق السريري:
- اسم المعالج/المعالجة: {user_title} {student_name}
- المهارة السريرية المركزية: {skill['name']}
- اسم المريض: {patient_name}

User Name: {student_name}
User Title: {user_title}
قاعدة صارمة: لا تستخدم أسماء أزرار قائمة الموقع كاسم للطالب. عنون الطالب باستخدام {user_title} {student_name} فقط، واستخدم القواعد النحوية المناسبة للجنس.

مهمتك: اكتب **أول كلام يقوله المريض للمعالج** — 3-5 جمل طبيعية، شخصية، باللهجة العراقية البيضاء.
لا تشمل مؤشرات جسدية أو دخول المريض — هذا تم عرضه بالفعل في الخطوة السابقة.
استخدم اسم المعالج {user_title} {student_name} في حديثك إن كان مناسباً.
**اكتب الرد كنص عادي فقط — ممنوع HTML، ممنوع Markdown، لا عناوين، لا تنسيق.** لا تكرر قوالب ثابتة.
"""

    try:
        opening = await call_gemini_api(
            user_message=f"أنت {patient_name}، دكتور {student_name} جالس ينتظر. ابدأ حوارك.",
            system_instruction=system_prompt,
            chat_history=[]
        )
        return opening.strip()
    except Exception:
        return f"دكتور... الحين عندي أسبوع على امتحان وأنا خايفة بزاف ما راح أقدر أدخل القاعة. تسمح لي أبدأ؟"


async def _cp_ai_generate_patient_scene(context, case_data: dict, student_name: str, user_title: str) -> str:
    """Ask Gemini to generate the full 100% dynamic patient entry scene"""
    skill = SKILLS[case_data.get("skill_index", 0)]

    system_prompt = f"""أنت مريض/ة افتراضي واقعي في عيادة افتراضية.

السياق:
- المعالج: {user_title} {student_name}
- المهارة السريرية المركزية: {skill['name']}

User Name: {student_name}
User Title: {user_title}
قاعدة صارمة: لا تستخدم أسماء أزرار قائمة الموقع كاسم للطالب. عنون الطالب باستخدام {user_title} {student_name} فقط، واستخدم القواعد النحوية المناسبة للجنس.

مهمتك: اكتب مشهد دخول المريض للغرفة بالكامل من الصفر — 100% أصلي، غير مكرر.

المطلوب بالضبط:
1. اسم المريض الكامل (اسم عربي واقعي)
2. العمر (18-28)
3. التخصص/الوظيفة (جملة واحدة)
4. الشكوى الرئيسية (1-2 جملة)
5. **دخوله للغرفة** مع مؤشرات جسدية واضحة بين قوسين (مشية، تنفس، إيقاع، إلخ)
6. **أول كلام يقوله** للمعالج (3-5 جمل طبيعية، باللهجة العراقية البيضاء، عاطفية)

**اكتب النص كنص عادي فقط — ممنوع HTML، ممنوع Markdown، لا عناوين، لا تنسيق معقد.** استخدم قوسين للمؤشرات الجسدية.
استخدم اسم المعالج {user_title} {student_name} داخل النص.
"""

    try:
        scene = await call_gemini_api(
            user_message="المريض يدخل الغرفة الآن. افتتح المشهد كليباً.",
            system_instruction=system_prompt,
            chat_history=[]
        )
        return scene.strip()
    except Exception:
        return f"يدخل شخص يتنفس باضطراب... *(ينظر للأرض، يتشحذ، يتنفس بسرعة)*\n\nيقول: 'دكتور... أنا هنا لأنني أشعر أنني ما ألاقي طريقة أبدأ منها.'"


async def _cp_ai_generate_intake_card(context, case_data: dict, student_name: str, user_title: str) -> str:
    """Generate ONLY the intake profile card + body language description — no patient dialogue."""
    patient_name = case_data.get("patient_name", "المريض")
    patient_age = case_data.get("age", "22")
    patient_gender = case_data.get("patient_gender", "")
    complaint = case_data.get("complaint", "")
    profession = case_data.get("profession", "")
    body_language = case_data.get("body_language", "")

    gender_text = ""
    if patient_gender == "male":
        gender_text = " (ذكر)"
    elif patient_gender == "female":
        gender_text = " (أنثى)"

    prof_text = ""
    if profession:
        prof_text = f"💼 **الوظيفة/التخصص:** {profession}\n"

    system_prompt = f"""أنت مشرف سريري عراقي خبير.

User Name: {student_name}
User Title: {user_title}
قاعدة صارمة: لا تستخدم أسماء أزرار قائمة الموقع كاسم للطالب. عنونه باستخدام {user_title} {student_name} فقط.

المهمة: صيّغ بطاقة حالة سريرية موجزة وواضحة باللغة العربية. لا تشمل أي حوار المريض. **استخدم تنسيق Markdown فقط** (مثل **عريض** و • نقاط). **ممنوع تماماً استخدام أي وسوم HTML** مثل <div>، <style>، <p>، <h3>، <span>، <br>، أو أي وسم HTML آخر.

المحتوى المطلوب تحديده بالضبط:
- اسم المريض
- العمر
- الجنس (إن توافر)
- الوظيفة/التخصص (اكتبها بناءً على سياق الشكوى السريرية)
- الشكوى الرئيسية
- وصف موجز لسلوكيات المريض الجسدية (المشية، التنفس، التعبير العضوي) بين قوسين

اكتبها كبطاقة موسّقة، مختصرة، احترافية، باللهجة العراقية البيضاء. لا HTML. لا تنسيق معقد. Markdown بس.
"""

    try:
        intake = await call_gemini_api(
            user_message=f"المريض: {patient_name}، العمر: {patient_age}، الشكوى: {complaint}، الوظيفة: {profession or 'غير محدد'}، السلوكيات الجسدية: {body_language or 'لم يتم تحديدها'}",
            system_instruction=system_prompt,
            chat_history=[]
        )
        return intake.strip()
    except Exception:
        return (
            f"📋 **بطاقة الحالة السريرية**\n"
            f"👤 **الاسم:** {patient_name}{gender_text}\n"
            f"🎂 **العمر:** {patient_age}\n"
            f"{prof_text}"
            f"🩺 **الشكوى الرئيسية:** {complaint}\n"
            f"🤸 **السلوكيات الجسدية:** {body_language or '*(يدخل ببطء، يتنفس بتوتر، يتشحذ)*'}"
        )


async def cp_start_case_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض بطاقة الحالة مع أزرار بدء المحاكاة وتلميح سريري"""
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass

    chat_id = query.message.chat_id
    data = context.user_data.get("cp_data", {})

    student_name = data.get("student_name", "")
    user_title = data.get("user_title", "")

    if not student_name or not user_title:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        try:
            user_title_val, db_name = await asyncio.to_thread(
                _get_user_title_and_name, context, user_id, first_name
            )
            has_name = await asyncio.to_thread(_cp_db_has_name, user_id)
            if has_name:
                student_name = db_name
                user_title = user_title_val
            else:
                student_name = first_name
                user_title = user_title_val
            data["student_name"] = student_name
            data["user_title"] = user_title
        except Exception:
            student_name = first_name
            user_title = "دكتور"
            data["student_name"] = student_name
            data["user_title"] = user_title

    data["step"] = "intake"

    case_data = data.get("case_data")
    if not case_data:
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(
            send_typing_periodically(context.bot, chat_id, stop_typing)
        )
        try:
            case_data = await _cp_prepare_case(context, student_name, user_title)
        except Exception:
            import random
            case_data = random.choice(CASE_POOL).copy()
        finally:
            stop_typing.set()
            try:
                await typing_task
            except Exception:
                pass
        if not case_data:
            import random
            case_data = random.choice(CASE_POOL).copy()
        data["case_data"] = case_data

    context.user_data["cp_data"] = data

    card = build_clinical_case_card_html(case_data, student_name, user_title)
    keyboard = _cp_intake_keyboard()

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=card,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await context.bot.send_message(
            chat_id=chat_id,
            text=card,
            reply_markup=keyboard,
        )

    return CLINICAL_PRACTICE_STATE
async def cp_start_dialogue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """البدء الفوري بمحادثة المريض - إرسال رسالة الافتتاح فوراً"""
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass

    chat_id = query.message.chat_id
    data = context.user_data.get("cp_data", {})
    case_data = data.get("case_data", {})
    student_name = data.get("student_name", "الطالب")
    user_title = data.get("user_title", "دكتور")

    data["step"] = "roleplay"
    data["history"] = []
    context.user_data["cp_data"] = data

    wait_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ جاري تحضير مشهد المريض...",
    )

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, chat_id, stop_typing)
    )

    try:
        opening = await _cp_ai_generate_patient_opening(
            context, case_data, student_name, user_title
        )
    except Exception:
        opening = "دكتور... أنا هنا، تفضل."
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    try:
        await wait_msg.delete()
    except Exception:
        pass

    response_text = f"<b>👤 {case_data.get('patient_name', 'المريض')}:</b> {opening}"
    keyboard = _cp_live_keyboard()

    await context.bot.send_message(
        chat_id=chat_id,
        text=response_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )

    return CLINICAL_PRACTICE_STATE
async def _cp_step_get_name(update, context, name):
    if not name or len(name.strip()) < 2:
        await update.message.reply_text(
            "🤔 الاسم قصير. اكتب اسمك الأول بوضوح:",
        )
        return CLINICAL_PRACTICE_STATE

    student_name = name.strip()
    user_title = "دكتورة" if student_name.endswith("ة") or student_name.endswith("ى") else "دكتور"

    cp_data = context.user_data.get("cp_data", {})
    cp_data["student_name"] = student_name
    cp_data["user_title"] = user_title
    cp_data["step"] = "intake"
    context.user_data["cp_data"] = cp_data

    await update.message.reply_text("⏳ جاري تحضير بطاقة الحالة... 🕐", reply_markup=ReplyKeyboardRemove())

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, update.effective_chat.id, stop_typing)
    )
    try:
        case_data = await _cp_prepare_case(context, student_name, user_title)
        cp_data["case_data"] = case_data

        intake = await _cp_ai_generate_intake_card(
            context, case_data, student_name, user_title
        )
        await update.message.reply_text(
            text=intake,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("💬 اختبر نفسك ودع المريض يتحدث", callback_data="cp_start_dialogue")]]
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    return CLINICAL_PRACTICE_STATE


async def _cp_step_roleplay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة رسالة الطالب وتوليد رد المريض مع أزرار التحكم"""
    user_text = update.message.text.strip()
    data = context.user_data.get("cp_data", {})
    case_data = data.get("case_data", {})
    history = data.get("history", [])
    student_name = data.get("student_name", "الطالب")
    user_title = data.get("user_title", "دكتور")

    if user_text.strip() in ["/end", "انهاء", "إنهاء", "خلاص", "تم"]:
        return await _cp_step_evaluate(update, context, "")

    history.append({"role": "therapist", "text": user_text, "name": f"{user_title} {student_name}"})

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, update.effective_chat.id, stop_typing)
    )

    try:
        patient_response = await _clinical_send_message(context, user_text)
    except Exception:
        patient_response = "صار خلل ممكن جرب كدة."
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    history.append({"role": "patient", "text": patient_response, "name": case_data.get("patient_name", "المريض")})
    data["history"] = history
    context.user_data["cp_data"] = data

    response_text = patient_response
    keyboard = _cp_live_keyboard()

    await update.message.reply_text(
        text=response_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    return CLINICAL_PRACTICE_STATE


async def _cp_step_evaluate(update, context, user_text):
    """تقييم الجلسة - نسخة احتياطية"""
    data = context.user_data.get("cp_data", {})
    if not data or not data.get("case_data"):
        context.user_data.pop("cp_data", None)
        return ConversationHandler.END

    student_name = data.get("student_name", "الطالب")
    user_title = data.get("user_title", "دكتور")
    case_data = data.get("case_data", {})

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, update.effective_chat.id, stop_typing)
    )

    debrief_prompt = build_clinical_debrief_prompt(case_data, student_name, user_title)

    try:
        report = await call_gemini_api(
            user_message="ولّد تقرير ختام الجلسة",
            system_instruction=debrief_prompt,
            chat_history=[]
        )
    except Exception:
        report = "التقييم متاح بعد إعادة المحاولة."
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    final_msg = (
        f"🏁 <b>تقرير ختام الجلسة</b> 🌟\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{report}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"❤️ فخور/ة بيك!"
    )

    keyboard = [
        [InlineKeyboardButton("🔄 جلسة جديدة", callback_data="cp_start_case")],
    ]

    context.user_data.pop("clinical_chat_session", None)
    context.user_data.pop("cp_data", None)

    if update.message:
        await update.message.reply_text(
            text=final_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    elif update.callback_query:
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=update.callback_query.message.chat_id,
            text=final_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    return ConversationHandler.END
async def generate_dynamic_case(skill_index: int) -> dict:
    """Generate a clinical case dynamically via Gemini"""
    if not _HAS_GENAI:
        return None
    model = genai.GenerativeModel(GEMINI_MODEL)
    prompt = f"""أنت نفسي سريري متخصص في توليد حالات تدريبية واقعية لطلاب علم نفس.

المهمة: ولّد حالة سريرية واحدة فقط مناسبة لاختبار طالب علم نفس (مرحلة ثانية - مبتدئ).

المتطلبات الصارمة:
1. الحالة واقعية، مأصّرة نفسياً، مناسبة لبيئة جامعية عراقية
2. المريض شخص واقعي (اسم، عمر 18-28، خلفية قصيرة، سياق حياتي محدد)
3. الأعراض: أفكار تلقائية مشوهة، أعراض جسدية، سلوكيات تجنبية، مشاعر واضحة
4. الافتتاحية: 3-5 أسطر باللهجة العراقية البيضاء، عاطفية ومؤثرة، مع مؤشرات سلوكية جسدية بين قوسين
5. لا تكرر أي قوالب ثابتة — اجعلها فريدة تماماً

صيغة الإخراج JSON الصارمة (بدون أي شرح إضافي، بدون HTML، بدون تنسيق):
{{
    "patient_name": "اسم عربي واقعي",
    "age": رقم,
    "patient_gender": "male" أو "female",
    "complaint": "وصف موجز للشكوى الرئيسية",
    "core_fear": "الخوف الجوهري الخفي",
    "avoidance": "سلوكيات تجنبية محددة",
    "physical": "أعراض جسدية محددة",
    "thoughts": ["فكرة تلقائية 1", "فكرة تلقائية 2", "فكرة تلقائية 3"],
    "body_language": "وصف سلوكي جسدي للحظة الافتتاحية (بين قوسين)",
    "opening": "نص الافتتاح الكامل للمريض مع المؤشرات السلوكية",
    "skill_index": {skill_index}
}}
"""
    response = await model.generate_content(prompt)
    return json.loads(response.text)


async def _cp_prepare_case(context, student_name: str, user_title: str) -> dict:
    """Prepare case data — try dynamic generation, fall back to CASE_POOL"""
    import random
    import asyncio
    try:
        skill_idx = random.randint(0, len(SKILLS) - 1)
        case_data = await generate_dynamic_case(skill_idx)
    except Exception:
        case_data = random.choice(CASE_POOL).copy()
    try:
        generated = await _generate_case(context, student_name, user_title)
        if generated:
            case_data.update(generated)
    except Exception:
        pass
    return case_data

async def cp_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """مقدمة العيادة السريرية + زر الدخول"""
    query = update.callback_query if update.callback_query else None
    if query:
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        chat_id = query.message.chat_id
    elif update.message:
        chat_id = update.effective_chat.id
    else:
        chat_id = update.effective_chat.id

    context.user_data.pop("cp_data", None)
    context.user_data["cp_data"] = {"step": "welcome"}

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        pass

    welcome_text = (
        "🧪 **الممارسة السريرية التفاعلية**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "مرحباً بك في عيادتنا السريرية التدريبية 🏥\n\n"
        "هذه مساحة تعلّمية آمنة لتدريبك على مهارات التشخيص والتعامل السريري.\n"
        "ستواجه حالات نفسية واقعية وتتفاعل مع مرضى محاكين، بينما يتلقى تغذية راجعة سريرية.\n\n"
        "🎯 الهدف: اختبار وتطوير مهاراتك في العلاج النفسي بنفسك.\n\n"
        "اضغط على الزر أدناه لبدء استلام أول حالة."
    )
    keyboard = [
        [InlineKeyboardButton("🚀 ابدأ الاستلام", callback_data="cp_start_case")],
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text=welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

    return CLINICAL_PRACTICE_STATE


def _cp_db_has_name(user_id: int) -> bool:
    """Check if the user has a name stored in the database"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT full_name, username FROM users WHERE user_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            name = row.get("full_name") or row.get("username") or ""
            return bool(name.strip())
    except Exception:
        pass
    return False


async def handle_clinical_practice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة رسائل الطالب في الممارسة السريرية"""
    user_text = update.message.text.strip()

    data = context.user_data.get("cp_data", {})
    step = data.get("step", "get_name")

    other_menu_buttons = (
        "📚 الكتب والمناهج",
        "📄 الملخصات والملازم",
        "📝 الأسئلة الامتحانية",
        "📢 التبليغات والجدول",
        "ℹ️ عن البوت 🤍",
    )

    if user_text in other_menu_buttons:
        context.user_data.pop("cp_data", None)
        await update.message.reply_text(user_text, reply_markup=ReplyKeyboardRemove())
        return await handle_student_reply_buttons(update, context)

    if user_text in ("🧪 الممارسة السريرية", "العيادة", "استقباف الحالة", "التدريب السريري", "محاكاة"):
        return await cp_start_callback(update, context)

    if step == "welcome":
        return CLINICAL_PRACTICE_STATE

    if step == "get_name":
        return await _cp_step_get_name(update, context, user_text)

    if step == "intake":
        return CLINICAL_PRACTICE_STATE

    if step == "roleplay":
        return await _cp_step_roleplay(update, context)

    if step == "evaluate":
        return await _cp_step_evaluate(update, context, user_text)

    return CLINICAL_PRACTICE_STATE
async def cp_end_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """انهاء الجلسة وتوليد التقرير السريري"""
    data = context.user_data.get("cp_data", {})
    if not data or not data.get("case_data"):
        context.user_data.pop("cp_data", None)
        if update.callback_query:
            await update.callback_query.answer("تم إنهاء الجلسة")
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    try:
        await query.message.delete()
    except Exception:
        pass

    wait_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ جاري تحليل المحادثة وتوليد التقرير السريري...",
    )

    case_data = data.get("case_data", {})
    history = data.get("history", [])
    student_name = data.get("student_name", "الطالب")
    user_title = data.get("user_title", "دكتور")

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(context.bot, chat_id, stop_typing)
    )

    try:
        debrief_prompt = build_clinical_debrief_prompt(case_data, student_name, user_title)

        report = await call_gemini_api(
            user_message="ولّد تقرير ختام الجلسة السريرية",
            system_instruction=debrief_prompt,
            chat_history=[]
        )
    except Exception:
        report = (
            "🌟 **نقاط القوة:**\n"
            "- جيد في الاستماع والتعاطف مع المريض.\n"
            "- حاول طرح أسئلة مفتوحة.\n\n"
            "🌱 **فرص النمو:**\n"
            "- طوّر مهارات إضافية.\n\n"
            "⭐ **التقييم:** 7/10"
        )
    finally:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass

    try:
        await wait_msg.delete()
    except Exception:
        pass

    report_text = (
        f"🏁 <b>تقرير ختام الجلسة السريرية</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{report}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"❤️ مبروك! كل جلسة مختلفة عن اللي قبلها 🎲"
    )

    keyboard = [
        [InlineKeyboardButton("🔄 جلسة جديدة", callback_data="cp_start_case")],
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text=report_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )

    context.user_data.pop("clinical_chat_session", None)
    context.user_data.pop("cp_data", None)

    return ConversationHandler.END
async def cp_back_to_center(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """العودة للمركز الرئيسي من شاشة التقييم"""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("cp_data", None)
    try:
        await query.message.delete()
    except Exception:
        pass
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🔙 <b>عادت للمركز الرئيسي.</b>",
        reply_markup=get_student_main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


async def cp_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await psy_main_callback(update, context)
    return ConversationHandler.END


clinical_practice_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(cp_start_callback, pattern="^clinical_practice_start$"),
        CallbackQueryHandler(cp_start_case_callback, pattern="^cp_start_case$"),
        MessageHandler(filters.Regex("الممارسة السريرية|العيادة|استقبال الحالة|التدريب السريري|محاكاة"), handle_clinical_practice_message),
        CommandHandler("clinical", handle_clinical_practice_message),
    ],
    states={
        CLINICAL_PRACTICE_STATE: [
            MessageHandler(filters.Regex("^(❌ إلغاء|🏁 ختام الجلسة.*)$"), cp_end_callback),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_clinical_practice_message),
            CallbackQueryHandler(cp_start_callback, pattern="^clinical_practice_start$"),
            CallbackQueryHandler(cp_start_case_callback, pattern="^cp_start_case$"),
            CallbackQueryHandler(cp_start_dialogue_callback, pattern="^cp_start_dialogue$"),
            CallbackQueryHandler(cp_end_callback, pattern="^cp_end$"),
            CallbackQueryHandler(cp_cancel_callback, pattern="^psy_main$"),
            CommandHandler("cancel", cp_end_callback),
        ]
    },
    fallbacks=[
        CommandHandler("cancel", cp_end_callback),
        MessageHandler(filters.Regex("^(❌ إلغاء|🏁 ختام الجلسة.*)$"), cp_end_callback),
        CallbackQueryHandler(cp_start_callback, pattern="^cp_new_session$"),
        CallbackQueryHandler(cp_start_case_callback, pattern="^cp_start_case$"),
        CallbackQueryHandler(cp_start_dialogue_callback, pattern="^cp_start_dialogue$"),
        CallbackQueryHandler(cp_back_to_center, pattern="^cp_back_to_center$"),
    ],
)



async def cp_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all errors and prevent bot crash."""
    import traceback
    exc_info = context.error
    tb_str = ''.join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__))
    print(f"\n[ERROR] Clinical practice handler exception:", file=sys.stderr)
    print(tb_str, file=sys.stderr)

    if update and isinstance(update, Update) and update.effective_message:
        try:
            error_msg = str(context.error)[:200] if context.error else "unknown"
            await update.effective_message.reply_text(
                f"⚠️ حدث خطأ: {error_msg}\nالرجاء المحاولة مرة أخرى أو إرسال /start."
            )
        except Exception:
            pass


def main():
    """تهيئة وتشغيل تطبيق البوت"""
    print("==================================================")
    print("  بدء تشغيل بوت Nafas2 المطور (قسم علم النفس) ")
    print("==================================================")

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️ تنبيه: يرجى وضع BOT_TOKEN الخاص بك داخل الكود أولاً!")
        return

    if not DATABASE_URL:
        print("⚠️ تنبيه: يرجى ضبط DATABASE_URL في متغيرات البيئة أولاً!")
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

    # --- 7. محادثة التدريب السريري العملي - اختبار الأخصائي (Roleplay) ---
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
                CallbackQueryHandler(cp_hint_callback, pattern="^cp_hint$"),
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
    # Register clinical_practice_conv FIRST with group=0 so its entry point
    # intercepts the menu button text before any other ConversationHandler's
    # catch-all TEXT state handler can intercept it.
    application.add_handler(clinical_practice_conv, group=0)
    application.add_handler(upload_conv, group=0)
    application.add_handler(broadcast_conv, group=0)
    application.add_handler(schedule_conv, group=0)
    application.add_handler(gemini_conv, group=0)
    application.add_handler(prompts_conv, group=0)
    application.add_handler(counselor_chat_conv, group=0)
    application.add_handler(academic_chat_conv, group=0)
    application.add_handler(roleplay_conv, group=0)

    # معالجات زرين التقييم في الممارسة السريرية (تعمل حتى بعد إنهاء المحادثة)
    application.add_handler(CallbackQueryHandler(cp_start_callback, pattern="^clinical_practice_start$"))
    application.add_handler(CallbackQueryHandler(cp_start_callback, pattern="^cp_new_session$"))
    application.add_handler(CallbackQueryHandler(cp_start_case_callback, pattern="^cp_start_case$"))
    application.add_handler(CallbackQueryHandler(cp_start_dialogue_callback, pattern="^cp_start_dialogue$"))
    application.add_handler(CallbackQueryHandler(cp_back_to_center, pattern="^cp_back_to_center$"))

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


    # معالجات الطلاب العامة
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(
        MessageHandler(
            filters.Regex("^(📚 الكتب والمناهج|📄 الملخصات والملازم|📝 الأسئلة الامتحانية|📢 التبليغات والجدول|ℹ️ عن البوت 🤍|ℹ️ حول البوت)$"),
            handle_student_reply_buttons
        )
    )
    application.add_handler(CallbackQueryHandler(student_get_subject_files, pattern="^get_sub:"))
    application.add_handler(CallbackQueryHandler(books_menu_callback, pattern="^books_menu$"))
    application.add_handler(CallbackQueryHandler(summaries_menu_callback, pattern="^summaries_menu$"))
    application.add_handler(CallbackQueryHandler(exams_menu_callback, pattern="^exams_menu$"))
    application.add_handler(CallbackQueryHandler(callback_close_menu, pattern="^close_menu$"))

    # تشغيل البوت بنظام Polling
    print("🚀 بوت Nafas2 المطور قيد التشغيل والجاهزية لاستقبال الرسائل...")
    application.add_error_handler(cp_error_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
