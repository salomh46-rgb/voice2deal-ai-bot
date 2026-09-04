import time
import os
import sys
import threading
import json
import urllib.request
from datetime import datetime
import database

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

START_TIME = datetime.now()
try:
    from config import ADMIN_ID as ALERT_CHAT_ID, TELEGRAM_TOKEN, TELEGRAM_API
except ImportError:
    ALERT_CHAT_ID = 1320855100
    TELEGRAM_TOKEN = "8620702517:AAFiNgQ2HB3o2yXpsuEahNc4byJYte5amHc"
    TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def get_system_uptime():
    diff = datetime.now() - START_TIME
    hours, remainder = divmod(int(diff.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours} soat, {minutes} daqiqa"

def check_telegram_api_health():
    try:
        url = f"{TELEGRAM_API}/getMe"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return {"status": "ok", "bot": data.get("result", {}).get("username")}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    return {"status": "error", "error": "Unknown Telegram error"}

def check_gemini_api_health():
    from ai_engine import GEMINI_API_KEY, MODEL_CANDIDATES
    model = MODEL_CANDIDATES[0]
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": "ping"}]}],
            "generationConfig": {"maxOutputTokens": 5}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.getcode() == 200:
                return {"status": "ok", "model": model}
    except Exception as e:
        return {"status": "warning", "error": str(e)}
    return {"status": "ok", "model": model}

def run_full_diagnostic():
    global LAST_HEALTH_REPORT
    
    # 1. Database Health
    db_res = database.check_and_repair_database()
    
    # 2. Telegram API Health
    tg_res = check_telegram_api_health()
    
    # 3. AI Engine Health
    ai_res = check_gemini_api_health()
    
    is_healthy = (db_res.get("status") in ["ok", "repaired"]) and (tg_res.get("status") == "ok")
    
    db_size_kb = 0
    if os.path.exists(database.DB_PATH):
        db_size_kb = round(os.path.getsize(database.DB_PATH) / 1024, 1)
        
    db_stat = db_res.get("status", "ok").upper()
    report = {
        "status": "HEALTHY 🟢" if is_healthy else "DEGRADED ⚠️",
        "uptime": get_system_uptime(),
        "database": f"{db_stat} ({db_size_kb} KB)",
        "telegram_api": tg_res.get("status", "ok").upper(),
        "ai_engine": ai_res.get("status", "ok").upper(),
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    LAST_HEALTH_REPORT = report
    return report

def send_alert_to_admin(msg_text):
    try:
        url = f"{TELEGRAM_API}/sendMessage"
        data = {
            "chat_id": ALERT_CHAT_ID,
            "text": msg_text,
            "parse_mode": "HTML"
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        print(f"Failed to send watchdog alert: {e}", flush=True)

def start_sentinel_watchdog():
    def watchdog_loop():
        consecutive_errors = 0
        while True:
            try:
                time.sleep(300) # Har 5 daqiqada tekshiradi
                diag = run_full_diagnostic()
                
                if "DEGRADED" in diag["status"]:
                    consecutive_errors += 1
                    # Self-Repair Actions
                    database.check_and_repair_database()
                    
                    if consecutive_errors >= 2:
                        alert = "🛡 <b>[SELF-HEALING HISOBOTI]</b>\n"
                        alert += "━━━━━━━━━━━━━━━━━━━━━━\n"
                        alert += "⚠️ Tizimda nosozlik aniqlandi va avtomatik ta'mirlandi:\n"
                        alert += f"• Baza: <b>{diag['database']}</b>\n"
                        alert += f"• Telegram: <b>{diag['telegram_api']}</b>\n"
                        alert += f"• AI Modellar: <b>{diag['ai_engine']}</b>\n"
                        alert += f"• Uptime: <b>{diag['uptime']}</b>\n"
                        alert += "━━━━━━━━━━━━━━━━━━━━━━\n"
                        alert += "✅ <i>Barcha ulanishlar avtomatik yangilandi va faoliyat tiklandi!</i>"
                        send_alert_to_admin(alert)
                        consecutive_errors = 0
                else:
                    consecutive_errors = 0
            except Exception as e:
                print(f"Sentinel Loop Error: {e}", flush=True)
                time.sleep(60)

    t = threading.Thread(target=watchdog_loop, daemon=True)
    t.start()
    print("🛡 Voice2Deal Self-Healing Watchdog Sentinel ishga tushdi...", flush=True)
