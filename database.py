import sqlite3
import json
import os
import random
import uuid
from datetime import datetime, timedelta

try:
    from config import DB_PATH
except ImportError:
    DB_PATH = os.path.join(os.path.dirname(__file__), "voice2deal.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
    except Exception:
        pass
    return conn

def check_and_repair_database():
    """Baza butunligi va nosozliklarini avtomatik tekshirish va ta'mirlash"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("PRAGMA integrity_check;")
        res = c.fetchone()
        status = res[0] if res else "unknown"
        c.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        init_db()
        conn.close()
        return {"status": "ok" if status == "ok" else "repaired", "detail": status}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Sozlamalar (Admin sozlamalari, Webhook URL)
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    
    # Foydalanuvchilar (Rollari: owner, seller, client, unselected)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        name TEXT,
        username TEXT,
        phone TEXT,
        role TEXT DEFAULT 'unselected',
        active_store_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Do'konlar
    c.execute("""
    CREATE TABLE IF NOT EXISTS stores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_code TEXT UNIQUE,
        telegram_id INTEGER UNIQUE,
        store_name TEXT,
        owner_name TEXT,
        currency TEXT DEFAULT 'UZS',
        plan TEXT DEFAULT 'trial',
        trial_ends_at TIMESTAMP,
        subscription_ends_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Xodimlar (Sotuvchilar / Shogirdlar)
    c.execute("""
    CREATE TABLE IF NOT EXISTS staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER,
        telegram_id INTEGER,
        name TEXT,
        username TEXT,
        role TEXT DEFAULT 'seller',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(store_id, telegram_id)
    )
    """)

    # Mijozlar (Nasiya daftari)
    c.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER,
        name TEXT,
        phone TEXT,
        telegram_id INTEGER,
        total_debt REAL DEFAULT 0,
        last_deal_date TIMESTAMP,
        last_reminder_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(store_id, name)
    )
    """)

    # Savdolar va tranzaksiyalar
    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER,
        staff_id INTEGER,
        client_id INTEGER,
        client_name TEXT,
        type TEXT, -- sale, debt_payment, debt_give, expense
        items_json TEXT,
        total_amount REAL DEFAULT 0,
        paid_amount REAL DEFAULT 0,
        debt_amount REAL DEFAULT 0,
        currency TEXT DEFAULT 'UZS',
        due_date TEXT,
        comment TEXT,
        raw_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Migratsiyalar
    try:
        c.execute("ALTER TABLE stores ADD COLUMN store_code TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE staff ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass

    # Mavjud do'konlarga store_code yaratish
    c.execute("SELECT id, store_code FROM stores WHERE store_code IS NULL OR store_code = ''")
    for s in c.fetchall():
        code = f"DK-{random.randint(1000, 9999)}"
        c.execute("UPDATE stores SET store_code = ? WHERE id = ?", (code, s["id"]))

        # Ombor va Tovar qoldiqlari (Sklad)
    c.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER,
        name TEXT,
        quantity REAL DEFAULT 0,
        unit TEXT DEFAULT 'dona',
        cost_price REAL DEFAULT 0,
        selling_price REAL DEFAULT 0,
        min_alert_qty REAL DEFAULT 5,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(store_id, name)
    )
    """)

    # To'lovlar (Billing)
    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER,
        provider TEXT,
        amount REAL,
        plan TEXT,
        status TEXT DEFAULT 'success',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def generate_unique_store_code():
    conn = get_db()
    c = conn.cursor()
    while True:
        code = f"DK-{random.randint(1000, 9999)}"
        c.execute("SELECT id FROM stores WHERE store_code = ?", (code,))
        if not c.fetchone():
            conn.close()
            return code

def get_or_create_user(telegram_id, name="Foydalanuvchi", username=""):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    if row:
        user = dict(row)
        c.execute("UPDATE users SET name = ?, username = ? WHERE telegram_id = ?", (name, username, telegram_id))
        conn.commit()
    else:
        c.execute("INSERT INTO users (telegram_id, name, username, role) VALUES (?, ?, ?, 'unselected')",
                  (telegram_id, name, username))
        conn.commit()
        c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = dict(c.fetchone())
    conn.close()
    return user

