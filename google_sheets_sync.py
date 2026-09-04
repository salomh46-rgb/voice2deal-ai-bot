import json
import urllib.request
import urllib.parse
from datetime import datetime
import database

def send_to_google_sheets(payload, webhook_url=None):
    """Google Apps Script Webhook URL ga ma'lumot yuborish"""
    if not webhook_url:
        webhook_url = database.get_setting("google_sheets_webhook_url")
        
    if not webhook_url or not webhook_url.startswith("http"):
        return {"success": False, "error": "Google Sheets Webhook URL sozlanmagan."}

    data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data_bytes,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp_body = resp.read().decode("utf-8")
            try:
                res_json = json.loads(resp_body)
                return {"success": True, "response": res_json}
            except:
                return {"success": True, "raw_response": resp_body[:200]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sync_all_data_to_sheets(webhook_url=None):
    """Barcha do'konlar, kassa va foydalanuvchilarni Google Sheets ga to'liq eksport qilish"""
    stores = database.get_all_stores_for_admin()
    metrics = database.get_saas_global_metrics()
    
    conn = database.get_db()
    c = conn.cursor()
    c.execute("""
    SELECT 
        tx.id, tx.created_at, s.store_code, s.store_name, tx.type, 
        tx.client_name, tx.total_amount, tx.paid_amount, tx.debt_amount,
        COALESCE(st.name, s.owner_name) as seller_name
    FROM transactions tx
    JOIN stores s ON s.id = tx.store_id
    LEFT JOIN staff st ON st.id = tx.staff_id
    ORDER BY tx.id DESC LIMIT 200
    """)
    recent_transactions = [dict(r) for r in c.fetchall()]
    
    c.execute("""
    SELECT u.telegram_id, u.name, u.username, u.role, s.store_name, s.store_code, u.created_at
    FROM users u
    LEFT JOIN stores s ON s.id = u.active_store_id
    ORDER BY u.telegram_id DESC
    """)
    users_list = [dict(r) for r in c.fetchall()]
    conn.close()

    payload = {
        "action": "full_sync",
        "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": metrics,
        "stores": stores,
        "transactions": recent_transactions,
        "users": users_list
    }
    
    return send_to_google_sheets(payload, webhook_url)


def notify_sheets_new_store(store_dict):
    """Yangi do'kon ochilganda Google Sheets ga real-time xabar berish"""
    payload = {
        "action": "new_store",
        "event_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "store": store_dict
    }
    return send_to_google_sheets(payload)


def notify_sheets_new_transaction(tx_dict, store_dict):
    """Yangi savdo bo'lganda Google Sheets ga real-time yozish"""
    payload = {
        "action": "new_transaction",
        "event_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "store_code": store_dict.get("store_code"),
        "store_name": store_dict.get("store_name"),
        "transaction": tx_dict
    }
    return send_to_google_sheets(payload)
