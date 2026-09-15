"""
check_proc.py - فحص حالة عملية بوت Nafas2
يتحقق من تشغيل البوت واتصال قاعدة البيانات وصحته العامة.
"""

import sys
import os
import subprocess
import json
import socket
import time
from datetime import datetime

# مسار ملف النتائج
STATUS_FILE = "bot_status.json"

# ألوان للتنسيق
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_colored(text: str, color: str):
    """طباعة نص ملون"""
    print(f"{color}{text}{Colors.RESET}")


def check_process_running(process_name: str = "bot.py") -> bool:
    """التحقق من تشغيل عملية البوت"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", process_name],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        try:
            result = subprocess.run(
                ["tasklist"],
                capture_output=True,
                text=True,
                shell=True
            )
            return process_name.lower() in result.stdout.lower()
        except Exception:
            pass
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )
            return process_name.lower() in result.stdout.lower()
        except Exception:
            return False


def get_process_info(process_name: str = "bot.py") -> dict:
    """الحصول على معلومات العملية"""
    info = {"pid": None, "uptime": None, "cpu": None, "memory": None}
    try:
        result = subprocess.run(
            ["pgrep", "-f", process_name],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pid = result.stdout.strip().split("\n")[0]
            info["pid"] = int(pid) if pid.isdigit() else None

            try:
                elapsed = subprocess.run(
                    ["ps", "-o", "etime=", "-p", str(pid)],
                    capture_output=True,
                    text=True
                )
                info["uptime"] = elapsed.stdout.strip()
            except Exception:
                pass

            try:
                cpu = subprocess.run(
                    ["ps", "-o", "%cpu=", "-p", str(pid)],
                    capture_output=True,
                    text=True
                )
                info["cpu"] = cpu.stdout.strip()
            except Exception:
                pass

            try:
                mem = subprocess.run(
                    ["ps", "-o", "%mem=", "-p", str(pid)],
                    capture_output=True,
                    text=True
                )
                info["memory"] = mem.stdout.strip()
            except Exception:
                pass
    except Exception:
        pass
    return info


def check_database_connection(db_url: str = None) -> bool:
    """التحقق من اتصال قاعدة البيانات"""
    if not db_url:
        db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return False

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor, sslmode='require', connect_timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return True
    except Exception:
        return False


def check_telegram_api(bot_token: str = None) -> bool:
    """التحقق من اتصال Telegram API"""
    if not bot_token:
        bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        return False

    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        client = httpx.Client(timeout=10)
        response = client.get(url)
        client.close()
        return response.status_code == 200
    except Exception:
        return False


def check_gemini_api(api_key: str = None) -> bool:
    """التحقق من اتصال Gemini API"""
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return False

    try:
        import httpx
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "test"}]}],
            "generationConfig": {"maxOutputTokens": 5}
        }
        client = httpx.Client(timeout=10)
        response = client.post(url, json=payload, headers={"Content-Type": "application/json"})
        client.close()
        return response.status_code == 200
    except Exception:
        return False


def check_port_listening(host: str = "0.0.0.0", port: int = 8000) -> bool:
    """التحقق من استماع منفذ معين"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def save_status(status: dict):
    """حفظ حالة البوت في ملف JSON"""
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def run_checks() -> dict:
    """تشغيل جميع الفحوصات"""
    print_colored("🔍 جارٍ فحص حالة بوت Nafas2...", Colors.BLUE)
    print("=" * 55)

    bot_running = check_process_running("bot.py")
    proc_info = get_process_info("bot.py") if bot_running else {}

    db_url = os.getenv("DATABASE_URL", "")
    bot_token = os.getenv("BOT_TOKEN", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    db_ok = check_database_connection(db_url) if bot_running else False
    telegram_ok = check_telegram_api(bot_token) if bot_running else False
    gemini_ok = check_gemini_api(gemini_key) if bot_running else False

    status = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "process": {
            "running": bot_running,
            "pid": proc_info.get("pid"),
            "uptime": proc_info.get("uptime"),
            "cpu": proc_info.get("cpu"),
            "memory": proc_info.get("memory"),
        },
        "database": {
            "connected": db_ok,
            "url_masked": f"{db_url[:20]}...{db_url[-10:]}" if db_url else "غير مضبوط",
        },
        "telegram_api": {
            "reachable": telegram_ok,
            "token_set": bool(bot_token),
        },
        "gemini_api": {
            "reachable": gemini_ok,
            "key_set": bool(gemini_key),
        },
        "health": "healthy" if (bot_running and db_ok and telegram_ok) else "degraded" if bot_running else "down",
    }

    # عرض النتائج
    proc_status = "✅ قيد التشغيل" if bot_running else "❌ متوقف"
    print_colored(f"📋 العملية: {proc_status}", Colors.GREEN if bot_running else Colors.RED)
    if bot_running and proc_info.get("pid"):
        print(f"   🔢 PID: {proc_info['pid']}")
        if proc_info.get("uptime"):
            print(f"   ⏱️  وقت التشغيل: {proc_info['uptime']}")
        if proc_info.get("cpu"):
            print(f"   💻 CPU: {proc_info['cpu']}")
        if proc_info.get("memory"):
            print(f"   🧠 RAM: {proc_info['memory']}")

    db_status = "✅ متصل" if db_ok else "❌ غير متصل"
    print_colored(f"🗄️  قاعدة البيانات: {db_status}", Colors.GREEN if db_ok else Colors.RED)

    tel_status = "✅ متاح" if telegram_ok else "❌ غير متاح" if bot_running else "⏭️  مُخطى (البوت متوقف)"
    print_colored(f"📱 Telegram API: {tel_status}", Colors.GREEN if telegram_ok else Colors.RED)

    gem_status = "✅ متاح" if gemini_ok else "❌ غير متاح" if bot_running else "⏭️  مُخطى (البوت متوقف)"
    print_colored(f"🧠 Gemini API: {gem_status}", Colors.GREEN if gemini_ok else Colors.RED)

    health_color = Colors.GREEN if status["health"] == "healthy" else Colors.YELLOW if status["health"] == "degraded" else Colors.RED
    health_text = "🟢 صحي" if status["health"] == "healthy" else "🟡 متدهور" if status["health"] == "degraded" else "🔴 متوقف"
    print("=" * 55)
    print_colored(f"الحالة العامة: {health_text}", health_color)

    save_status(status)
    print(f"\n💾 تم حفظ الحالة في: {STATUS_FILE}")

    return status