def set_user_role(telegram_id, role, active_store_id=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    INSERT INTO users (telegram_id, role, active_store_id)
    VALUES (?, ?, ?)
    ON CONFLICT(telegram_id) DO UPDATE SET role = excluded.role, active_store_id = excluded.active_store_id
    """, (telegram_id, role, active_store_id))
    conn.commit()
    conn.close()

def create_store_for_owner(telegram_id, owner_name="", store_name="Mening Do'konim"):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM stores WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    if row:
        store = dict(row)
        if not store.get("store_code"):
            code = generate_unique_store_code()
            c.execute("UPDATE stores SET store_code = ? WHERE id = ?", (code, store["id"]))
            conn.commit()
            store["store_code"] = code
    else:
        code = generate_unique_store_code()
        trial_end = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
        INSERT INTO stores (telegram_id, store_code, owner_name, store_name, plan, trial_ends_at)
        VALUES (?, ?, ?, ?, 'trial', ?)
        """, (telegram_id, code, owner_name, store_name, trial_end))
        conn.commit()
        c.execute("SELECT * FROM stores WHERE telegram_id = ?", (telegram_id,))
        store = dict(c.fetchone())
    
    # User rolini owner qilib belgilaymiz
    c.execute("UPDATE users SET role = 'owner', active_store_id = ? WHERE telegram_id = ?", (store["id"], telegram_id))
    conn.commit()
    conn.close()
    return store

