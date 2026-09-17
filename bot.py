import admin_panel
import google_sheets_sync
import database
import self_healing_watchdog
import socket

_INSTANCE_LOCK_SOCKET = None
def acquire_single_instance_lock(port=49152):
    global _INSTANCE_LOCK_SOCKET
    _INSTANCE_LOCK_SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _INSTANCE_LOCK_SOCKET.bind(('127.0.0.1', port))
        _INSTANCE_LOCK_SOCKET.listen(1)
        return True
    except socket.error:
        print("⚠️ Boshqa bot nusxasi allaqachon ishlab turibdi! Chiqilmoqda...", flush=True)
        sys.exit(0)

import os
import json
import urllib.request
import urllib.parse
import time
import sys
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import threading
from datetime import datetime, timedelta
from ai_engine import (
    parse_voice_or_text, generate_gentle_reminder, 
    generate_ai_business_report, answer_ai_support, 
    generate_telegram_share_link
)
from receipt_generator import generate_thermal_receipt_text, generate_thermal_receipt_html
from database import (
    get_seller_shift_summary,
    record_transaction, get_kassa_summary, get_debtors_list, 
    get_recent_transactions, get_user_context, create_store_for_owner,
    join_store_as_seller, get_store_by_code, set_user_role,
    check_subscription, activate_subscription, get_store_staff,
    remove_staff_member, get_client_by_id, record_reminder_sent,
    get_client_debts_by_telegram_id, get_client_debts_by_phone_or_id, 
    add_or_update_inventory, decrement_inventory_on_sale, get_inventory_list, get_business_analytics_data,
    update_store_name
)
from excel_export import export_kassa_excel

try:
    from config import TELEGRAM_TOKEN, TELEGRAM_API, TELEGRAM_FILE_API, ADMIN_ID
except ImportError:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_TOKEN", ""))
    TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    TELEGRAM_FILE_API = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"
    ADMIN_ID = 1320855100

# Foydalanuvchi kutish holatlari (State memory)
USER_STATES = {} # {chat_id: "waiting_for_store_code" | "waiting_for_phone" | ...}
PENDING_CONFIRMATIONS = {} # {chat_id: {"operations": [...], "raw_text": "...", "store_id": 1, ...}}

def format_number(n):
    try:
        return f"{int(round(float(n))):,}".replace(",", " ")
    except Exception:
        return str(n)

def format_trade_confirmation_card(operations_list):
    """
    Audio Confirmation Loop: Savdogarga xatolik bo'lmasligi uchun tasdiqlash kartochkasi.
    Masalan:
    📦 Nasiya: Eshmat aka, 500 000 so'm. To'g'rimi?
    [✅ Tasdiqlash] [❌ Tahrirlash]
    [🚫 Bekor qilish]
    """
    if not operations_list:
        return "⚠️ Tasdiqlash uchun savdo amali topilmadi.", None

    if len(operations_list) == 1:
        op = operations_list[0]
        op_type = op.get("operation_type")
        client = op.get("client_name") or "Noma'lum"
        total = float(op.get("total_amount") or 0)
        debt = float(op.get("debt_amount") or 0)
        paid = float(op.get("paid_amount") or 0)
        items = op.get("items") or []

        if op_type == "inventory_in":
            items_desc = ", ".join([f"{it.get('qty', 1)} ta {it.get('name', 'Tovar')}" for it in items]) if items else "Tovar kirimi"
            sum_val = format_number(total or (items[0].get('price', 0) if items else 0))
            text = f"📥 <b>Ombor kirimi:</b> {items_desc}, <b>{sum_val} so'm</b>.\n\nTo'g'rimi?"
        elif op_type in ["debt_give", "nasiya"] or debt > 0:
            sum_val = format_number(debt if debt > 0 else total)
            text = f"📦 <b>Nasiya:</b> {client}, <b>{sum_val} so'm</b>.\n\nTo'g'rimi?"
        elif op_type == "debt_payment":
            sum_val = format_number(paid if paid > 0 else total)
            text = f"💵 <b>Qarz to'lovi:</b> {client}, <b>{sum_val} so'm</b>.\n\nTo'g'rimi?"
        elif op_type == "expense":
            sum_val = format_number(total)
            text = f"📉 <b>Xarajat:</b> {client}, <b>{sum_val} so'm</b>.\n\nTo'g'rimi?"
        else:
            sum_val = format_number(total if total > 0 else paid)
            text = f"💰 <b>Naqd savdo:</b> {client}, <b>{sum_val} so'm</b>.\n\nTo'g'rimi?"
    else:
        lines = []
        for idx, op in enumerate(operations_list, 1):
            op_type = op.get("operation_type")
            client = op.get("client_name") or "Xaridor"
            total = float(op.get("total_amount") or 0)
            debt = float(op.get("debt_amount") or 0)
            paid = float(op.get("paid_amount") or 0)
            if op_type in ["debt_give", "nasiya"] or debt > 0:
                s = format_number(debt if debt > 0 else total)
                lines.append(f"{idx}. 📦 <b>Nasiya:</b> {client} — {s} so'm")
            elif op_type == "debt_payment":
                s = format_number(paid if paid > 0 else total)
                lines.append(f"{idx}. 💵 <b>Qarz to'lovi:</b> {client} — {s} so'm")
            elif op_type == "inventory_in":
                lines.append(f"{idx}. 📥 <b>Ombor kirimi:</b> {client}")
            elif op_type == "expense":
                s = format_number(total)
                lines.append(f"{idx}. 📉 <b>Xarajat:</b> {client} — {s} so'm")
            else:
                s = format_number(total if total > 0 else paid)
                lines.append(f"{idx}. 💰 <b>Naqd savdo:</b> {client} — {s} so'm")

        text = f"📋 <b>Savdo amallari ({len(operations_list)} ta):</b>\n"
        text += "\n".join(lines) + "\n\n<b>To'g'rimi?</b>"

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Tasdiqlash", "callback_data": "confirm_trade_yes"},
                {"text": "❌ Tahrirlash", "callback_data": "confirm_trade_edit"}
            ],
            [
                {"text": "🚫 Bekor qilish", "callback_data": "confirm_trade_cancel"}
            ]
        ]
    }
    return text, keyboard


def send_telegram_request(method, data):
    url = f"{TELEGRAM_API}/{method}"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Telegram API Error ({method}): {e}", flush=True)
        return None

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    return send_telegram_request("sendMessage", data)

def send_photo(chat_id, photo, caption="", reply_markup=None, parse_mode="HTML"):
    data = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": parse_mode
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    return send_telegram_request("sendPhoto", data)