def restart_bot():
    """إعادة تشغيل البوت"""
    print_colored("🔄 جارٍ إعادة تشغيل بوت Nafas2...", Colors.YELLOW)

    try:
        result = subprocess.run(
            ["systemctl", "restart", "nafas2"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print_colored("✅ تم إعادة التشغيل بنجاح!", Colors.GREEN)
        else:
            print_colored(f"⚠️ خطأ في systemctl: {result.stderr}", Colors.RED)
            print_colored("جاري المحاولة عبر تشغيل مباشر...", Colors.YELLOW)
            subprocess.Popen(
                ["python", "bot.py"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            print_colored("✅ تم التشغيل المباشر (سيستمر في الخلفية).", Colors.GREEN)
    except FileNotFoundError:
        print_colored("⚠️ systemd غير متاح. جاري التشغيل المباشر...", Colors.YELLOW)
        subprocess.Popen(
            ["python", "bot.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        print_colored("✅ تم التشغيل المباشر.", Colors.GREEN)
    except subprocess.TimeoutExpired:
        print_colored("❌ انتهت مهلة إعادة التشغيل.", Colors.RED)


def monitor(interval: int = 30):
    """مراقبة مستمرة للبوت"""
    print_colored(f"🔄 بدء المراقبة المستمرة (كل {interval} ثانية)...", Colors.BLUE)
    print("اضغط Ctrl+C للإيقاف.\n")

    consecutive_failures = 0
    try:
        while True:
            status = run_checks()

            if status["health"] == "healthy":
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print_colored(
                        f"\n⚠️ {consecutive_failures} فشلات متتالية! جاري إعادة التشغيل التلقائي...",
                        Colors.RED
                    )
                    restart_bot()
                    consecutive_failures = 0
                    time.sleep(10)

            time.sleep(interval)
    except KeyboardInterrupt:
        print_colored("\n⛔ تم إيقاف المراقبة.", Colors.YELLOW)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "restart":
            restart_bot()
        elif command == "monitor":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            monitor(interval)
        elif command == "db":
            ok = check_database_connection()
            print_colored(f"🗄️  قاعدة البيانات: {'✅ متصل' if ok else '❌ غير متصل'}", Colors.GREEN if ok else Colors.RED)
        elif command == "telegram":
            ok = check_telegram_api()
            print_colored(f"📱 Telegram API: {'✅ متاح' if ok else '❌ غير متاح'}", Colors.GREEN if ok else Colors.RED)
        elif command == "gemini":
            ok = check_gemini_api()
            print_colored(f"🧠 Gemini API: {'✅ متاح' if ok else '❌ غير متاح'}", Colors.GREEN if ok else Colors.RED)
        elif command == "status":
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    status = json.load(f)
                print(json.dumps(status, ensure_ascii=False, indent=2))
            else:
                print("لا توجد حالة محفوظة. شغّل الفحص أولاً.")
        else:
            print(f"الأمر غير معروف: {command}")
            print("الأوامر المتاحة: restart, monitor, db, telegram, gemini, status")
    else:
        run_checks()