def update_store_name(telegram_id, new_store_name):
    conn = get_db()
    c = conn.cursor()
    clean_name = new_store_name.strip()
    c.execute("UPDATE stores SET store_name = ? WHERE telegram_id = ?", (clean_name, telegram_id))
    affected = c.rowcount
    if affected == 0:
        c.execute("SELECT active_store_id FROM users WHERE telegram_id = ?", (telegram_id,))
        u_row = c.fetchone()
        if u_row and u_row["active_store_id"]:
            c.execute("UPDATE stores SET store_name = ? WHERE id = ?", (clean_name, u_row["active_store_id"]))
            affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_store_by_code(store_code):
    conn = get_db()
    c = conn.cursor()
    code_clean = store_code.strip().upper()
    c.execute("SELECT * FROM stores WHERE UPPER(store_code) = ?", (code_clean,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def join_store_as_seller(seller_telegram_id, store_code, seller_name="", username=""):
    store = get_store_by_code(store_code)
    if not store:
        return {"success": False, "error": f"'{store_code}' kodli do'kon topilmadi. Iltimos, do'kon kodini tekshirib qaytadan kiriting."}
    
    if store["telegram_id"] == seller_telegram_id:
        return {"success": False, "error": "Siz ushbu do'konning egasisiz!"}
        
    store_id = store["id"]
    conn = get_db()
    c = conn.cursor()
    
    # Staff ga qo'shish yoki yangilash
    c.execute("SELECT * FROM staff WHERE store_id = ? AND telegram_id = ?", (store_id, seller_telegram_id))
    existing = c.fetchone()
    if existing:
        c.execute("UPDATE staff SET name = ?, username = ?, is_active = 1 WHERE id = ?",
                  (seller_name, username, existing["id"]))
    else:
        c.execute("""
        INSERT INTO staff (store_id, telegram_id, name, username, role, is_active)
        VALUES (?, ?, ?, ?, 'seller', 1)
        """, (store_id, seller_telegram_id, seller_name, username))
        
    # User rolini seller qilib belgilaymiz
    c.execute("UPDATE users SET role = 'seller', active_store_id = ? WHERE telegram_id = ?", (store_id, seller_telegram_id))
    conn.commit()
    conn.close()
    
    return {
        "success": True, 
        "store_id": store_id,
        "store_name": store["store_name"], 
        "store_code": store["store_code"],
        "owner_name": store["owner_name"]
    }

def get_user_context(telegram_id, user_name="Foydalanuvchi", username=""):
    user = get_or_create_user(telegram_id, user_name, username)
    role = user.get("role") or "unselected"
    active_store_id = user.get("active_store_id")

    conn = get_db()
    c = conn.cursor()

    # 1. Agar foydalanuvchi roli aniq "seller" bo'lsa va do'konga biriktirilgan bo'lsa:
    if role == "seller" and active_store_id:
        c.execute("""
        SELECT s.*, st.id as store_real_id, st.store_name, st.store_code, st.owner_name, st.plan, st.trial_ends_at, st.subscription_ends_at, st.currency
        FROM staff s
        JOIN stores st ON s.store_id = st.id
        WHERE s.telegram_id = ? AND s.store_id = ? AND s.is_active = 1
        """, (telegram_id, active_store_id))
        staff_row = c.fetchone()
        if staff_row:
            staff_dict = dict(staff_row)
            store_dict = {
                "id": staff_dict["store_real_id"],
                "store_code": staff_dict["store_code"],
                "store_name": staff_dict["store_name"] or "Mening Do'konim",
                "owner_name": staff_dict["owner_name"] or "Do'kon Egasi",
                "plan": staff_dict["plan"],
                "trial_ends_at": staff_dict["trial_ends_at"],
                "subscription_ends_at": staff_dict["subscription_ends_at"],
                "currency": staff_dict["currency"]
            }
            conn.close()
            return {
                "is_registered": True,
                "role": "seller",
                "is_owner": False,
                "store": store_dict,
                "staff_id": staff_dict["id"],
                "staff_name": staff_dict["name"] or user_name
            }

    # 2. Agar foydalanuvchi roli "owner" bo'lsa yoki o'z do'koni bo'lsa:
    if role == "owner" or role == "unselected":
        c.execute("SELECT * FROM stores WHERE telegram_id = ?", (telegram_id,))
        owner_store = c.fetchone()
        if owner_store:
            st_dict = dict(owner_store)
            if not st_dict.get("store_code"):
                code = generate_unique_store_code()
                c.execute("UPDATE stores SET store_code = ? WHERE id = ?", (code, st_dict["id"]))
                conn.commit()
                st_dict["store_code"] = code
            if not st_dict.get("owner_name"):
                st_dict["owner_name"] = user_name or "Do'kon Egasi"
            conn.close()
            return {
                "is_registered": True,
                "role": "owner",
                "is_owner": True,
                "store": st_dict,
                "staff_id": None
            }

    # 3. Agar foydalanuvchi biror do'konda sotuvchi bo'lsa (lekin active_store_id belgilanmagan bo'lsa):
    c.execute("""
    SELECT s.*, st.id as store_real_id, st.store_name, st.store_code, st.owner_name, st.plan, st.trial_ends_at, st.subscription_ends_at, st.currency
    FROM staff s
    JOIN stores st ON s.store_id = st.id
    WHERE s.telegram_id = ? AND s.is_active = 1
    """, (telegram_id,))
    staff_row = c.fetchone()
    if staff_row:
        staff_dict = dict(staff_row)
        store_dict = {
            "id": staff_dict["store_real_id"],
            "store_code": staff_dict["store_code"],
            "store_name": staff_dict["store_name"] or "Mening Do'konim",
            "owner_name": staff_dict["owner_name"] or "Do'kon Egasi",
            "plan": staff_dict["plan"],
            "trial_ends_at": staff_dict["trial_ends_at"],
            "subscription_ends_at": staff_dict["subscription_ends_at"],
            "currency": staff_dict["currency"]
        }
        conn.close()
        return {
            "is_registered": True,
            "role": "seller",
            "is_owner": False,
            "store": store_dict,
            "staff_id": staff_dict["id"],
            "staff_name": staff_dict["name"] or user_name
        }

    # 4. Agar mijoz (klient) bo'lsa
    if role == "client":
        conn.close()
        return {
            "is_registered": True,
            "role": "client",
            "is_owner": False,
            "store": None,
            "staff_id": None
        }

    conn.close()
    return {
        "is_registered": False,
        "role": "unselected",
        "is_owner": False,
        "store": None,
        "staff_id": None
    }

def get_store_staff(owner_telegram_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM stores WHERE telegram_id = ?", (owner_telegram_id,))
    s_row = c.fetchone()
    if not s_row:
        conn.close()
        return []
    store_id = s_row["id"]
    c.execute("SELECT id, name, username, role, telegram_id, created_at FROM staff WHERE store_id = ? AND is_active = 1", (store_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def remove_staff_member(owner_telegram_id, staff_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM stores WHERE telegram_id = ?", (owner_telegram_id,))
    s_row = c.fetchone()
    if not s_row:
        conn.close()
        return False
    c.execute("UPDATE staff SET is_active = 0 WHERE id = ? AND store_id = ?", (staff_id, s_row["id"]))
    conn.commit()
    conn.close()
    return True

def get_client_debts_by_phone_or_id(phone=None, telegram_id=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    SELECT c.name, c.total_debt, c.last_deal_date, st.store_name, st.store_code, st.owner_name
    FROM clients c
    JOIN stores st ON c.store_id = st.id
    WHERE (c.phone = ? AND ? IS NOT NULL) OR (c.telegram_id = ? AND ? IS NOT NULL)
    """, (phone, phone, telegram_id, telegram_id))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def check_subscription(store_dict):
    if not store_dict:
        return {"is_active": False, "plan": "none", "status_text": "Do'kon mavjud emas", "days_left": 0}
    now = datetime.now()
    plan = store_dict.get("plan") or "trial"
    trial_end = store_dict.get("trial_ends_at")
    sub_end = store_dict.get("subscription_ends_at")
    
    if plan == "yearly" or plan == "monthly":
        if sub_end:
            sub_dt = datetime.strptime(sub_end.split(".")[0], "%Y-%m-%d %H:%M:%S")
            diff_sec = (sub_dt - now).total_seconds()
            if diff_sec >= 0:
                days_left = max(1, int(diff_sec / 86400 + 0.99))
                return {
                    "is_active": True,
                    "plan": plan,
                    "status_text": f"👑 {plan.capitalize()} (Qolgan: {days_left} kun)",
                    "days_left": days_left
                }
    
    if trial_end:
        try:
            trial_dt = datetime.strptime(trial_end.split(".")[0], "%Y-%m-%d %H:%M:%S")
            diff_sec = (trial_dt - now).total_seconds()
            if diff_sec >= 0:
                days_left = max(1, int(diff_sec / 86400 + 0.99))
                return {
                    "is_active": True,
                    "plan": "trial",
                    "status_text": f"🎁 Bepul Sinov Davri (Qolgan: {days_left} kun)",
                    "days_left": days_left
                }
        except Exception:
            pass
            
    return {
        "is_active": False,
        "plan": "expired",
        "status_text": "❌ Obuna muddati tugagan",
        "days_left": 0
    }

def activate_subscription(telegram_id, plan="monthly", days=30):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM stores WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    store_id = None
    if row:
        store_id = row["id"]
    else:
        c.execute("SELECT active_store_id FROM users WHERE telegram_id = ?", (telegram_id,))
        u_row = c.fetchone()
        if u_row and u_row["active_store_id"]:
            store_id = u_row["active_store_id"]
            
    if not store_id:
        conn.close()
        return None
        
    new_end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE stores SET plan = ?, subscription_ends_at = ? WHERE id = ?", (plan, new_end, store_id))
    
    # Also record in payments table
    amount_val = 49000 if plan == "monthly" else (89000 if plan == "pro" else 390000)
    c.execute("INSERT INTO payments (store_id, provider, amount, plan, status) VALUES (?, 'receipt_manual', ?, ?, 'success')",
              (store_id, amount_val, plan))
    
    conn.commit()
    conn.close()
    return new_end

def record_transaction(telegram_id, ai_data, raw_text=""):
    ctx = get_user_context(telegram_id)
    store = ctx["store"]
    if not store:
        return None
    store_id = store["id"]
    staff_id = ctx["staff_id"]
    
    conn = get_db()
    c = conn.cursor()

    client_name = ai_data.get("client_name") or "Noma'lum"
    client_phone = ai_data.get("client_phone")
    op_type = ai_data.get("operation_type") or "sale"
    total = float(ai_data.get("total_amount") or 0)
    paid = float(ai_data.get("paid_amount") or 0)
    debt = float(ai_data.get("debt_amount") or 0)
    currency = ai_data.get("currency") or "UZS"
    due_date = ai_data.get("due_date")
    comment = ai_data.get("comment") or ""
    items = json.dumps(ai_data.get("items") or [], ensure_ascii=False)

    client_id = None
    new_debt = 0.0
    had_previous_debt = False
    prev_debt = 0.0

    if client_name and client_name != "Noma'lum":
        inp_clean = client_name.lower().strip()
        inp_first = inp_clean.split()[0] if inp_clean else ""

        c_row = None
        
        # 1. Agar qarz to'lovi (debt_payment) bo'lsa, BIRINCHI NAVBATDA qarzi bor mijozlardan qidiramiz (total_debt > 0)
        if op_type == "debt_payment":
            c.execute("SELECT * FROM clients WHERE store_id = ? AND total_debt > 0", (store_id,))
            debtors_list = c.fetchall()
            # A) Exact match among active debtors
            for d in debtors_list:
                if d["name"].lower().strip() == inp_clean:
                    c_row = d
                    break
            # B) Fuzzy / first name / substring match among active debtors
            if not c_row:
                for d in debtors_list:
                    cand_clean = d["name"].lower().strip()
                    cand_first = cand_clean.split()[0] if cand_clean else ""
                    if cand_first == inp_first or cand_clean in inp_clean or inp_clean in cand_clean:
                        c_row = d
                        break

        # 2. Agar hali ham topilmasa (yoki oddiy savdo bo'lsa), barcha mijozlardan qidiramiz
        if not c_row:
            c.execute("SELECT * FROM clients WHERE store_id = ? AND LOWER(name) = LOWER(?)", (store_id, client_name))
            c_row = c.fetchone()
            
        if not c_row:
            c.execute("SELECT * FROM clients WHERE store_id = ?", (store_id,))
            all_store_clients = c.fetchall()
            for cand in all_store_clients:
                cand_clean = cand["name"].lower().strip()
                cand_first = cand_clean.split()[0] if cand_clean else ""
                if cand_clean == inp_clean or cand_first == inp_first or cand_clean in inp_clean or inp_clean in cand_clean:
                    c_row = cand
                    break

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if c_row:
            client_id = c_row["id"]
            client_name = c_row["name"] # Haqiqiy bazadagi ismga sinxronlaymiz
            curr_debt = float(c_row["total_debt"] or 0)
            prev_debt = curr_debt
            if curr_debt > 0:
                had_previous_debt = True
            
            if op_type == "sale":
                new_debt = curr_debt + debt
            elif op_type == "debt_give":
                eff_debt = debt if debt > 0 else total
                new_debt = curr_debt + eff_debt
            elif op_type == "debt_payment":
                # Agar to'lov summasi ko'rsatilmagan bo'lsa yoki 0 bo'lsa, mavjud barcha qarzini yopadi
                if paid <= 0 and total <= 0:
                    paid = curr_debt
                    total = curr_debt
                elif paid <= 0 and total > 0:
                    paid = total
                new_debt = max(0.0, curr_debt - paid)
            else:
                new_debt = max(0.0, curr_debt - paid)
                
            c.execute("UPDATE clients SET total_debt = ?, last_deal_date = ?, phone = COALESCE(?, phone) WHERE id = ?",
                      (new_debt, now, client_phone, client_id))
        else:
            if op_type == "sale":
                new_debt = debt
            elif op_type == "debt_give":
                new_debt = debt if debt > 0 else total
            elif op_type == "debt_payment":
                if paid <= 0 and total > 0:
                    paid = total
                new_debt = 0.0
            else:
                new_debt = 0.0
            c.execute("INSERT INTO clients (store_id, name, phone, total_debt, last_deal_date) VALUES (?, ?, ?, ?, ?)",
                      (store_id, client_name, client_phone, new_debt, now))
            client_id = c.lastrowid

    c.execute("""
    INSERT INTO transactions (store_id, staff_id, client_id, client_name, type, items_json, total_amount, paid_amount, debt_amount, currency, due_date, comment, raw_text)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (store_id, staff_id, client_id, client_name, op_type, items, total, paid, debt, currency, due_date, comment, raw_text))

    tx_id = c.lastrowid
    conn.commit()
    conn.close()

    return {
        "tx_id": tx_id,
        "store_id": store_id,
        "client_name": client_name,
        "total": total,
        "paid": paid,
        "debt": debt,
        "new_debt": new_debt,
        "had_previous_debt": had_previous_debt,
        "prev_debt": prev_debt,
        "op_type": op_type
    }

def get_kassa_summary(telegram_id, date_filter=None):
    ctx = get_user_context(telegram_id)
    store = ctx["store"]
    if not store:
        return {"today": {"total_deals": 0, "total_sales": 0, "total_cash": 0, "total_debt": 0}, "overall_debt": 0, "debtor_count": 0, "date": ""}
    store_id = store["id"]
    conn = get_db()
    c = conn.cursor()

    date_str = date_filter or datetime.now().strftime("%Y-%m-%d")
    
    c.execute("""
    SELECT 
        COUNT(*) as total_deals,
        COALESCE(SUM(total_amount), 0) as total_sales,
        COALESCE(SUM(paid_amount), 0) as total_cash,
        COALESCE(SUM(debt_amount), 0) as total_debt
    FROM transactions 
    WHERE store_id = ? AND DATE(created_at) = DATE(?)
    """, (store_id, date_str))
    today_stats = dict(c.fetchone())

    c.execute("SELECT COALESCE(SUM(total_debt), 0) as all_debt, COUNT(*) as debtor_count FROM clients WHERE store_id = ? AND total_debt > 0", (store_id,))
    debt_stats = dict(c.fetchone())

    conn.close()
    return {
        "today": today_stats,
        "overall_debt": debt_stats["all_debt"],
        "debtor_count": debt_stats["debtor_count"],
        "date": date_str
    }

def get_debtors_list(telegram_id, limit=20):
    ctx = get_user_context(telegram_id)
    store = ctx["store"]
    if not store:
        return []
    store_id = store["id"]
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    SELECT id, name, phone, total_debt, last_deal_date, last_reminder_at 
    FROM clients 
    WHERE store_id = ? AND total_debt > 0 
    ORDER BY total_debt DESC 
    LIMIT ?
    """, (store_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_client_by_id(client_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_recent_transactions(telegram_id, limit=10):
    ctx = get_user_context(telegram_id)
    store = ctx["store"]
    if not store:
        return []
    store_id = store["id"]
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    SELECT id, client_name, type, total_amount, paid_amount, debt_amount, created_at, comment
    FROM transactions
    WHERE store_id = ?
    ORDER BY created_at DESC
    LIMIT ?
    """, (store_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def record_reminder_sent(client_id):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE clients SET last_reminder_at = ? WHERE id = ?", (now, client_id))
    conn.commit()
    conn.close()


def add_or_update_inventory(store_id, item_name, qty, cost_price=0, selling_price=0, unit="dona"):
    """Skladga tovar kirim qilish yoki mavjud tovar sonini oshirish"""
    conn = get_db()
    c = conn.cursor()
    item_clean = item_name.strip()
    
    c.execute("SELECT * FROM inventory WHERE store_id = ? AND LOWER(name) = LOWER(?)", (store_id, item_clean))
    row = c.fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if row:
        new_qty = row["quantity"] + float(qty)
        new_cost = float(cost_price) if float(cost_price) > 0 else row["cost_price"]
        new_sell = float(selling_price) if float(selling_price) > 0 else row["selling_price"]
        c.execute("""
        UPDATE inventory 
        SET quantity = ?, cost_price = ?, selling_price = ?, unit = ?, updated_at = ?
        WHERE id = ?
        """, (new_qty, new_cost, new_sell, unit, now, row["id"]))
        inv_id = row["id"]
    else:
        c.execute("""
        INSERT INTO inventory (store_id, name, quantity, unit, cost_price, selling_price, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (store_id, item_clean, float(qty), unit, float(cost_price), float(selling_price), now))
        inv_id = c.lastrowid
        new_qty = float(qty)
        
    conn.commit()
    conn.close()
    return {"id": inv_id, "name": item_clean, "new_quantity": new_qty}

def decrement_inventory_on_sale(store_id, items):
    """Sotilgan tovarlarni ombordan avtomatik kamaytirish va kam qolganlarni ogohlantirish"""
    if not items or not isinstance(items, list):
        return []
    conn = get_db()
    c = conn.cursor()
    warnings = []
    
    for it in items:
        name = it.get("name")
        qty = float(it.get("qty") or 1)
        if not name:
            continue
        c.execute("SELECT * FROM inventory WHERE store_id = ? AND LOWER(name) = LOWER(?)", (store_id, name.strip()))
        row = c.fetchone()
        if row:
            new_qty = max(0, row["quantity"] - qty)
            c.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, row["id"]))
            if new_qty <= row["min_alert_qty"]:
                warnings.append(f"⚠️ <b>{row['name']}</b> omborda oz qoldi: <b>{int(new_qty)} {row['unit']}</b>")
                
    conn.commit()
    conn.close()
    return warnings

def get_inventory_list(telegram_id):
    """Do'konning barcha tovar qoldiqlari ro'yxati"""
    ctx = get_user_context(telegram_id)
    store = ctx["store"]
    if not store:
        return []
    store_id = store["id"]
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    SELECT id, name, quantity, unit, cost_price, selling_price, min_alert_qty, updated_at
    FROM inventory
    WHERE store_id = ?
    ORDER BY quantity ASC
    """, (store_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_business_analytics_data(telegram_id):
    """AI Maslahatchi uchun do'konning chuqur statistikasi"""
    ctx = get_user_context(telegram_id)
    store = ctx["store"]
    if not store:
        return None
    store_id = store["id"]
    conn = get_db()
    c = conn.cursor()
    
    # Savdolar hajmi (Oxirgi 30 kun)
    c.execute("""
    SELECT 
        COUNT(*) as total_orders,
        COALESCE(SUM(total_amount), 0) as total_volume,
        COALESCE(SUM(paid_amount), 0) as total_cash,
        COALESCE(SUM(debt_amount), 0) as total_debt
    FROM transactions 
    WHERE store_id = ? AND type = 'sale'
    """, (store_id,))
    sales_stats = dict(c.fetchone())

    # Xarajatlar
    c.execute("""
    SELECT COALESCE(SUM(total_amount), 0) as total_expense
    FROM transactions 
    WHERE store_id = ? AND type = 'expense'
    """, (store_id,))
    expense_stats = dict(c.fetchone())

    # Nasiyadorlar
    c.execute("""
    SELECT name, total_debt, last_deal_date 
    FROM clients 
    WHERE store_id = ? AND total_debt > 0 
    ORDER BY total_debt DESC LIMIT 5
    """, (store_id,))
    top_debtors = [dict(r) for r in c.fetchall()]

    # Sklad qoldiqlari
    c.execute("""
    SELECT name, quantity, unit, cost_price, selling_price 
    FROM inventory 
    WHERE store_id = ?
    ORDER BY quantity ASC LIMIT 10
    """, (store_id,))
    inventory_items = [dict(r) for r in c.fetchall()]

    conn.close()
    return {
        "store_name": store["store_name"],
        "store_code": store.get("store_code"),
        "sales": sales_stats,
        "expense": expense_stats["total_expense"],
        "top_debtors": top_debtors,
        "inventory": inventory_items
    }


def get_setting(key, default=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
    """, (key, str(value)))
    conn.commit()
    conn.close()

def get_all_stores_for_admin():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    SELECT 
        s.id, s.store_code, s.store_name, s.owner_name, s.telegram_id as owner_tg_id,
        u.username as owner_username, s.plan, s.trial_ends_at, s.subscription_ends_at, s.created_at,
        (SELECT COUNT(*) FROM staff st WHERE st.store_id = s.id AND st.is_active = 1) as staff_count,
        (SELECT COUNT(*) FROM clients cl WHERE cl.store_id = s.id) as client_count,
        (SELECT COALESCE(SUM(total_amount), 0) FROM transactions tx WHERE tx.store_id = s.id AND tx.type = 'sale') as total_sales,
        (SELECT COALESCE(SUM(total_debt), 0) FROM clients cl WHERE cl.store_id = s.id) as total_debt
    FROM stores s
    LEFT JOIN users u ON u.telegram_id = s.telegram_id
    ORDER BY s.id DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_saas_global_metrics():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total_stores FROM stores")
    total_stores = c.fetchone()["total_stores"]
    c.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = c.fetchone()["total_users"]
    c.execute("SELECT COUNT(*) as total_staff FROM staff WHERE is_active = 1")
    total_staff = c.fetchone()["total_staff"]
    c.execute("SELECT COUNT(*) as total_deals, COALESCE(SUM(total_amount), 0) as total_turnover FROM transactions WHERE type = 'sale'")
    tx_stat = dict(c.fetchone())
    c.execute("SELECT COALESCE(SUM(total_debt), 0) as total_debt FROM clients")
    total_debt = c.fetchone()["total_debt"]
    conn.close()
    return {
        "total_stores": total_stores,
        "total_users": total_users,
        "total_staff": total_staff,
        "total_deals": tx_stat["total_deals"],
        "total_turnover": tx_stat["total_turnover"],
        "total_debt": total_debt
    }

def set_user_role(telegram_id, role):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id))
    conn.commit()
    conn.close()

def get_client_debts_by_telegram_id(telegram_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user_row = c.fetchone()
    user = dict(user_row) if user_row else {}
    u_name = user.get("name", "")
    u_username = user.get("username", "")

    c.execute("""
    SELECT 
        cl.id, cl.name as client_name, cl.total_debt, cl.last_deal_date,
        s.store_name, s.store_code, s.owner_name
    FROM clients cl
    JOIN stores s ON s.id = cl.store_id
    WHERE (cl.telegram_id = ? OR (LOWER(cl.name) = LOWER(?) AND ? != '') OR (LOWER(cl.name) = LOWER(?) AND ? != ''))
      AND cl.total_debt > 0
    ORDER BY cl.last_deal_date DESC
    """, (telegram_id, u_name, u_name, u_username, u_username))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_seller_shift_summary(telegram_id):
    ctx = get_user_context(telegram_id)
    store = ctx["store"]
    staff_id = ctx.get("staff_id")
    if not store:
        return None
    store_id = store["id"]
    conn = get_db()
    c = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if staff_id:
        c.execute("""
        SELECT 
            COUNT(*) as total_deals,
            COALESCE(SUM(total_amount), 0) as total_sales,
            COALESCE(SUM(paid_amount), 0) as total_cash,
            COALESCE(SUM(debt_amount), 0) as total_debt
        FROM transactions 
        WHERE store_id = ? AND staff_id = ? AND DATE(created_at) = DATE(?)
        """, (store_id, staff_id, today_str))
    else:
        c.execute("""
        SELECT 
            COUNT(*) as total_deals,
            COALESCE(SUM(total_amount), 0) as total_sales,
            COALESCE(SUM(paid_amount), 0) as total_cash,
            COALESCE(SUM(debt_amount), 0) as total_debt
        FROM transactions 
        WHERE store_id = ? AND DATE(created_at) = DATE(?)
        """, (store_id, today_str))
        
    stats = dict(c.fetchone())
    conn.close()
    return {
        "store_name": store["store_name"],
        "store_code": store.get("store_code"),
        "stats": stats,
        "date": today_str
    }

init_db()