def send_document(chat_id, file_path, caption="", reply_markup=None):
    if not os.path.exists(file_path):
        return None
    boundary = "----WebKitFormBoundaryVoice2Deal"
    lines = []
    lines.append(f"--{boundary}".encode("utf-8"))
    lines.append(f'Content-Disposition: form-data; name="chat_id"\r\n'.encode("utf-8"))
    lines.append(f"{chat_id}\r\n".encode("utf-8"))
    
    if caption:
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="caption"\r\n'.encode("utf-8"))
        lines.append(f"{caption}\r\n".encode("utf-8"))

    filename = os.path.basename(file_path)
    lines.append(f"--{boundary}".encode("utf-8"))
    lines.append(f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode("utf-8"))
    lines.append(b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n")
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    lines.append(file_bytes + b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode("utf-8"))

    body = b"\r\n".join(lines)
    req = urllib.request.Request(
        f"{TELEGRAM_API}/sendDocument",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"SendDocument Error: {e}", flush=True)
        return None

def answer_callback_query(callback_query_id, text=None, show_alert=False):
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
        data["show_alert"] = show_alert
    return send_telegram_request("answerCallbackQuery", data)

def download_telegram_file(file_id):
    res = send_telegram_request("getFile", {"file_id": file_id})
    if not res or not res.get("ok"):
        return None
    file_path = res["result"]["file_path"]
    download_url = f"{TELEGRAM_FILE_API}/{file_path}"
    try:
        with urllib.request.urlopen(download_url, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        print(f"File Download Error: {e}", flush=True)
        return None

def get_main_keyboard(role="owner"):
    if role == "owner":
        return {
            "keyboard": [
                [{"text": "🎙 Savdo / Qarz kiritish"}, {"text": "📊 Kassa hisoboti"}],
                [{"text": "⏳ Qarzdorlar daftari"}, {"text": "📦 Sklad & Tovar qoldiqlari"}],
                [{"text": "🧠 AI Biznes Maslahatchi"}, {"text": "📥 Excel hisobot"}],
                [{"text": "👥 Xodimlarim"}, {"text": "👑 Obuna & Tariflar"}],
                [{"text": "⚙️ Do'kon sozlamalari"}, {"text": "❓ Yordam & Support AI"}],
                [{"text": "🔄 Rolni o'zgartirish"}]
            ],
            "resize_keyboard": True
        }
    elif role == "seller":
        return {
            "keyboard": [
                [{"text": "🎙 Savdo / Qarz kiritish"}, {"text": "🔍 Mijoz qarzini tekshirish"}],
                [{"text": "📦 Ombor & Sklad qoldiqlari"}, {"text": "📊 Mening smenam (Kassa)"}],
                [{"text": "ℹ️ Mening do'konim"}, {"text": "❓ Yordam & Support AI"}],
                [{"text": "🔄 Rolni o'zgartirish"}]
            ],
            "resize_keyboard": True
        }
    else: # client
        return {
            "keyboard": [
                [{"text": "📋 Mening qarzlarim & Cheklarim"}],
                [{"text": "📱 Telefon raqamimni ulash (Qarzlarni topish)", "request_contact": True}],
                [{"text": "❓ Yordam & Qo'llanma"}, {"text": "🔄 Rolni o'zgartirish"}]
            ],
            "resize_keyboard": True
        }

def show_role_selection_screen(chat_id, user_name="Foydalanuvchi"):
    msg = f"👋 <b>Assalomu alaykum, {user_name}!</b>\n"
    msg += "«Voice2Deal — Ovozli Savdo & Qarz Daftari AI» tizimiga xush kelibsiz!\n\n"
    msg += "<b>Iltimos, botdan kim sifatida foydalanmoqchisiz?</b>\n"
    msg += "Quyidagi variantlardan birini tanlang:"
    
    inline_kb = {
        "inline_keyboard": [
            [{"text": "🏪 1. Yangi do'kon ochish (Do'kon Egasi)", "callback_data": "choose_role_owner"}],
            [{"text": "💼 2. Do'konga ulanish (Sotuvchi / Ishchi)", "callback_data": "choose_role_seller"}],
            [{"text": "👤 3. Xaridor (Qarzlarimni tekshirish)", "callback_data": "choose_role_client"}]
        ]
    }
    send_message(chat_id, msg, reply_markup=inline_kb)

def format_receipt(ai_data):
    op_type = ai_data.get("operation_type")
    client = ai_data.get("client_name") or "Noma'lum"
    total = format_number(ai_data.get("total_amount", 0))
    paid = format_number(ai_data.get("paid_amount", 0))
    debt = format_number(ai_data.get("debt_amount", 0))
    due_date = ai_data.get("due_date")
    items = ai_data.get("items") or []

    if op_type == "debt_payment":
        msg = "🏆 <b>TABRIKLAYMIZ! QARZ MUVAFFAQIYATLI QAYTARILDI!</b> 💰\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        if client and client != "Noma'lum":
            msg += f"👤 <b>Mijoz:</b> {client}\n"
        msg += f"✅ <b>Qabul qilingan summa:</b> +<b>{paid} so'm</b>\n"
        msg += "📈 <b>Do'koningiz kassa balansi va daromadi oshdi!</b>\n"
        if comment:
            msg += f"📝 <i>Izoh: {comment}</i>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "✅ <i>Kassa va qarz daftariga muvaffaqiyatli saqlandi!</i>"
        return msg

    type_titles = {
        "sale": "🧾 YANGI SOTUV & NASIYA",
        "expense": "📉 DO\'KON XARAJATI",
        "debt_give": "⏳ QARZ BERILDI"
    }
    header = type_titles.get(op_type, "🧾 SAVDO AMALI")

    msg = f"<b>{header}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    if client and client != "Noma'lum":
        msg += f"👤 <b>Mijoz:</b> {client}\n"

    if items:
        msg += "\n🛒 <b>Mahsulotlar:</b>\n"
        for idx, it in enumerate(items, 1):
            name = it.get("name", "Tovar")
            qty = it.get("qty", 1)
            p = format_number(it.get("price", 0))
            tot = format_number(it.get("total", 0))
            msg += f"  {idx}. {name} — {qty} x {p} = <b>{tot} so'm</b>\n"

    msg += "\n💰 <b>Hisob-kitob:</b>\n"
    if op_type == "expense":
        msg += f"  • Xarajat summasi: <b>{total} so'm</b>\n"
    else:
        msg += f"  • Jami summa: <b>{total} so'm</b>\n"
        msg += f"  • Naqd to'landi: <b>{paid} so'm</b>\n"
        if float(ai_data.get("debt_amount", 0)) > 0:
            msg += f"  • ⏳ <b>Nasiya (Qarz): {debt} so'm</b>\n"
            if due_date:
                msg += f"  • 📅 Qaytarish sanasi: <b>{due_date}</b>\n"

    comment = ai_data.get("comment")
    if comment:
        msg += f"\n📝 <i>Izoh: {comment}</i>\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "✅ <i>Kassa va qarz daftariga muvaffaqiyatli saqlandi!</i>"
    return msg

def handle_subscription_view(chat_id, ctx):
    store = ctx.get("store") or {}
    sub_info = check_subscription(store)
    
    msg = "👑 <b>VOICE2DEAL — OBUNA VA TARIFLAR</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🏪 <b>Do'kon:</b> {store.get('store_name', 'Mening do\'konim')}\n"
    msg += f"🆔 <b>Do'kon Kodi:</b> <code>{store.get('store_code', 'Noma\'lum')}</code>\n"
    msg += f"📊 <b>Joriy holat:</b> {sub_info['status_text']}\n\n"
    msg += "💡 <i>Bitta qaytgan qarz butun yillik obuna narxini 10 barobar qoplaydi!</i>\n\n"
    
    msg += "<b>Mavjud tariflar:</b>\n\n"
    msg += "🥉 <b>1. Basic (Bepul)</b> — <b>0 so'm / oy</b>\n"
    msg += "   • Oyiga 30 tagacha ovozli savdo kiritish\n"
    msg += "   • Oddiy kassa va qarzlar ro'yxati\n\n"

    msg += "🥈 <b>2. Standart (Tuzoq)</b> — <b>39 000 so'm / oy</b>\n"
    msg += "   • Cheksiz ovozli savdo kiritish\n"
    msg += "   • Sklad va tovarlar nazorati\n"
    msg += "   ❌ <i>Qarzdorlarga AI eslatmalar yo'q</i>\n"
    msg += "   ❌ <i>Xodimlarni ulash yo'q</i>\n\n"

    msg += "🥇 <b>3. VIP AI Avtopilot (Tavsiya etiladi ⭐)</b> — <b>45 000 so'm / oy</b>\n"
    msg += "   🔥 <b>Kuni atigi 1 500 so'm (bitta non narxi!)</b>\n"
    msg += "   • Cheksiz ovozli savdo kiritish\n"
    msg += "   • Qarzdorlarga avtomatik xushmuomala AI eslatmalar\n"
    msg += "   • QR-kodli va termal cheklar chiqarish\n"
    msg += "   • Cheksiz xodimlar (sotuvchilar) ulash\n"
    msg += "   • Excel va Google Sheets sinxronizatsiyasi\n\n"
    
    msg += "👑 <b>4. Yillik VIP (45% Chegirma)</b> — <b>290 000 so'm / yil</b>\n"
    msg += "   • Kuni atigi 800 so'm!\n"
    msg += "   • 12 oy davomida to'liq VIP imkoniyatlar\n\n"
    msg += "<i>To'lov qilish uchun tarifni tanlang:</i>"
    
    inline_kb = {
        "inline_keyboard": [
            [{"text": "🥉 1. Bepul Basic (0 so'm)", "callback_data": "plan_basic_free"}],
            [{"text": "🥈 2. Standart (39 000 so'm)", "callback_data": "pay_plan_monthly_standard"}],
            [{"text": "🥇 3. VIP AI Avtopilot (45 000 so'm) ⭐", "callback_data": "pay_plan_monthly_vip"}],
            [{"text": "👑 4. Yillik VIP (290 000 so'm) — 45% chegirma", "callback_data": "pay_plan_yearly_vip"}],
            [{"text": "🎁 1 oylik sinovni faollashtirish (Test)", "callback_data": "activate_test_sub"}]
        ]
    }
    send_message(chat_id, msg, reply_markup=inline_kb)

def handle_help_menu(chat_id, ctx):
    store = ctx.get("store") or {}
    store_name = store.get("store_name", "Do'koningiz")
    store_code = store.get("store_code", "Noma'lum")
    
    msg = "❓ <b>VOICE2DEAL — YORDAM VA QO'LLAB-QUVVATLASH MARKAZI</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🏪 <b>Do'kon:</b> {store_name} (Kodi: <code>{store_code}</code>)\n\n"
    msg += "Sizga qanday yordam kerak? Quyidagi bo'limlardan birini tanlang yoki <b>24/7 AI Maslahatchi</b>ga savolingizni bering:\n\n"
    msg += "🤖 <b>1. 24/7 AI Maslahatchi</b> — Barcha savollaringizga darhol o'zbek tilida javob beradi.\n"
    msg += "👨‍💻 <b>2. Adminga murojaat</b> — Tirik mutaxassisga to'g'ridan-to'g'ri xabar yuborish.\n"
    msg += "📚 <b>3. Tezkor yo'riqnomalar</b> — Ovozli savdo, ombor va xodimlarni boshqarish."
    
    inline_kb = {
        "inline_keyboard": [
            [{"text": "🧠 24/7 AI Maslahatchiga savol berish", "callback_data": "help_ask_ai"}],
            [{"text": "👨‍💻 Adminga xabar yuborish (Tirik mutaxassis)", "callback_data": "help_contact_admin"}],
            [{"text": "🎙 Ovozli savdo yo'riqnomasi", "callback_data": "help_faq_voice"}],
            [{"text": "📦 Ombor (Sklad) yo'riqnomasi", "callback_data": "help_faq_sklad"}],
            [{"text": "👥 Xodimlarni ulash yo'riqnomasi", "callback_data": "help_faq_staff"}],
            [{"text": "👑 Obuna va to'lov yo'riqnomasi", "callback_data": "help_faq_billing"}]
        ]
    }
    send_message(chat_id, msg, reply_markup=inline_kb)

def handle_store_settings_view(chat_id, ctx):
    if not ctx["is_owner"]:
        send_message(chat_id, "🔒 <i>Do'kon sozlamalari faqat do'kon egasi uchun ochiq.</i>")
        return
        
    store = ctx["store"] or {}
    store_name = store.get("store_name", "Mening Do'konim")
    store_code = store.get("store_code", "Noma'lum")
    owner_name = store.get("owner_name", "Do'kon Egasi")
    sub_info = check_subscription(store)
    
    msg = "⚙️ <b>DO'KON SOZLAMALARI VA BOSHQARUV</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🏪 <b>Do'kon nomi:</b> <b>{store_name}</b>\n"
    msg += f"🆔 <b>Do'kon Kodi:</b> <code>{store_code}</code>\n"
    msg += f"👤 <b>Do'kon Egasi:</b> {owner_name}\n"
    msg += f"👑 <b>Obuna holati:</b> {sub_info['status_text']}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "<i>Quyidagi amallardan birini tanlang:</i>"
    
    inline_kb = {
        "inline_keyboard": [
            [{"text": "✏️ Do'kon nomini o'zgartirish", "callback_data": "change_store_name"}],
            [{"text": "👥 Xodimlarni boshqarish", "callback_data": "settings_view_staff"}],
            [{"text": "👑 Obuna & Tariflar", "callback_data": "settings_view_billing"}],
            [{"text": "🔄 Rolni almashtirish", "callback_data": "settings_change_role"}]
        ]
    }
    send_message(chat_id, msg, reply_markup=inline_kb)

def handle_staff_view(chat_id, ctx):
    if not ctx["is_owner"]:
        send_message(chat_id, "🔒 <i>Bu bo'lim faqat do'kon egasi uchun ochiq.</i>")
        return
        
    store = ctx["store"]
    store_code = store.get("store_code", "Noma'lum")
    staff_list = get_store_staff(chat_id)
    
    msg = "👥 <b>XODIMLAR VA SOTUVCHILAR NAZORATI</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🏪 <b>Do'kon:</b> {store.get('store_name', 'Mening do\'konim')}\n"
    msg += f"🆔 <b>Do'kon Kodi:</b> <code>{store_code}</code>\n"
    msg += f"🔗 <b>Sotuvchi ulanish havolasi:</b>\n<code>https://t.me/Ovozli_SavdoBOT?start={store_code}</code>\n\n"
    msg += f"<i>Sotuvchingiz ushbu havolani bossa yoki botga <code>{store_code}</code> kodini yozsa, do'koningizga avtomatik biriktiriladi.</i>\n\n"
    
    inline_buttons = []
    if staff_list:
        msg += "<b>Biriktirilgan faol sotuvchilar:</b>\n"
        for idx, s in enumerate(staff_list, 1):
            name = s.get("name") or "Sotuvchi"
            username = f" (@{s['username']})" if s.get("username") else ""
            msg += f"  {idx}. 💼 <b>{name}</b>{username}\n"
            inline_buttons.append([{"text": f"❌ {name}ni o'chirish", "callback_data": f"delstaff_{s['id']}"}])
    else:
        msg += "<i>Hozircha biriktirilgan sotuvchilar yo'q.</i>\n"
        
    markup = {"inline_keyboard": inline_buttons} if inline_buttons else None
    send_message(chat_id, msg, reply_markup=markup)

def handle_client_debts_view(chat_id):
    debts = get_client_debts_by_telegram_id(chat_id)
    msg = "👤 <b>XARIDOR PROFILI & QARZLAR</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    if debts:
        msg += "<b>Sizning do'konlardagi nasiya hisoblaringiz:</b>\n\n"
        for idx, d in enumerate(debts, 1):
            store_name = d.get("store_name", "Do'kon")
            debt_sum = format_number(d.get("total_debt", 0))
            last_date = str(d.get("last_deal_date", ""))[:10]
            msg += f"{idx}. 🏪 <b>{store_name}</b> (Kodi: <code>{d['store_code']}</code>)\n"
            msg += f"   • Nasiya: <b>{debt_sum} so'm</b>\n"
            msg += f"   • Oxirgi xarid: {last_date}\n\n"
    else:
        msg += "🎉 <b>Sizda hech qaysi do'konda qarzdorlik mavjud emas!</b>\n\n"
        msg += "<i>Agar do'konda boshqa telefon raqam yoki ism bilan yozilgan bo'lsangiz, do'kon egasiga Telegram akkauntingizni ayting.</i>\n\n"
        msg += "💡 <b>Siz do'kon egasi yoki sotuvchimisiz?</b>\n"
        msg += "Rolingizni o'zgartirish uchun /rol buyrug'ini bosing."
        
    send_message(chat_id, msg, reply_markup=get_main_keyboard(role="client"))

def handle_update(update):
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb["id"]
        chat_id = cb["message"]["chat"]["id"]
        data = cb.get("data", "")
        from_user = cb.get("from", {})
        first_name = from_user.get("first_name", "Foydalanuvchi")
        username = from_user.get("username", "")

        # 1. Rol tanlash
        if data == "choose_role_owner":
            store = create_store_for_owner(chat_id, owner_name=first_name)
            answer_callback_query(cb_id, "Do'kon muvaffaqiyatli yaratildi!")
            
            resp = f"🎉 <b>Tabriklaymiz, {first_name}!</b>\n\n"
            resp += f"Sizning do'koningiz yaratildi:\n"
            resp += f"🏪 <b>Do'kon:</b> {store['store_name']}\n"
            resp += f"🆔 <b>Do'kon Kodi:</b> <code>{store['store_code']}</code>\n"
            resp += f"🎁 <b>Sinov muddati:</b> 14 kun bepul faol!\n\n"
            resp += "Sotuvchilaringizni ulash uchun <code>👥 Xodimlarim</code> bo'limidan foydalanishingiz mumkin.\n\n"
            resp += "🎙 Savdo kiritish uchun ovozli xabar (Voice) yoki matn yuboring!"
            send_message(chat_id, resp, reply_markup=get_main_keyboard(role="owner"))
            return

        elif data == "choose_role_seller":
            USER_STATES[chat_id] = "waiting_for_store_code"
            answer_callback_query(cb_id)
            msg = "💼 <b>Sotuvchi / Ishchi sifatida ulanish</b>\n\n"
            msg += "Iltimos, do'kon egasi bergan <b>Do'kon Kodini</b> yozib yuboring:\n"
            msg += "<i>(Masalan: <code>DK-1052</code>)</i>"
            send_message(chat_id, msg)
            return

        elif data == "choose_role_client":
            set_user_role(chat_id, "client")
            answer_callback_query(cb_id, "Xaridor rejimi faollashtirildi!")
            handle_client_debts_view(chat_id)
            return

        elif data.startswith("receipt_"):
            tx_id = data.split("_")[1]
            ctx = get_user_context(chat_id, first_name, username)
            store = ctx["store"] or {}
            recent = get_recent_transactions(chat_id, limit=5)
            target_tx = next((t for t in recent if str(t["id"]) == str(tx_id)), recent[0] if recent else {})
            
            thermal_text = generate_thermal_receipt_text(target_tx, store)
            answer_callback_query(cb_id, "Chek tayyorlandi!")
            send_message(chat_id, f"<pre>{thermal_text}</pre>")
            return

        elif data.startswith("delstaff_"):
            staff_id = int(data.split("_")[1])
            remove_staff_member(chat_id, staff_id)
            answer_callback_query(cb_id, "Xodim do'kondan o'chirildi!", show_alert=True)
            ctx = get_user_context(chat_id, first_name, username)
            handle_staff_view(chat_id, ctx)
            return
        elif data == "refresh_inventory":
            inv_list = get_inventory_list(chat_id)
            msg_text = "📦 <b>OMBOR VA TOVAR QOLDIQLARI (SKLAD)</b>\n"
            msg_text += "━━━━━━━━━━━━━━━━━━━━━━\n"
            if inv_list:
                for idx, item in enumerate(inv_list, 1):
                    name = item["name"]
                    qty = int(item["quantity"])
                    unit = item.get("unit", "dona")
                    cost = format_number(item.get("cost_price", 0))
                    sell = format_number(item.get("selling_price", 0))
                    status_icon = "🟢" if qty > item.get("min_alert_qty", 5) else "🔴 (Kam qoldi!)"
                    msg_text += f"{idx}. <b>{name}</b> — <b>{qty} {unit}</b> {status_icon}\n"
                    if float(item.get("cost_price", 0)) > 0 or float(item.get("selling_price", 0)) > 0:
                        msg_text += f"   • Tan narxi: {cost} so'm | Sotilishi: {sell} so'm\n"
            else:
                msg_text += "<i>Hozircha omborda tovarlar mavjud emas.</i>\n\n"
            msg_text += "\n🎙 <b>Kiritish usuli:</b> <i>«Skladga 50 dona Coca-Cola 12000 so'mdan qo'sh»</i>"
            answer_callback_query(cb_id, "Qoldiqlar yangilandi")
            send_message(chat_id, msg_text)
            return

        elif data == "guide_inventory":
            msg_g = "🎙 <b>OMBORGA TOVAR KIRITISH BO'YICHA YO'RIQNOMA</b>\n\n"
            msg_g += "Siz tovarlarni ovozli yoki matnli xabar orqali kiritishingiz mumkin:\n\n"
            msg_g += "<b>1. Ovozli xabar bilan (Voice):</b>\n"
            msg_g += "Mikrofonni bosib ayting:\n"
            msg_g += "<i>«Skladga 50 dona Coca-Cola 1.5L 12000 so'mdan qo'sh»</i>\n"
            msg_g += "<i>«Omborga 100 ta moy filtr kirdi»</i>\n"
            msg_g += "<i>«30 ta Snickers 8000 so'mdan kiritdim»</i>\n\n"
            msg_g += "<b>2. Matn orqali:</b>\n"
            msg_g += "Shunchaki chatga yozing:\n"
            msg_g += "<i>«Skladga 20 ta non 3000 dan»</i>\n\n"
            msg_g += "⚡️ <i>Bot tovar nomi, miqdori va narxini avtomatik ajratib olib skladga qo'shadi!</i>"
            answer_callback_query(cb_id)
            send_message(chat_id, msg_g)
            return

        elif data.startswith("remind_"):
            try:
                client_id = int(data.split("_")[1])
                client = get_client_by_id(client_id)
                if client:
                    ctx = get_user_context(chat_id, first_name, username)
                    store_name = ctx["store"].get("store_name", "Do'konimiz") if ctx["store"] else "Do'konimiz"
                    reminder_text = generate_gentle_reminder(
                        client["name"], 
                        client["total_debt"], 
                        store_name=store_name
                    )
                    record_reminder_sent(client_id)
                    share_url = generate_telegram_share_link(reminder_text)
                    
                    msg = f"🔔 <b>{client['name']} uchun xushmuomala eslatma matni:</b>\n\n"
                    msg += f"<blockquote>{reminder_text}</blockquote>\n\n"
                    msg += "📲 <i>Pastdagi tugma orqali eslatmani to'g'ridan-to'g'ri mijozga Telegramda yuborishingiz mumkin:</i>"
                    
                    remind_kb = {
                        "inline_keyboard": [
                            [{"text": "🚀 Mijozga Telegram orqali yuborish", "url": share_url}],
                            [{"text": "🔄 Qayta generatsiya qilish", "callback_data": f"remind_{client_id}"}]
                        ]
                    }
                    answer_callback_query(cb_id, "Eslatma matni tayyorlandi!")
                    send_message(chat_id, msg, reply_markup=remind_kb)
                else:
                    answer_callback_query(cb_id, "Mijoz topilmadi!", show_alert=True)
            except Exception as e:
                answer_callback_query(cb_id, f"Xatolik: {e}")
            return

        elif data == "confirm_trade_yes":
            pending = PENDING_CONFIRMATIONS.pop(chat_id, None)
            USER_STATES.pop(chat_id, None)
            if not pending:
                answer_callback_query(cb_id, "Amal muddati tugagan yoki tasdiqlangan.", show_alert=True)
                return
            answer_callback_query(cb_id, "✅ Savdo tasdiqlandi!")
            execute_confirmed_transactions(chat_id, pending)
            return

        elif data == "confirm_trade_edit":
            USER_STATES[chat_id] = "waiting_for_trade_edit"
            answer_callback_query(cb_id, "✏️ Tahrirlash rejimi")
            send_message(
                chat_id, 
                "✍️ <i>Iltimos, to'g'rilangan ma'lumotni ovozda ayting yoki yozib yuboring:</i>\n"
                "<i>(Masalan: «Eshmat akaga 450 ming nasiyaga berdim»)</i>"
            )
            return

        elif data == "confirm_trade_cancel":
            PENDING_CONFIRMATIONS.pop(chat_id, None)
            USER_STATES.pop(chat_id, None)
            answer_callback_query(cb_id, "🚫 Savdo bekor qilindi", show_alert=True)
            send_message(chat_id, "🚫 <i>Savdo amali bekor qilindi. Kassa o'zgarishsiz qoldi.</i>")
            return


        elif data == "plan_basic_free":
            answer_callback_query(cb_id, "Siz Bepul Basic tarifidasiz (Oyiga 30 ta savdo)!", show_alert=True)
            return

        elif data.startswith("lang_"):
            lang = data.replace("lang_", "")
            ctx = get_user_context(chat_id, first_name, username)
            if not ctx["is_registered"]:
                create_store_for_owner(chat_id, owner_name=first_name, store_name=f"{first_name} do'koni")
                ctx = get_user_context(chat_id, first_name, username)
            answer_callback_query(cb_id, "Til tanlandi!")
            if lang == "ru":
                msg_start = f"👋 <b>Здравствуйте, {first_name}!</b>\n\n"
                msg_start += "🎉 <b>Давайте сразу проверим, как работает система!</b>\n"
                msg_start += "Пока не нужны ни ваше имя, ни название магазина.\n\n"
                msg_start += "🎙 <b>Просто отправьте одно голосовое сообщение:</b>\n"
                msg_start += "<i>(Например: «Дал Акмалю масло на 50 тысяч, оплатил 20 тысяч, 30 тысяч в долг до понедельника»)\n\n"
                msg_start += "или напишите текстом ниже 👇</i>"
            else:
                msg_start = f"👋 <b>Assalomu alaykum, {first_name}!</b>\n\n"
                msg_start += "🎉 <b>Keling, tizim qanday ishlashini darhol sinab ko‘ramiz!</b>\n"
                msg_start += "Hozircha ismingiz ham, do‘kon nomi ham shart emas.\n\n"
                msg_start += "🎙 <b>Shunchaki bitta ovozli xabar yuboring:</b>\n"
                msg_start += "<i>(Masalan: «Akmal akaga 50 minglik moy berdim, 20 ming to‘ladi, 30 mingi dushanbagacha nasiya»)\n\n"
                msg_start += "yoki pastga matn ko‘rinishida yozing 👇</i>"
            send_message(chat_id, msg_start, reply_markup=get_main_keyboard(role="owner"))
            return

        elif data == "activate_test_sub":
            activate_subscription(chat_id, plan="monthly", days=30)
            answer_callback_query(cb_id, "1 oylik Standart obuna muvaffaqiyatli faollashtirildi!", show_alert=True)
            ctx = get_user_context(chat_id, first_name, username)
            handle_subscription_view(chat_id, ctx)
            return

        
        # --- SUPER ADMIN PANEL CALLBACKS ---
        elif data == "admin_home":
            msg = admin_panel.get_admin_dashboard_message()
            kb = admin_panel.get_admin_dashboard_keyboard()
            answer_callback_query(cb_id)
            send_message(chat_id, msg, reply_markup=kb)
            return

        elif data.startswith("admin_stores_"):
            page = int(data.split("_")[2])
            msg, kb = admin_panel.get_admin_stores_page(page=page)
            answer_callback_query(cb_id)
            send_message(chat_id, msg, reply_markup=kb)
            return

        elif data == "admin_sync_sheets":
            answer_callback_query(cb_id, "Google Sheets ga sinxronlanmoqda...", show_alert=False)
            res = google_sheets_sync.sync_all_data_to_sheets()
            if res.get("success"):
                send_message(chat_id, "✅ <b>Google Sheets bilan muvaffaqiyatli sinxronlashtirildi!</b>\nBarcha do'konlar, kassa va mijozlar jadvalga to'liq yangilandi.")
            else:
                err = res.get("error", "Noma'lum xatolik")
                send_message(chat_id, f"⚠️ <b>Sinxronlashda xatolik:</b> {err}\n\nIltimos, Webhook URL to'g'ri sozlanganini tekshiring.")
            return

        elif data == "admin_setup_sheets":
            USER_STATES[chat_id] = "waiting_for_sheets_url"
            msg = "🔗 <b>GOOGLE SHEETS WEBHOOK URL NI SOZLASH</b>\n\n"
            msg += "Google Apps Script dan olgan Webhook URL (havola)ingizni shu yerga yuboring.\n"
            msg += "<i>Masalan: https://script.google.com/macros/s/.../exec</i>"
            answer_callback_query(cb_id)
            send_message(chat_id, msg)
            return

        elif data == "admin_export_data":
            answer_callback_query(cb_id, "Fayl tayyorlanmoqda...")
            csv_path = admin_panel.export_all_saas_data_csv()
            if csv_path and os.path.exists(csv_path):
                send_document(chat_id, csv_path, caption="📊 <b>Barcha Do'konlar va SaaS Ma'lumotlari (CSV)</b>")
            else:
                send_message(chat_id, "⚠️ Eksport qilishda xatolik yuz berdi.")
            return

        elif data.startswith("pay_plan_"):
            plan_code = data.replace("pay_plan_", "")
            plan_info = {
                "monthly_standard": {"title": "🥈 Standart", "amount": "39 000", "days": 30, "plan": "standard"},
                "monthly_vip": {"title": "🥇 VIP AI Avtopilot ⭐", "amount": "45 000", "days": 30, "plan": "monthly"},
                "yearly_vip": {"title": "👑 Yillik VIP (45% Chegirma)", "amount": "290 000", "days": 365, "plan": "yearly"}
            }.get(plan_code, {"title": "🥇 VIP AI Avtopilot ⭐", "amount": "45 000", "days": 30, "plan": "monthly"})
            
            USER_STATES[chat_id] = {
                "state": "waiting_for_payment_receipt",
                "plan_title": plan_info["title"],
                "amount": plan_info["amount"],
                "days": plan_info["days"],
                "plan_code": plan_info["plan"]
            }
            
            pay_msg = "💳 <b>TO'LOV MA'LUMOTLARI</b>\n"
            pay_msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
            pay_msg += f"📌 <b>Tanlangan tarif:</b> {plan_info['title']}\n"
            pay_msg += f"💰 <b>To'lov summasi:</b> <b>{plan_info['amount']} so'm</b>\n\n"
            pay_msg += "💳 <b>Karta raqami:</b> <code>4916 9903 0500 7954</code>\n"
            pay_msg += "👤 <b>Karta egasi:</b> <b>JAVOHIRBEK A.</b>\n"
            pay_msg += "🏦 <b>To'lov ilovalari:</b> Click / Payme / Uzum / Anorbank\n\n"
            pay_msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
            pay_msg += "⚠️ <b>MUHIM QADAM:</b>\n"
            pay_msg += "To'lovni amalga oshirgach, <b>to'lov chekining skrinshoti yoki kvitansiya rasmini</b> to'g'ridan-to'g'ri shu chatga yuboring!\n\n"
            pay_msg += "📸 <i>Chek rasmi kelishi bilan u admin (ID: 1320855100) ga yetib boradi va tasdiqlangach obunangiz bir zumda faollashadi.</i>"
            
            cancel_kb = {"inline_keyboard": [[{"text": "❌ To'lovni bekor qilish", "callback_data": "cancel_payment"}]]}
            answer_callback_query(cb_id)
            send_message(chat_id, pay_msg, reply_markup=cancel_kb)
            return

        elif data == "cancel_payment":
            USER_STATES.pop(chat_id, None)
            answer_callback_query(cb_id, "To'lov bekor qilindi.")
            ctx = get_user_context(chat_id, first_name, username)
            handle_subscription_view(chat_id, ctx)
            return

        elif data.startswith("approve_sub_"):
            parts = data.split("_")
            target_user_id = int(parts[2])
            plan_code = parts[3]
            days = int(parts[4])
            
            new_end = activate_subscription(target_user_id, plan=plan_code, days=days)
            answer_callback_query(cb_id, f"Obuna {days} kunga muvaffaqiyatli yoqildi!", show_alert=True)
            
            admin_confirm_msg = "✅ <b>TO'LOV TASDIQLANDI!</b>\n\n"
            admin_confirm_msg += f"👤 Foydalanuvchi: <code>{target_user_id}</code>\n"
            admin_confirm_msg += f"👑 Tarif: <b>{plan_code.upper()}</b>\n"
            admin_confirm_msg += f"📅 Yangi muddat: <b>{new_end}</b> ({days} kun)"
            send_message(chat_id, admin_confirm_msg)
            
            user_target_ctx = get_user_context(target_user_id)
            store_name = user_target_ctx["store"].get("store_name", "Do'koningiz") if user_target_ctx.get("store") else "Do'koningiz"
            user_notify = f"🎉 <b>TABRIKLAYMIZ! To'lovingiz tasdiqlandi!</b>\n\n"
            user_notify += f"🏪 <b>Do'kon:</b> {store_name}\n"
            user_notify += f"👑 <b>Faollashtirilgan tarif:</b> {plan_code.capitalize()}\n"
            user_notify += f"📅 <b>Amal qilish muddati:</b> {new_end} gacha ({days} kun)\n\n"
            user_notify += "Barcha imkoniyatlardan to'liq va cheksiz foydalanishingiz mumkin! 🚀"
            send_message(target_user_id, user_notify, reply_markup=get_main_keyboard(role="owner"))
            return

        elif data.startswith("reject_sub_"):
            target_user_id = int(data.split("_")[2])
            answer_callback_query(cb_id, "To'lov cheki rad etildi.", show_alert=True)
            send_message(chat_id, f"❌ Foydalanuvchi (ID: <code>{target_user_id}</code>) to'lovi rad etildi.")
            
            user_notify = "⚠️ <b>To'lov chekingiz tasdiqlanmadi.</b>\n\n"
            user_notify += "Iltimos, to'lov muvaffaqiyatli amalga oshganini tekshirib, chekni qaytadan yuboring yoki admin bilan bog'laning."
            send_message(target_user_id, user_notify)
            return

        # --- YORDAM VA SUPPORT CALLBACKS ---
        elif data == "help_ask_ai":
            USER_STATES[chat_id] = "waiting_for_ai_support_question"
            answer_callback_query(cb_id)
            msg_h = "🤖 <b>24/7 AI MASLAHATCHI (SCRIPTBOT AI)</b>\n"
            msg_h += "━━━━━━━━━━━━━━━━━━━━━━\n"
            msg_h += "Voice2Deal tizimi, savdo kiritish, sklad, xodimlar yoki qarzlar bo'yicha har qanday savolingizni <b>ovozli xabar (Voice)</b> yoki <b>matn</b> ko'rinishida yuboring:\n\n"
            msg_h += "<i>(Masalan: «Qarzdorlarga eslatmani qanday yuboraman?», «Sotuvchimni qanday ulayman?»)</i>"
            send_message(chat_id, msg_h)
            return

        elif data == "help_contact_admin":
            USER_STATES[chat_id] = "waiting_for_admin_ticket"
            answer_callback_query(cb_id)
            msg_t = "👨‍💻 <b>TIRIK MUTAXASSIS / ADMINGA MUROJAAT</b>\n"
            msg_t += "━━━━━━━━━━━━━━━━━━━━━━\n"
            msg_t += "Iltimos, savolingiz, muammoingiz yoki taklifingizni yozib yuboring (matn, ovoz yoki rasm skrinshot):\n\n"
            msg_t += "📩 <i>Xabaringiz to'g'ridan-to'g'ri admin (ID: 1320855100) ga yetkaziladi va tez orada sizga javob beriladi.</i>"
            send_message(chat_id, msg_t)
            return

        elif data == "help_faq_voice":
            answer_callback_query(cb_id)
            msg_v = "🎙 <b>OVOZLI VA MATNLI SAVDO KIRITISH YO'RIQNOMASI</b>\n"
            msg_v += "━━━━━━━━━━━━━━━━━━━━━━\n"
            msg_v += "Bot har qanday sheva va so'zlarni tushunadi. Mikrofonni bosib quyidagicha gapiring:\n\n"
            msg_v += "1️⃣ <b>Savdo va qarz:</b>\n"
            msg_v += "<i>«Akmal akaga 2 ta moy filtr berdim 50 mingdan, 30 mingini berdi, 70 ming qarz»</i>\n\n"
            msg_v += "2️⃣ <b>Qarz to'lovi (bitta yoki bir nechta odam):</b>\n"
            msg_v += "<i>«Islomxon aka 70 ming, Javohir 50 ming qarzlarini to'lashdi»</i>\n\n"
            msg_v += "3️⃣ <b>Qarz berildi (nasiya):</b>\n"
            msg_v += "<i>«Sardor aka 100 ming qarz oldi»</i>\n\n"
            msg_v += "4️⃣ <b>Do'kon xarajati:</b>\n"
            msg_v += "<i>«Arendaga 1 million to'ladim»</i>\n\n"
            msg_v += "5️⃣ <b>Omborga kirim:</b>\n"
            msg_v += "<i>«Skladga 50 ta kola 12 mingdan kirdi»</i>"
            send_message(chat_id, msg_v)
            return

        elif data == "help_faq_sklad":
            answer_callback_query(cb_id)
            msg_s = "📦 <b>OMBOR VA SKLAD QOLDIQLARI YO'RIQNOMASI</b>\n"
            msg_s += "━━━━━━━━━━━━━━━━━━━━━━\n"
            msg_s += "1. <b>Kirim qilish:</b> <i>«Skladga 100 ta moy filtr 30 mingdan qo'sh»</i> deb ovoz yuboring.\n"
            msg_s += "2. <b>Avtomatik kamayish:</b> Tovar sotilganida (masalan: <i>«2 ta filtr sotdim»</i>) ombordagi soni avtomatik kamayadi.\n"
            msg_s += "3. <b>Ogohlantirish:</b> Tovar soni 5 tadan kam qolganda bot qizil belgi bilan eslatadi.\n"
            msg_s += "4. <b>Qoldiqlarni ko'rish:</b> <code>📦 Sklad & Tovar qoldiqlari</code> tugmasini bosing."
            send_message(chat_id, msg_s)
            return

        elif data == "help_faq_staff":
            answer_callback_query(cb_id)
            msg_st = "👥 <b>XODIMLAR VA SOTUVCHILARNI ULASH YO'RIQNOMASI</b>\n"
            msg_st += "━━━━━━━━━━━━━━━━━━━━━━\n"
            msg_st += "1. <code>👥 Xodimlarim</code> bo'limiga kiring.\n"
            msg_st += "2. Do'koningiz uchun berilgan <b>Do'kon Kodi</b>ni (masalan: <code>DK-8977</code>) yoki taklif havolasini sotuvchingizga yuboring.\n"
            msg_st += "3. Sotuvchi botga kirib ushbu kodni yuborsa, darhol do'koningizga biriktiriladi.\n"
            msg_st += "4. Sotuvchining barcha kiritgan savdolari real-time sizning kassa hisobotingizga tushadi."
            send_message(chat_id, msg_st)
            return

        elif data == "help_faq_billing":
            answer_callback_query(cb_id)
            msg_b = "👑 <b>OBUNA VA TO'LOV QILISH YO'RIQNOMASI</b>\n"
            msg_b += "━━━━━━━━━━━━━━━━━━━━━━\n"
            msg_b += "1. <code>👑 Obuna & Tariflar</code> bo'limidan o'zingizga ma'qul tarifni tanlang.\n"
            msg_b += "2. Ko'rsatilgan karta raqamiga (<code>4916 9903 0500 7954</code> JAVOHIRBEK A.) to'lov qiling.\n"
            msg_b += "3. To'lov cheki skrinshotini botga yuboring.\n"
            msg_b += "4. Admin tekshirib tasdiqlashi bilan obunangiz bir zumda yoqiladi!"
            send_message(chat_id, msg_b)
            return

        elif data.startswith("support_reply_"):
            target_user_id = int(data.split("_")[2])
            USER_STATES[chat_id] = {
                "state": "admin_replying_to_ticket",
                "target_user_id": target_user_id
            }
            answer_callback_query(cb_id)
            send_message(chat_id, f"✍️ <b>Foydalanuvchi (ID: <code>{target_user_id}</code>) uchun javob xabaringizni yozing:</b>\n<i>(Matn, ovoz yoki rasm yuborishingiz mumkin)</i>")
            return

        # --- DO'KON SOZLAMALARI CALLBACKS ---
        elif data == "change_store_name":
            USER_STATES[chat_id] = "waiting_for_new_store_name"
            answer_callback_query(cb_id)
            msg_sn = "🏪 <b>DO'KON NOMINI O'ZGARTIRISH</b>\n\n"
            msg_sn += "Do'koningiz uchun yangi nomni yozib yuboring:\n"
            msg_sn += "<i>(Masalan: «Grand Supermarket», «Avtozapchast 777», «Omonat Bakkol»)</i>"
            send_message(chat_id, msg_sn)
            return

        elif data == "settings_view_staff":
            answer_callback_query(cb_id)
            ctx = get_user_context(chat_id, first_name, username)
            handle_staff_view(chat_id, ctx)
            return

        elif data == "settings_view_billing":
            answer_callback_query(cb_id)
            ctx = get_user_context(chat_id, first_name, username)
            handle_subscription_view(chat_id, ctx)
            return

        elif data == "settings_change_role":
            answer_callback_query(cb_id)
            show_role_selection_screen(chat_id, first_name)
            return

        answer_callback_query(cb_id)
        return

    if "message" not in update:
        return

    msg = update["message"]
    chat_id = msg["chat"]["id"]
    from_user = msg.get("from", {})
    sender_name = from_user.get("first_name", "Foydalanuvchi")
    username = from_user.get("username", "")
    text = msg.get("text", "")
    voice = msg.get("voice") or msg.get("audio")

    # Telegram Contact qabul qilish (Xaridor telefon raqamini bog'lash)
    contact = msg.get("contact")
    if contact:
        phone = contact.get("phone_number", "").replace("+", "").strip()
        conn = database.get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET phone = ? WHERE telegram_id = ?", (phone, chat_id))
        # O'sha telefon raqamga tegishli barcha do'konlardagi qarz yozuvlarini ushbu telegram_id ga ulaymiz
        c.execute("UPDATE clients SET telegram_id = ? WHERE phone = ? OR phone LIKE ?", (chat_id, phone, f"%{phone[-9:]}%"))
        conn.commit()
        conn.close()
        send_message(chat_id, f"🎉 <b>Rahmat, {sender_name}!</b>\nSizning telefon raqamingiz (+{phone}) tizimga muvaffaqiyatli bog'landi!\n\nEndi barcha do'konlardagi qarzlaringiz avtomatik aniqlanadi.")
        handle_client_debts_view(chat_id)
        return

    # To'lov Cheki (Photo) qabul qilish
    photo = msg.get("photo")
    if photo:
        highest_photo = photo[-1]["file_id"]
        user_state = USER_STATES.get(chat_id)
        
        ctx = get_user_context(chat_id, sender_name, username)
        store = ctx.get("store") or {}
        store_name = store.get("store_name", "Do'kon")
        store_code = store.get("store_code", "Noma'lum")
        
        plan_title = "1️⃣ Oylik Standart"
        amount = "49 000"
        days = 30
        plan_code = "monthly"
        
        if isinstance(user_state, dict) and user_state.get("state") == "waiting_for_payment_receipt":
            plan_title = user_state.get("plan_title", plan_title)
            amount = user_state.get("amount", amount)
            days = user_state.get("days", days)
            plan_code = user_state.get("plan_code", plan_code)
            USER_STATES.pop(chat_id, None)
            
        ADMIN_ID = 1320855100
        
        admin_caption = "🔔 <b>YANGI TO'LOV CHEKI KELDI!</b>\n"
        admin_caption += "━━━━━━━━━━━━━━━━━━━━━━\n"
        admin_caption += f"👤 <b>Mijoz:</b> {sender_name} (@{username})\n"
        admin_caption += f"🆔 <b>Telegram ID:</b> <code>{chat_id}</code>\n"
        admin_caption += f"🏪 <b>Do'kon:</b> {store_name} (<code>{store_code}</code>)\n"
        admin_caption += f"📌 <b>Tarif:</b> {plan_title}\n"
        admin_caption += f"💰 <b>Summa:</b> <b>{amount} so'm</b> ({days} kun)\n"
        admin_caption += "━━━━━━━━━━━━━━━━━━━━━━\n"
        admin_caption += "Chekni tekshirib, quyidagi tugmani bosing:"
        
        admin_kb = {
            "inline_keyboard": [
                [{"text": f"✅ Tasdiqlash ({days} kun)", "callback_data": f"approve_sub_{chat_id}_{plan_code}_{days}"}],
                [{"text": "❌ Rad etish (Bekor qilish)", "callback_data": f"reject_sub_{chat_id}"}]
            ]
        }
        
        send_photo(ADMIN_ID, highest_photo, caption=admin_caption, reply_markup=admin_kb)
        
        user_msg = "✅ <b>To'lov chekingiz qabul qilindi!</b>\n\n"
        user_msg += "⏳ Chek tekshirish uchun adminga yuborildi.\n"
        user_msg += "Admin tasdiqlashi bilan obunangiz avtomatik yoqiladi va sizga darhol xabar beriladi."
        send_message(chat_id, user_msg)
        return


    ADMIN_ID = 1320855100
    ctx = get_user_context(chat_id, sender_name, username)
    user_state = USER_STATES.get(chat_id)

    # 1. Admin foydalanuvchiga javob qaytarmoqda (Admin replying to user ticket)
    if isinstance(user_state, dict) and user_state.get("state") == "admin_replying_to_ticket":
        target_user = user_state.get("target_user_id")
        USER_STATES.pop(chat_id, None)
        
        reply_content = text or (voice and "🎤 [Ovozli javob]") or "📸 [Rasm]"
        user_notification = "👨‍💻 <b>VOICE2DEAL QO'LLAB-QUVVATLASH MUTAXASSISIDAN JAVOB:</b>\n"
        user_notification += "━━━━━━━━━━━━━━━━━━━━━━\n"
        user_notification += f"{reply_content}\n"
        user_notification += "━━━━━━━━━━━━━━━━━━━━━━\n"
        user_notification += "<i>Agar yana savollaringiz bo'lsa, '❓ Yordam' bo'limi orqali yozishingiz mumkin.</i>"
        
        send_message(target_user, user_notification)
        send_message(chat_id, f"✅ <b>Javobingiz foydalanuvchiga (ID: <code>{target_user}</code>) muvaffaqiyatli yetkazildi!</b>")
        return

    # 2. Foydalanuvchi adminga murojaat yubormoqda (User sending ticket to Admin)
    if user_state == "waiting_for_admin_ticket":
        USER_STATES.pop(chat_id, None)
        store = ctx.get("store") or {}
        store_name = store.get("store_name", "Do'kon")
        store_code = store.get("store_code", "Noma'lum")
        role_uz = "👑 Xo'jayin" if ctx.get("is_owner") else ("💼 Sotuvchi" if ctx.get("role") == "seller" else "👤 Xaridor")
        
        ticket_content = text or (voice and "🎤 [Ovozli murojaat yubordi]") or "📸 [Rasm yubordi]"
        
        admin_msg = "📩 <b>YANGI FOYDALANUVCHI MUROJAATI!</b>\n"
        admin_msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        admin_msg += f"👤 <b>Mijoz:</b> {sender_name} (@{username})\n"
        admin_msg += f"🆔 <b>Telegram ID:</b> <code>{chat_id}</code>\n"
        admin_msg += f"🏪 <b>Do'kon:</b> {store_name} (<code>{store_code}</code>)\n"
        admin_msg += f"👤 <b>Roli:</b> {role_uz}\n"
        admin_msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        admin_msg += f"📝 <b>Murojaat matni:</b>\n<i>«{ticket_content}»</i>"
        
        reply_kb = {"inline_keyboard": [[{"text": "↩️ Foydalanuvchiga javob berish", "callback_data": f"support_reply_{chat_id}"}]]}
        send_message(ADMIN_ID, admin_msg, reply_markup=reply_kb)
        
        user_confirm = "✅ <b>Murojaatingiz adminga muvaffaqiyatli yuborildi!</b>\n\n"
        user_confirm += "⏳ Tez orada mutaxassisimiz xabaringizni ko'rib chiqib, to'g'ridan-to'g'ri ushbu bot orqali javob yozadi."
        send_message(chat_id, user_confirm, reply_markup=get_main_keyboard(role=ctx.get("role", "owner")))
        return

    # 3. 24/7 AI Maslahatchiga savol berilmoqda (User asking question to AI Support)
    if user_state == "waiting_for_ai_support_question":
        USER_STATES.pop(chat_id, None)
        question_text = text
        if voice:
            send_message(chat_id, "🎧 <i>Savolingiz eshitilmoqda...</i>")
            audio_bytes = download_telegram_file(voice["file_id"])
            if audio_bytes:
                ai_parsed = parse_voice_or_text(audio_bytes=audio_bytes)
                question_text = ai_parsed.get("comment") or "Ovozli savol" if isinstance(ai_parsed, dict) else "Ovozli savol"
        
        store = ctx.get("store") or {}
        store_name = store.get("store_name", "Do'kon")
        
        send_message(chat_id, "🤖 <i>AI Maslahatchi javob tayyorlamoqda...</i>")
        ai_reply = answer_ai_support(question_text or "Yordam", role=ctx.get("role", "owner"), store_name=store_name)
        
        support_kb = {
            "inline_keyboard": [
                [{"text": "👨‍💻 Adminga xabar yuborish (Tirik mutaxassis)", "callback_data": "help_contact_admin"}],
                [{"text": "❓ Boshqa savol berish", "callback_data": "help_ask_ai"}]
            ]
        }
        send_message(chat_id, f"🤖 <b>AI Maslahatchi:</b>\n\n{ai_reply}", reply_markup=support_kb)
        return

    # Yordam & Support Markazi
    if text in ["❓ Yordam & Support AI", "❓ Yordam & Qo'llanma", "❓ Yordam", "/help", "/yordam", "/support"]:
        handle_help_menu(chat_id, ctx)
        return

    # State: Do'kon nomini o'zgartirish
    if user_state == "waiting_for_new_store_name" and text and not text.startswith("/"):
        USER_STATES.pop(chat_id, None)
        new_name = text.strip()
        if len(new_name) >= 2:
            update_store_name(chat_id, new_name)
            google_sheets_sync.sync_all_data_to_sheets()
            confirm = f"🎉 <b>Do'koningiz nomi muvaffaqiyatli «{new_name}» ga o'zgartirildi!</b>\n\n"
            confirm += "Endi barcha elektron cheklar, hisobotlar va xabarlarda ushbu nom aks etadi."
            send_message(chat_id, confirm, reply_markup=get_main_keyboard(role="owner"))
        else:
            send_message(chat_id, "⚠️ Do'kon nomi kamida 2 ta harfdan iborat bo'lishi kerak.")
        return

    # Do'kon sozlamalari menyusi
    if text in ["⚙️ Do'kon sozlamalari", "/settings", "/sozlamalar"]:
        handle_store_settings_view(chat_id, ctx)
        return

    # Zaxira nusxa yuklab olish (Backup)
    if text in ["/backup", "📦 Backup", "/db"]:
        db_path = os.path.join(os.path.dirname(__file__), "voice2deal.db")
        if os.path.exists(db_path):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            send_document(chat_id, db_path, caption=f"🗄 <b>Voice2Deal SQLite Database Backup</b>\n📅 <i>{now_str}</i>")
        else:
            send_message(chat_id, "⚠️ Baza fayli topilmadi.")
        return

    # Tizim salomatligi va Auto-Repair diagnostikasi (/health)
    if text in ["/health", "/status", "🛡 Salomatlik"]:
        diag = self_healing_watchdog.run_full_diagnostic()
        h_msg = "🛡 <b>VOICE2DEAL TIZIM SALOMATLIGI & SELF-HEALING</b>\n"
        h_msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        h_msg += f"📊 <b>Holati:</b> {diag['status']}\n"
        h_msg += f"⏱ <b>Uptime:</b> <code>{diag['uptime']}</code>\n"
        h_msg += f"🗄 <b>Baza (SQLite WAL):</b> <code>{diag['database']}</code>\n"
        h_msg += f"🤖 <b>AI Modellar:</b> <code>{diag['ai_engine']}</code>\n"
        h_msg += f"📡 <b>Telegram Bot API:</b> <code>{diag['telegram_api']}</code>\n"
        h_msg += f"🕒 <b>Oxirgi tekshiruv:</b> <i>{diag['checked_at']}</i>\n"
        h_msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        h_msg += "✅ <i>Avtomatik nosozliklarni bartaraf etish (Self-Healing Sentinel) faol!</i>"
        send_message(chat_id, h_msg)
        return

    # Start command handling
    
    # 0. Google Sheets Webhook URL qabul qilish
    if text and (text.startswith("https://script.google.com/macros/s/") or USER_STATES.get(chat_id) == "waiting_for_sheets_url"):
        if text.startswith("https://script.google.com/"):
            clean_url = text.strip()
            database.set_setting("google_sheets_webhook_url", clean_url)
            USER_STATES.pop(chat_id, None)
            admin_panel.add_admin_id(chat_id)
            send_message(chat_id, "⏳ <i>Google Sheets Webhook URL saqlandi! Birinchi sinxronizatsiya yuborilmoqda...</i>")
            sync_res = google_sheets_sync.sync_all_data_to_sheets(clean_url)
            if sync_res.get("success"):
                send_message(chat_id, "🎉 <b>Ajoyib! Google Sheets muvaffaqiyatli ulandi va barcha do'konlar jadvalga tushirildi!</b>")
            else:
                send_message(chat_id, f"⚠️ <i>URL saqlandi, lekin sinxronlashda javob: {sync_res.get('error')}</i>")
            
            # Show admin dashboard
            msg = admin_panel.get_admin_dashboard_message()
            kb = admin_panel.get_admin_dashboard_keyboard()
            send_message(chat_id, msg, reply_markup=kb)
            return

    # 0. Super Admin Panel Buyrug'i (/admin)
    if text in ["/admin", "/admin_panel", "👑 Admin"]:
        # Har qanday dastlabki murojaat qilgan asosiy userni adminga qo'shamiz
        admin_panel.add_admin_id(chat_id)
        msg = admin_panel.get_admin_dashboard_message()
        kb = admin_panel.get_admin_dashboard_keyboard()
        send_message(chat_id, msg, reply_markup=kb)
        return

    if text and text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1:
            code_param = parts[1].strip().upper()
            # Do'kon kodi orqali to'g'ridan-to'g'ri ulanish
            join_res = join_store_as_seller(chat_id, code_param, sender_name, username)
            if join_res.get("success"):
                welcome = f"🎉 <b>Tabriklaymiz, {sender_name}!</b>\n\n"
                s_name = join_res.get('store_name', '')
                s_code = join_res.get('store_code', '')
                welcome += f"Siz muvaffaqiyatli ravishda <b>\"{s_name}\"</b> (Kodi: <code>{s_code}</code>) do'koniga <b>Sotuvchi</b> sifatida biriktirildingiz!\n\n"
                welcome += "Endi istalgan savdo yoki qarz to'lovini ovozli yoki matn ko'rinishida yuborishingiz mumkin. Barcha savdolar do'kon hisobiga yoziladi."
                send_message(chat_id, welcome, reply_markup=get_main_keyboard(role="seller"))
                return
            else:
                send_message(chat_id, f"⚠️ {join_res.get('error', 'Ulanishda xatolik')}")

        # 1-Qadam: Til tanlash va Frictionless Onboarding
        lang_kb = {
            "inline_keyboard": [
                [{"text": "🇺🇿 O'zbekcha", "callback_data": "lang_uz"}, {"text": "🇷🇺 Русский", "callback_data": "lang_ru"}]
            ]
        }
        msg_lang = f"👋 <b>Assalomu alaykum, {sender_name}! / Здравствуйте!</b>\n\n"
        msg_lang += "«Voice2Deal — Ovozli Savdo & Qarz Daftari AI» tizimiga xush kelibsiz!\n"
        msg_lang += "Iltimos, muloqot tilini tanlang / Пожалуйста, выберите язык:"
        send_message(chat_id, msg_lang, reply_markup=lang_kb)
        return
            
        role = ctx["role"]
        store = ctx["store"]
        
        if role == "owner":
            start_msg = f"👋 <b>Assalomu alaykum, {sender_name}!</b>\n"
            start_msg += f"Siz <b>«Voice2Deal — Ovozli Savdo & Qarz Daftari AI»</b> tizimidasiz.\n\n"
            start_msg += f"🏪 <b>Do'kon:</b> {store.get('store_name', 'Mening do\'konim')}\n"
            start_msg += f"🆔 <b>Do'kon Kodi:</b> <code>{store.get('store_code', 'Noma\'lum')}</code>\n"
            start_msg += f"👤 <b>Rolingiz:</b> 👑 Do'kon Egasi (Xo'jayin)\n\n"
            start_msg += "🎙 <b>Qanday ishlatiladi?</b>\n"
            start_msg += "Shunchaki ovozli xabar (Voice) yuboring yoki yozing, masalan:\n"
            start_msg += "<i>• «Rustam akaga 5 ta moy filtr berdim 40 mingdan, 100 mingini berdi, qolgani dushanbaga qarz»</i>\n"
            start_msg += "<i>• «Akmal aka 300 ming qarzini to'ladi»</i>\n"
            start_msg += "<i>• «Do'kon arendasiga 500 ming to'ladim»</i>\n"
            send_message(chat_id, start_msg, reply_markup=get_main_keyboard(role="owner"))
        elif role == "seller":
            start_msg = f"👋 <b>Assalomu alaykum, {sender_name}!</b>\n"
            start_msg += f"🏪 <b>Do'kon:</b> {store.get('store_name', 'Mening do\'konim')}\n"
            start_msg += f"🆔 <b>Do'kon Kodi:</b> <code>{store.get('store_code', 'Noma\'lum')}</code>\n"
            start_msg += f"👤 <b>Rolingiz:</b> 💼 Sotuvchi\n\n"
            start_msg += "🎙 Istalgan savdo amalini ovoz yoki matn bilan yuboring, u avtomatik hisobga olinadi."
            send_message(chat_id, start_msg, reply_markup=get_main_keyboard(role="seller"))
        else:
            handle_client_debts_view(chat_id)
        return

    # Rolni almashtirish buyrug'i
    if text in ["🔄 Rolni o'zgartirish", "/rol", "/role"]:
        show_role_selection_screen(chat_id, sender_name)
        return

    # Do'kon Kodi kiritilganini avtomatik aniqlash (masalan: DK-8977, dk-8977, DK 8977, DK8977)
    if text and not text.startswith("/"):
        clean_code = re.sub(r'[\s_]', '-', text.strip().upper())
        if re.match(r'^DK-\d{3,}$', clean_code) or re.match(r'^DK\d{3,}$', clean_code):
            if not clean_code.startswith("DK-"):
                clean_code = "DK-" + clean_code[2:]
            
            store = get_store_by_code(clean_code)
            if not store:
                send_message(chat_id, f"⚠️ <b>'{clean_code}' kodli do'kon topilmadi!</b>\n\nIltimos, do'kon egasidan kodni aniqlab qaytadan kiriting.")
                return
                
            if store["telegram_id"] == chat_id:
                s_name = store.get('store_name', 'Mening do\'konim')
                msg = f"ℹ️ <b><code>{clean_code}</code> — bu sizning o'z do'koningiz («{s_name}»)!</b>\n\n"
                msg += "👑 Siz allaqachon bu do'konning <b>Xo'jayinisiz</b>.\n\n"
                msg += "👥 <b>Sotuvchi yoki ishchi qo'shish uchun:</b>\n"
                msg += f"Ushbu kodni (<code>{clean_code}</code>) yoki taklif havolasini sotuvchingizning Telegramiga yuboring:\n"
                msg += f"👉 <code>https://t.me/Ovozli_SavdoBOT?start={clean_code}</code>\n\n"
                msg += "Sotuvchi o'z Telegramidan ushbu havolani bosishi yoki botga kodni yuborishi bilan darhol sizning do'koningizga birikadi!"
                send_message(chat_id, msg)
                return
                
            join_res = join_store_as_seller(chat_id, clean_code, sender_name, username)
            if join_res.get("success"):
                USER_STATES.pop(chat_id, None)
                welcome = f"🎉 <b>Tabriklaymiz, {sender_name}!</b>\n\n"
                s_name = join_res.get('store_name', '')
                s_code = join_res.get('store_code', '')
                welcome += f"Siz muvaffaqiyatli ravishda <b>\"{s_name}\"</b> (Kodi: <code>{s_code}</code>) do'koniga <b>Sotuvchi</b> sifatida biriktirildingiz!\n\n"
                welcome += "Endi ushbu do'kon uchun istalgan savdo yoki qarz to'lovini ovozli yoki matn ko'rinishida yuborishingiz mumkin. Barcha savdolar do'kon hisobiga yoziladi."
                send_message(chat_id, welcome, reply_markup=get_main_keyboard(role="seller"))
                return
            else:
                send_message(chat_id, f"⚠️ {join_res.get('error')}")
                return


    # State: Do'kon kodini kutish (Sotuvchi uchun)
    if USER_STATES.get(chat_id) == "waiting_for_store_code" and text and not text.startswith("/"):
        code_input = text.strip().upper()
        join_res = join_store_as_seller(chat_id, code_input, sender_name, username)
        if join_res.get("success"):
            USER_STATES.pop(chat_id, None)
            welcome = f"🎉 <b>Tabriklaymiz, {sender_name}!</b>\n\n"
            s_name = join_res.get('store_name', '')
            s_code = join_res.get('store_code', '')
            welcome += f"Siz muvaffaqiyatli ravishda <b>\"{s_name}\"</b> (Kodi: <code>{s_code}</code>) do'koniga <b>Sotuvchi</b> sifatida biriktirildingiz!\n\n"
            welcome += "Endi istalgan savdo yoki qarz to'lovini ovozli yoki matn ko'rinishida yuborishingiz mumkin. Barcha savdolar do'kon hisobiga yoziladi."
            send_message(chat_id, welcome, reply_markup=get_main_keyboard(role="seller"))
            return
        else:
            send_message(chat_id, f"⚠️ {join_res.get('error')}\n\nIltimos, do'kon kodini tekshirib qaytadan yozing yoki /rol buyrug'i orqali bekor qiling.")
            return

    ctx = get_user_context(chat_id, sender_name, username)
    if not ctx["is_registered"]:
        show_role_selection_screen(chat_id, sender_name)
        return

    role = ctx["role"]
    is_owner = ctx["is_owner"]
    store = ctx.get("store")

    # 1. Tugma: "🎙 Savdo / Qarz kiritish" -> Yo'riqnoma berish (AI ga yubormaslik!)
    if text in ["🎙 Savdo / Qarz kiritish", "/savdo"]:
        guide_msg = "🎙 <b>Ovozli yoki matnli savdo kiritish</b>\n\n"
        guide_msg += "Istalgan savdo amalini ovozli xabar (Voice) qilib yuboring yoki quyidagicha yozing:\n\n"
        guide_msg += "<i>• «Rustam akaga 5 ta moy filtr berdim 40 mingdan, 100 mingini berdi, qolgani dushanbaga qarz»</i>\n"
        guide_msg += "<i>• «Akmal aka 200 ming qarzini olib kelib berdi»</i>\n"
        guide_msg += "<i>• «Do'kon arendasiga 500 ming xarajat qildim»</i>\n\n"
        guide_msg += "⚡️ <i>Bot barcha hisob-kitobni avtomatik amalga oshiradi!</i>"
        send_message(chat_id, guide_msg)
        return

    # Obuna & Tariflar
    if text in ["👑 Obuna & Tariflar", "/obuna", "/tariflar"]:
        handle_subscription_view(chat_id, ctx)
        return

    # Xodimlar
    if text in ["👥 Xodimlarim", "/xodimlar", "/xodim_qoshish"]:
        handle_staff_view(chat_id, ctx)
        return

    # Xaridor qarzlarini ko'rish
    if text in ["📋 Mening qarzlarim & Cheklarim", "/qarzim"]:
        handle_client_debts_view(chat_id)
        return

    # Sotuvchi do'kon ma'lumoti
    
    # Sotuvchi Smena Hisoboti
    if text in ["📊 Mening smenam (Kassa)", "/smena", "📊 Mening smenam"]:
        shift = get_seller_shift_summary(chat_id)
        if shift:
            st = shift["stats"]
            s_name = shift.get('store_name', 'Do\'kon')
            msg_shift = f"📊 <b>BUGUNGI SMENA HISOBOTI</b>\n"
            msg_shift += f"🏪 <b>Do'kon:</b> {s_name}\n"
            msg_shift += f"📅 <b>Sana:</b> {shift['date']}\n"
            msg_shift += "━━━━━━━━━━━━━━━━━━━━━━\n"
            msg_shift += f"🛒 <b>Siz qilgan savdolar:</b> {st['total_deals']} ta\n"
            msg_shift += f"💵 <b>Yig'ilgan naqd pul:</b> {format_number(st['total_cash'])} so'm\n"
            msg_shift += f"⏳ <b>Yangi berilgan nasiyalar:</b> {format_number(st['total_debt'])} so'm\n"
            msg_shift += f"📈 <b>Jami savdo aylanmasi:</b> {format_number(st['total_sales'])} so'm\n"
            msg_shift += "━━━━━━━━━━━━━━━━━━━━━━\n"
            msg_shift += "✅ <i>Kechqurun xo'jayinga hisob topshirish uchun qulay!</i>"
            send_message(chat_id, msg_shift)
        else:
            send_message(chat_id, "⚠️ Smena ma'lumotlari topilmadi.")
        return

    if text in ["ℹ️ Mening do'konim"]:
        store = ctx["store"]
        if store:
            send_message(chat_id, f"🏪 <b>Do'kon:</b> {store.get('store_name')}\n🆔 <b>Kodi:</b> <code>{store.get('store_code')}</code>\n👑 <b>Egasi:</b> {store.get('owner_name', 'Xo\'jayin')}\n💼 <b>Rolingiz:</b> Sotuvchi")
        else:
            send_message(chat_id, "Siz hali hech qaysi do'konga biriktirilmagansiz. /rol buyrug'ini bosing.")
        return

    
    # 1. Sklad va Tovar qoldiqlari (Xo'jayin va Sotuvchi uchun)
    if text in ["📦 Sklad & Tovar qoldiqlari", "📦 Ombor & Sklad qoldiqlari", "/sklad", "/ombor"]:
        if not store:
            send_message(chat_id, "🔒 <i>Siz hech qaysi do'konga biriktirilmagansiz.</i>")
            return
            
        inv_list = get_inventory_list(chat_id)
        msg_text = "📦 <b>OMBOR VA TOVAR QOLDIQLARI (SKLAD)</b>\n"
        msg_text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        
        if inv_list:
            for idx, item in enumerate(inv_list, 1):
                name = item["name"]
                qty = int(item["quantity"])
                unit = item.get("unit", "dona")
                cost = format_number(item.get("cost_price", 0))
                sell = format_number(item.get("selling_price", 0))
                
                status_icon = "🟢" if qty > item.get("min_alert_qty", 5) else "🔴 (Kam qoldi!)"
                msg_text += f"{idx}. <b>{name}</b> — <b>{qty} {unit}</b> {status_icon}\n"
                if float(item.get("cost_price", 0)) > 0 or float(item.get("selling_price", 0)) > 0:
                    msg_text += f"   • Tan narxi: {cost} so'm | Sotilishi: {sell} so'm\n"
        else:
            msg_text += "<i>Hozircha omborda tovarlar mavjud emas.</i>\n\n"
            
        msg_text += "\n🎙 <b>Omborga tovar kiritish usuli:</b>\n"
        msg_text += "Shunchaki ovoz yuboring yoki yozing:\n"
        msg_text += "<i>• «Skladga 50 dona Coca-Cola 1.5L 12000 so'mdan qo'sh»</i>\n"
        msg_text += "<i>• «Omborga 100 ta moy filtr kirdi»</i>\n"
        msg_text += "<i>• «30 ta Snickers 8000 so'mdan kiritdim»</i>"
        
        inline_kb = {
            "inline_keyboard": [
                [{"text": "🔄 Ro'yxatni yangilash", "callback_data": "refresh_inventory"}],
                [{"text": "🎙 Tovar qo'shish bo'yicha yo'riqnoma", "callback_data": "guide_inventory"}]
            ]
        }
        send_message(chat_id, msg_text, reply_markup=inline_kb)
        return

    # 2. AI Biznes Maslahatchi & Tahlil (Faqat Xo'jayin uchun)
    if text in ["🧠 AI Biznes Maslahatchi", "/tahlil", "/maslahat", "/analitika"]:
        if not is_owner:
            send_message(chat_id, "🔒 <i>Biznes tahlilini ko'rish faqat do'kon egasiga ruxsat etilgan.</i>")
            return
            
        send_message(chat_id, "🧠 <i>Sun'iy intellekt do'koningiz savdosi, xarajatlari va qarzlarini tahlil qilmoqda...</i>")
        analytics_data = get_business_analytics_data(chat_id)
        if analytics_data:
            report_text = generate_ai_business_report(analytics_data)
            send_message(chat_id, report_text)
        else:
            send_message(chat_id, "⚠️ Tahlil uchun ma'lumotlar yetarli emas.")
        return

    # Kassa hisoboti (Faqat Xo'jayin uchun)
    if text in ["📊 Kassa hisoboti", "/kassa", "/hisobot"]:
        if not is_owner:
            send_message(chat_id, "🔒 <i>Kassa hisobotini ko'rish huquqi faqat do'kon egasiga berilgan.</i>")
            return
            
        kassa = get_kassa_summary(chat_id)
        today = kassa["today"]
        msg_text = "📊 <b>KASSA VA TUSHUM HISOBOTI</b>\n"
        msg_text += f"📅 <i>Sana: {kassa['date']}</i>\n"
        msg_text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg_text += f"🛒 <b>Bugungi savdolar soni:</b> {today['total_deals']} ta\n"
        msg_text += f"💵 <b>Bugungi naqd tushum:</b> {format_number(today['total_cash'])} so'm\n"
        msg_text += f"⏳ <b>Bugungi yangi nasiyalar:</b> {format_number(today['total_debt'])} so'm\n"
        msg_text += f"📈 <b>Bugungi jami aylanma:</b> {format_number(today['total_sales'])} so'm\n"
        msg_text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg_text += f"🔴 <b>JAMI QARZLAR (NASIYA):</b> <b>{format_number(kassa['overall_debt'])} so'm</b>\n"
        msg_text += f"👥 <b>Qarzdorlar soni:</b> {kassa['debtor_count']} kishi\n"
        send_message(chat_id, msg_text)
        return

    # Qarzdorlar daftari & Mijoz qarzini tekshirish (Xo'jayin va Sotuvchi uchun)
    if text in ["⏳ Qarzdorlar daftari", "🔍 Mijoz qarzini tekshirish", "/qarzlar", "/nasiya"]:
        if not store:
            send_message(chat_id, "🔒 <i>Siz hech qaysi do'konga biriktirilmagansiz.</i>")
            return
            
        debtors = get_debtors_list(chat_id)
        if not debtors:
            send_message(chat_id, "🎉 <b>Hozircha hech kimda qarz yo'q!</b> Barcha hisoblar yopilgan.")
            return

        msg_text = "⏳ <b>QARZDORLAR (NASIYA) DAFTARI</b>\n"
        msg_text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        
        inline_buttons = []
        for idx, d in enumerate(debtors, 1):
            name = d.get("name", "Noma'lum")
            debt = format_number(d.get("total_debt", 0))
            last_date = d.get("last_deal_date", "")[:10]
            last_rem = d.get("last_reminder_at")
            rem_tag = " (🔔 Eslatma yuborilgan)" if last_rem else ""
            msg_text += f"{idx}. 👤 <b>{name}</b> — <b>{debt} so'm</b>\n"
            msg_text += f"   📅 Oxirgi savdo: {last_date}{rem_tag}\n"
            
            if idx <= 5:
                inline_buttons.append([{"text": f"🔔 {name} ga eslatma matni", "callback_data": f"remind_{d['id']}"}])

        total_debt_sum = sum(float(d.get("total_debt", 0)) for d in debtors)
        msg_text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg_text += f"🔴 <b>JAMI YOPILMAGAN NASIYALAR:</b> <b>{format_number(total_debt_sum)} so'm</b>\n"
        msg_text += "💡 <i>VIP AI eslatuvchi orqali mijozlarga avtomatik xushmuomala xabarlar yuborib qarzlarni 2x tezroq undirishingiz mumkin!</i>\n\n"
        msg_text += "<i>Mijozga xushmuomala eslatma matnini olish uchun pastdagi tugmani bosing:</i>"
        
        markup = {"inline_keyboard": inline_buttons} if inline_buttons else None
        send_message(chat_id, msg_text, reply_markup=markup)
        return

    # Excel hisobot (Faqat Xo'jayin uchun)
    if text in ["📥 Excel hisobot", "/export", "/excel"]:
        if not is_owner:
            send_message(chat_id, "🔒 <i>Hisobotlarni yuklab olish faqat do'kon egasiga ruxsat etilgan.</i>")
            return
            
        send_message(chat_id, "⏳ <i>Excel hisobot tayyorlanmoqda...</i>")
        csv_file = export_kassa_excel(chat_id)
        if csv_file and os.path.exists(csv_file):
            send_document(chat_id, csv_file, caption="📊 <b>Kassa va Nasiya hisoboti (Excel/CSV)</b>")
        else:
            send_message(chat_id, "⚠️ Hisobot yaratishda xatolik yuz berdi.")
        return

    # Agar xaridor bo'lsa va savdo kiritmoqchi bo'lsa
    if role == "client" and (voice or (text and not text.startswith("/"))):
        send_message(chat_id, "ℹ️ <i>Siz xaridor rejimidasiz. Savdo kiritish uchun /rol buyrug'i orqali Do'kon Egasi yoki Sotuvchi rejimiga o'ting.</i>")
        return

    # Ovozli yoki matnli savdo kiritish
    audio_bytes = None
    if voice:
        send_message(chat_id, "🎧 <i>Ovoz eshitilmoqda va tahlil qilinmoqda...</i>")
        file_id = voice["file_id"]
        audio_bytes = download_telegram_file(file_id)
        if not audio_bytes:
            send_message(chat_id, "⚠️ Ovozli xabarni yuklab olishda xatolik yuz berdi.")
            return
        parsed_data = parse_voice_or_text(audio_bytes=audio_bytes)
    elif text and not text.startswith("/"):
        send_message(chat_id, "⚡️ <i>Savdo ma'lumoti tahlil qilinmoqda...</i>")
        parsed_data = parse_voice_or_text(text=text)
    else:
        return

    if not parsed_data:
        send_message(chat_id, "⚠️ Xabarni tushunib bo'lmadi. Iltimos, savdo, qarz yoki to'lov amalini aniqroq ayting yoki yozing.\nMasalan: <i>«Akmal akaga 2 ta moy filtr berdim 50 mingdan»</i>")
        return

    # Batch (ko'p amallar) yoki Yagona amalni ro'yxatga keltiramiz:
    if isinstance(parsed_data, list):
        operations_list = parsed_data
    elif isinstance(parsed_data, dict):
        if "operations" in parsed_data and isinstance(parsed_data["operations"], list):
            operations_list = parsed_data["operations"]
        else:
            operations_list = [parsed_data]
    else:
        operations_list = []

    store = ctx["store"]
    store_id = store["id"] if store else None

    # Agar 1 ta dona amal bo'lib, ma'lumot yetarli bo'lmasa:
    if len(operations_list) == 1:
        op_data = operations_list[0]
        op_type = op_data.get("operation_type")
        items = op_data.get("items") or []
        if op_type == "other" and not items and not op_data.get("total_amount") and not op_data.get("paid_amount"):
            send_message(chat_id, "⚠️ Xabarni tushunib bo'lmadi. Iltimos, tovar nomi, narxi yoki miqdorini ayting.\nMasalan: <i>«Skladga 50 ta kola 12 mingdan qo'sh»</i>")
            return

    # Audio Confirmation Loop: Foydalanuvchiga avval tasdiqlash kartochkasini chiqaramiz!
    PENDING_CONFIRMATIONS[chat_id] = {
        "operations": operations_list,
        "raw_text": text or (voice and "Ovozli savdo") or "Savdo amali",
        "store_id": store_id,
        "timestamp": time.time()
    }
    if USER_STATES.get(chat_id) == "waiting_for_trade_edit":
        USER_STATES.pop(chat_id, None)

    card_text, kb = format_trade_confirmation_card(operations_list)
    send_message(chat_id, card_text, reply_markup=kb)
    return

def execute_confirmed_transactions(chat_id, pending_data):
    """
    Savdogar tasdiqlaganidan so'ng operatsiyalarni bazaga saqlaydi va natijaviy cheklarni chiqaradi.
    """
    if not pending_data:
        send_message(chat_id, "⚠️ Tasdiqlash muddati tugagan yoki amallar topilmadi. Qaytadan urinib ko'ring.")
        return

    operations_list = pending_data.get("operations", [])
    store_id = pending_data.get("store_id")
    raw_text = pending_data.get("raw_text", "Voice Message")

    if not operations_list:
        send_message(chat_id, "⚠️ Saqlash uchun amallar topilmadi.")
        return

    # Agar 1 ta dona amal bo'lsa:
    if len(operations_list) == 1:
        op_data = operations_list[0]
        op_type = op_data.get("operation_type")
        items = op_data.get("items") or []

        # Sklad kirim bo'lsa:
        if op_type == "inventory_in" and store_id:
            if not items:
                items = [{"name": "Tovar", "qty": 1, "price": op_data.get("total_amount", 0)}]
            added_names = []
            for it in items:
                name = it.get("name") or "Tovar"
                qty = float(it.get("qty") or 1)
                cost = float(it.get("price") or 0)
                res_inv = add_or_update_inventory(store_id, name, qty, cost_price=cost)
                added_names.append(f"• <b>{name}</b>: +{int(qty)} dona (Omborda jami: <b>{int(res_inv['new_quantity'])} dona</b>)")
                
            msg_inv = "📦 <b>SKLADGA TOVAR QABUL QILINDI!</b>\n"
            msg_inv += "━━━━━━━━━━━━━━━━━━━━━━\n"
            msg_inv += "\n".join(added_names) + "\n\n"
            msg_inv += "✅ <i>Ombor qoldig'iga muvaffaqiyatli saqlandi!</i>\n"
            msg_inv += "💡 <i>Har bir sotuvda ushbu tovar avtomatik ravishda ombordan kamayib boradi.</i>"
            inline_kb = {"inline_keyboard": [[{"text": "📦 Ombor qoldiqlarini ko'rish", "callback_data": "refresh_inventory"}]]}
            send_message(chat_id, msg_inv, reply_markup=inline_kb)
            return

        # Savdo / Qarz / To'lov saqlash:
        res_tx = record_transaction(chat_id, op_data, raw_text=raw_text)
        if res_tx:
            op_data["client_name"] = res_tx.get("client_name", op_data.get("client_name"))
            op_data["paid_amount"] = res_tx.get("paid", op_data.get("paid_amount"))
            op_data["total_amount"] = res_tx.get("total", op_data.get("total_amount"))
            op_data["debt_amount"] = res_tx.get("debt", op_data.get("debt_amount"))
            
            receipt_text = format_receipt(op_data)
            if op_type == "debt_payment":
                new_debt_left = res_tx.get("new_debt", 0)
                if new_debt_left <= 0:
                    receipt_text += "\n🎉 <b>Mijozning barcha qarzi to'liq yopildi!</b>"
                else:
                    receipt_text += f"\n⏳ <b>Mijozning qolgan qarzi: {format_number(new_debt_left)} so'm</b>"

            if op_type == "sale" and store_id:
                stock_alerts = decrement_inventory_on_sale(store_id, items)
                if stock_alerts:
                    receipt_text += "\n\n" + "\n".join(stock_alerts)
            tx_id = res_tx.get("tx_id", 1)
            inline_receipt_kb = {
                "inline_keyboard": [
                    [
                        {"text": "🧾 Termal Chek (58/80mm)", "callback_data": f"receipt_{tx_id}"}
                    ]
                ]
            }
            send_message(chat_id, receipt_text, reply_markup=inline_receipt_kb)
        else:
            send_message(chat_id, "⚠️ Savdoni saqlashda xatolik yuz berdi. Iltimos, /start bosing.")
        return

    # Agar 2 yoki undan ortiq amallar birdaniga aytilgan bo'lsa (Batch Processing):
    summary_lines = []
    receipt_buttons = []
    
    for idx, op_data in enumerate(operations_list, 1):
        op_type = op_data.get("operation_type")
        items = op_data.get("items") or []
        client = op_data.get("client_name") or "Noma'lum"
        total_p = op_data.get("total_amount", 0)
        paid_p = op_data.get("paid_amount", 0)
        debt_p = op_data.get("debt_amount", 0)

        # Sklad kirim:
        if op_type == "inventory_in" and store_id:
            for it in items:
                name = it.get("name") or "Tovar"
                qty = float(it.get("qty") or 1)
                cost = float(it.get("price") or 0)
                res_inv = add_or_update_inventory(store_id, name, qty, cost_price=cost)
                summary_lines.append(f"{idx}. 📦 <b>{name}</b> (+{int(qty)} dona skladga qo'shildi)")
            continue

        # Savdo / Qarz to'lash:
        res_tx = record_transaction(chat_id, op_data, raw_text=raw_text)
        if res_tx:
            if op_type == "sale" and store_id:
                decrement_inventory_on_sale(store_id, items)
            tx_id = res_tx.get("tx_id")
            actual_client = res_tx.get("client_name", client)
            actual_paid = res_tx.get("paid", paid_p)
            actual_debt = res_tx.get("debt", debt_p)
            actual_total = res_tx.get("total", total_p)
            new_debt_left = res_tx.get("new_debt", 0)

            if tx_id:
                receipt_buttons.append([{"text": f"🧾 {actual_client} cheki", "callback_data": f"receipt_{tx_id}"}])
                
            if op_type == "debt_payment":
                had_prev = res_tx.get("had_previous_debt", False)
                if had_prev:
                    if new_debt_left <= 0:
                        rem_info = " (Oldingi qarzi to'liq yopildi 🎉)"
                    else:
                        rem_info = f" (Qoldiq qarz: {format_number(new_debt_left)} so'm)"
                else:
                    rem_info = " (Kassaga to'lov sifatida qabul qilindi 💵)"
                summary_lines.append(f"{idx}. 💵 <b>{actual_client}:</b> {format_number(actual_paid)} so'm to'ladi ✅{rem_info}")
            elif op_type in ["debt_give", "sale"]:
                if actual_debt > 0:
                    summary_lines.append(f"{idx}. ⏳ <b>{actual_client}:</b> {format_number(actual_debt)} so'm qarz (nasiya) yozildi")
                else:
                    summary_lines.append(f"{idx}. 🛒 <b>{actual_client}:</b> {format_number(actual_total)} so'm naqd savdo")
            elif op_type == "expense":
                summary_lines.append(f"{idx}. 📉 <b>Xarajat:</b> {format_number(actual_total)} so'm chiqim qilindi")
            else:
                summary_lines.append(f"{idx}. ✅ <b>{actual_client}:</b> Amal muvaffaqiyatli saqlandi")

    batch_msg = f"🎉 <b>BARCHA AMALLAR QABUL QILINDI ({len(operations_list)} ta):</b>\n"
    batch_msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    batch_msg += "\n".join(summary_lines) + "\n"
    batch_msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    batch_msg += "✅ <i>Kassa va qarz daftari avtomatik yangilandi!</i>"
    
    markup = {"inline_keyboard": receipt_buttons[:4]} if receipt_buttons else None
    send_message(chat_id, batch_msg, reply_markup=markup)


def run_auto_backup_daemon():
    def backup_worker():
        ADMIN_ID = 1320855100
        while True:
            try:
                time.sleep(12 * 3600)
                db_path = os.path.join(os.path.dirname(__file__), "voice2deal.db")
                if os.path.exists(db_path):
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    caption = f"🗄 <b>VOICE2DEAL AVTOMATIK ZAXIRA NUSXA (BACKUP)</b>\n📅 <i>Sana: {now_str}</i>\n\nBarcha do'konlar va hisob-kitoblar xavfsiz saqlangan."
                    send_document(ADMIN_ID, db_path, caption=caption)
            except Exception as e:
                print(f"Auto-backup Error: {e}", flush=True)
                time.sleep(3600)
                
    t = threading.Thread(target=backup_worker, daemon=True)
    t.start()

def main():
    acquire_single_instance_lock()
    run_auto_backup_daemon()
    self_healing_watchdog.start_sentinel_watchdog()
    print("🚀 Voice2Deal Telegram Bot (v3 Role & Code Architecture) ishga tushdi...", flush=True)
    
    commands = [
        {"command": "kassa", "description": "Bugungi kassa va tushum"},
        {"command": "qarzlar", "description": "Qarzdorlar daftari va eslatmalar"},
        {"command": "xodimlar", "description": "Sotuvchilarni boshqarish"},
        {"command": "obuna", "description": "Tariflar va to'lov"},
        {"command": "rol", "description": "Rolni o'zgartirish (Egasi / Sotuvchi / Mijoz)"},
        {"command": "export", "description": "Excel hisobot yuklab olish"},
        {"command": "health", "description": "Tizim salomatligi & Self-Healing"},
        {"command": "start", "description": "Botni yangilash / qayta boshlash"}
    ]
    res_cmd = send_telegram_request("setMyCommands", {"commands": commands})
    print(f"setMyCommands: {res_cmd}", flush=True)

    last_update_id = 0
    while True:
        try:
            url = f"{TELEGRAM_API}/getUpdates?offset={last_update_id + 1}&timeout=30"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    for update in data.get("result", []):
                        last_update_id = max(last_update_id, update["update_id"])
                        try:
                            handle_update(update)
                        except Exception as e:
                            import traceback
                            print(f"Update handling error: {e}", flush=True)
                            traceback.print_exc()
        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    main()
