import os
import json
import csv
from datetime import datetime
import database
import google_sheets_sync

ADMIN_IDS = [1320855100, 8553116067]

def is_admin(telegram_id):
    if telegram_id in ADMIN_IDS:
        return True
    # Also check dynamic admin list from settings
    dynamic_admins = database.get_setting("admin_telegram_ids", "")
    if dynamic_admins:
        admin_list = [int(i.strip()) for i in dynamic_admins.split(",") if i.strip().isdigit()]
        return telegram_id in admin_list
    return False

def add_admin_id(telegram_id):
    current = database.get_setting("admin_telegram_ids", "")
    ids = set([int(i.strip()) for i in current.split(",") if i.strip().isdigit()] + ADMIN_IDS)
    ids.add(int(telegram_id))
    database.set_setting("admin_telegram_ids", ",".join(map(str, ids)))

def get_admin_dashboard_message():
    metrics = database.get_saas_global_metrics()
    webhook_url = database.get_setting("google_sheets_webhook_url")
    sync_status = "🟢 Ulangan" if webhook_url else "🔴 Ulanmagan"
    
    total_turnover = f"{int(metrics['total_turnover']):,}".replace(",", " ")
    total_debt = f"{int(metrics['total_debt']):,}".replace(",", " ")
    
    msg = "👑 <b>VOICE2DEAL — SUPER ADMIN DASHBOARD</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🏬 <b>Jami Do'konlar:</b> <b>{metrics['total_stores']} ta</b>\n"
    msg += f"👥 <b>Jami Foydalanuvchilar:</b> <b>{metrics['total_users']} ta</b>\n"
    msg += f"💼 <b>Faol Sotuvchilar/Xodimlar:</b> <b>{metrics['total_staff']} ta</b>\n"
    msg += f"🛒 <b>Jami Savdolar Soni:</b> <b>{metrics['total_deals']} ta</b>\n"
    msg += f"💰 <b>Umumiy Savdo Aylanmasi:</b> <b>{total_turnover} so'm</b>\n"
    msg += f"⏳ <b>Tizimdagi Jami Qarzlar:</b> <b>{total_debt} so'm</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📊 <b>Google Sheets:</b> {sync_status}\n"
    if webhook_url:
        short_url = webhook_url[:35] + "..." if len(webhook_url) > 35 else webhook_url
        msg += f"🔗 <code>{short_url}</code>\n"
    else:
        msg += "💡 <i>Google Sheets ni ulash uchun pastdagi 'Google Sheets ulash' tugmasini bosing.</i>\n"
        
    return msg

def get_admin_dashboard_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🏬 Ulangan do'konlar ro'yxati", "callback_data": "admin_stores_0"}],
            [{"text": "🔄 Google Sheets ga sinxronlash (Sync Now)", "callback_data": "admin_sync_sheets"}],
            [{"text": "🔗 Google Sheets Webhook URL sozlash", "callback_data": "admin_setup_sheets"}],
            [{"text": "📥 Barcha ma'lumotlarni yuklab olish (CSV)", "callback_data": "admin_export_data"}]
        ]
    }

def get_admin_stores_page(page=0, page_size=6):
    stores = database.get_all_stores_for_admin()
    total_count = len(stores)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * page_size
    current_page_stores = stores[start_idx:start_idx + page_size]
    
    msg = f"🏬 <b>ULANGAN DO'KONLAR RO'YXATI ({page + 1}/{total_pages}-sahifa)</b>\n"
    msg += f"Jami do'konlar soni: <b>{total_count} ta</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    
    if not current_page_stores:
        msg += "<i>Hozircha tizimda do'konlar mavjud emas.</i>\n"
    else:
        for idx, s in enumerate(current_page_stores, start_idx + 1):
            s_name = s.get("store_name", "Noma'lum")
            s_code = s.get("store_code", "Yo'q")
            owner = s.get("owner_name") or "Xo'jayin"
            username = f"(@{s['owner_username']})" if s.get("owner_username") else ""
            staff_c = s.get("staff_count", 0)
            sales = f"{int(s.get('total_sales', 0)):,}".replace(",", " ")
            debt = f"{int(s.get('total_debt', 0)):,}".replace(",", " ")
            plan = s.get("plan", "trial").upper()
            date = str(s.get("created_at", ""))[:10]
            
            msg += f"<b>{idx}. {s_name}</b> (<code>{s_code}</code>)\n"
            msg += f"   • 👑 Egasi: {owner} {username} (ID: <code>{s.get('owner_tg_id')}</code>)\n"
            msg += f"   • 👥 Xodimlar: {staff_c} ta | Tarif: <b>{plan}</b>\n"
            msg += f"   • 💰 Savdo: <b>{sales} so'm</b> | Qarz: {debt} so'm\n"
            msg += f"   • 📅 Ochilgan sana: {date}\n\n"
            
    inline_buttons = []
    nav_row = []
    if page > 0:
        nav_row.append({"text": "⬅️ Oldingi", "callback_data": f"admin_stores_{page - 1}"})
    if page < total_pages - 1:
        nav_row.append({"text": "Keyingi ➡️", "callback_data": f"admin_stores_{page + 1}"})
        
    if nav_row:
        inline_buttons.append(nav_row)
    inline_buttons.append([{"text": "🔙 Asosiy Admin Panel", "callback_data": "admin_home"}])
    
    return msg, {"inline_keyboard": inline_buttons}

def export_all_saas_data_csv():
    """Admin uchun barcha do'konlar va tranzaksiyalarni CSV formatida yaratish"""
    export_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(export_dir, exist_ok=True)
    filename = f"saas_full_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(export_dir, filename)
    
    stores = database.get_all_stores_for_admin()
    
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID", "Do'kon Kodi", "Do'kon Nomi", "Egasi", "Telegram ID", 
            "Username", "Tarif", "Xodimlar Soni", "Mijozlar Soni", 
            "Jami Savdo (so'm)", "Jami Qarz (so'm)", "Ochilgan Sana"
        ])
        for s in stores:
            writer.writerow([
                s.get("id"),
                s.get("store_code"),
                s.get("store_name"),
                s.get("owner_name"),
                s.get("owner_tg_id"),
                s.get("owner_username") or "",
                s.get("plan"),
                s.get("staff_count"),
                s.get("client_count"),
                s.get("total_sales"),
                s.get("total_debt"),
                s.get("created_at")
            ])
            
    return filepath
