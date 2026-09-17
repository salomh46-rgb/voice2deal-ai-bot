import pytest
import urllib.parse
import os
import sys

# Loyiha ildiz papkasini import uchun qo'shamiz
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from receipt_generator import (
    format_number,
    generate_thermal_receipt_text,
    generate_thermal_receipt_html
)
from ai_engine import (
    generate_gentle_reminder,
    generate_telegram_share_link
)
from bot import format_trade_confirmation_card

# ============================================================================
# 1. Ovozli savdo va parsing testlari (Voice Transaction Parser)
# ============================================================================

def parse_voice_transaction(text: str):
    lower = text.lower()
    amount = 0
    words = lower.split()
    for w in words:
        cleaned = "".join(filter(str.isdigit, w))
        if cleaned:
            amount = int(cleaned)
            break
    # Nasiya / Qarz berish va Qarz to'lash kalit so'zlari
    debt_give_keywords = ["nasiya", "nasiyaga", "qarzga", "berdim", "qarz yoz"]
    payment_keywords = ["to'ladi", "qarzini berdi", "pulini berdi", "yopdi", "qaytardi"]
    
    is_payment = any(k in lower for k in payment_keywords)
    is_debt = any(k in lower for k in debt_give_keywords) and not is_payment

    op_type = "debt_payment" if is_payment else ("debt_give" if is_debt else "sale")
    return {
        "text": text,
        "amount": amount,
        "is_debt": is_debt,
        "operation_type": op_type,
        "currency": "UZS"
    }


def test_voice_parser_debt_recognition():
    result = parse_voice_transaction("Eshmat akaga 500000 som nasiyaga berdim")
    assert result["amount"] == 500000
    assert result["is_debt"] is True
    assert result["operation_type"] == "debt_give"

def test_voice_parser_cash_recognition():
    result = parse_voice_transaction("Bugun kassaga 1200000 som naqd tushdi")
    assert result["amount"] == 1200000
    assert result["is_debt"] is False
    assert result["operation_type"] == "sale"

def test_voice_parser_payment_recognition():
    result = parse_voice_transaction("Toshmat aka 300000 som qarzini to'ladi")
    assert result["amount"] == 300000
    assert result["operation_type"] == "debt_payment"

# ============================================================================
# 2. Audio Confirmation Loop Testlari (Ovozli tasdiqlash dialoqi)
# ============================================================================

def test_audio_confirmation_card_single_nasiya():
    operations = [{
        "operation_type": "debt_give",
        "client_name": "Eshmat aka",
        "debt_amount": 500000,
        "total_amount": 500000,
        "paid_amount": 0
    }]
    text, markup = format_trade_confirmation_card(operations)
    
    # Matnda mijoz ismi va summa bo'lishi shart
    assert "Eshmat aka" in text
    assert "500 000" in text
    assert "Nasiya" in text
    assert "To'g'rimi?" in text
    
    # Tugmalar to'liqligi tekshiruvi: [✅ Tasdiqlash] va [❌ Tahrirlash]
    buttons = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
    callbacks = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
    
    assert any("Tasdiqlash" in b for b in buttons)
    assert any("Tahrirlash" in b for b in buttons)
    assert "confirm_trade_yes" in callbacks
    assert "confirm_trade_edit" in callbacks
    assert "confirm_trade_cancel" in callbacks

def test_audio_confirmation_card_single_debt_payment():
    operations = [{
        "operation_type": "debt_payment",
        "client_name": "Eshmat aka",
        "paid_amount": 500000,
        "total_amount": 500000,
        "debt_amount": 0
    }]
    text, markup = format_trade_confirmation_card(operations)
    assert "Eshmat aka" in text
    assert "500 000" in text
    assert "Qarz to'lovi" in text
    assert "To'g'rimi?" in text

def test_audio_confirmation_card_single_cash_sale():
    operations = [{
        "operation_type": "sale",
        "client_name": "Olimjon",
        "paid_amount": 150000,
        "total_amount": 150000,
        "debt_amount": 0
    }]
    text, markup = format_trade_confirmation_card(operations)
    assert "Olimjon" in text
    assert "150 000" in text
    assert "Naqd savdo" in text

def test_audio_confirmation_card_inventory_in():
    operations = [{
        "operation_type": "inventory_in",
        "items": [{"name": "Kola 1.5L", "qty": 50, "price": 12000}],
        "total_amount": 600000
    }]
    text, markup = format_trade_confirmation_card(operations)
    assert "Ombor kirimi" in text
    assert "Kola 1.5L" in text
    assert "600 000" in text

def test_audio_confirmation_card_batch_multiple_clients():
    operations = [
        {"operation_type": "debt_give", "client_name": "Eshmat aka", "debt_amount": 500000},
        {"operation_type": "debt_payment", "client_name": "Toshmat aka", "paid_amount": 200000}
    ]
    text, markup = format_trade_confirmation_card(operations)
    assert "Savdo amallari (2 ta)" in text
    assert "Eshmat aka" in text
    assert "500 000" in text
    assert "Toshmat aka" in text
    assert "200 000" in text

def test_audio_confirmation_card_empty():
    text, markup = format_trade_confirmation_card([])
    assert "topilmadi" in text.lower()
    assert markup is None

# ============================================================================
# 3. Bozor Printerlari uchun Termal Kvitansiya Testlari (58mm / 80mm)
# ============================================================================

def test_thermal_receipt_text_58mm():
    tx_data = {
        "tx_id": 105,
        "client_name": "Eshmat aka",
        "total_amount": 500000,
        "paid_amount": 0,
        "debt_amount": 500000,
        "due_date": "15-sentabr",
        "operation_type": "debt_give"
    }
    store_data = {
        "store_name": "Bozor Oziq-Ovqat",
        "store_code": "DK-7788"
    }
    receipt = generate_thermal_receipt_text(tx_data, store_data, paper_width="58mm")
    
    assert "Bozor Oziq-Ovqat" in receipt
    assert "DK-7788" in receipt
    assert "Eshmat aka" in receipt
    assert "500 000" in receipt
    assert "NASIYA (QARZ)" in receipt
    assert "15-sentabr" in receipt
    # 58mm printer uchun qatorlar kengligi 32 belgidan oshmasligi kerak
    lines = receipt.split("\n")
    for line in lines:
        assert len(line) <= 34, f"Qator uzunligi 58mm chegarasidan oshdi: {line}"

def test_thermal_receipt_text_80mm_with_items():
    tx_data = {
        "tx_id": 204,
        "client_name": "Rustam aka",
        "total_amount": 350000,
        "paid_amount": 350000,
        "debt_amount": 0,
        "items": [
            {"name": "Moy filtr", "qty": 2, "price": 75000, "total": 150000},
            {"name": "Motor moyi 4L", "qty": 1, "price": 200000, "total": 200000}
        ]
    }
    receipt = generate_thermal_receipt_text(tx_data, {}, paper_width="80mm")
    assert "Moy filtr" in receipt
    assert "Motor moyi 4L" in receipt
    assert "350 000" in receipt
    assert "TO'LANDI" in receipt

def test_thermal_receipt_html_generation():
    tx_data = {
        "tx_id": 305,
        "client_name": "Akmal Do'konchi",
        "total_amount": 1200000,
        "paid_amount": 200000,
        "debt_amount": 1000000,
        "due_date": "20-sentabr"
    }
    html_58 = generate_thermal_receipt_html(tx_data, paper_width="58mm")
    assert "@page" in html_58
    assert "58mm" in html_58
    assert "@media print" in html_58
    assert "Akmal Do'konchi" in html_58
    assert "1 000 000" in html_58
    assert "20-sentabr" in html_58

    html_80 = generate_thermal_receipt_html(tx_data, paper_width="80mm")
    assert "80mm" in html_80

# ============================================================================
# 4. Qarzdorlarga Muloyim Telegram Eslatma Generator Testlari
# ============================================================================

def test_gentle_reminder_generator_politeness_and_structure():
    client_name = "Eshmat aka"
    debt_amount = 500000
    store_name = "Do'konimiz"
    due_date = "15-sentabr"

    reminder = generate_gentle_reminder(
        client_name=client_name,
        debt_amount=debt_amount,
        store_name=store_name,
        due_date=due_date
    )

    # Talab qilingan muloyim boshlanish va qismlar
    assert "Assalomu alaykum, hurmatli Eshmat aka!" in reminder
    assert "500 000" in reminder
    assert "qarz muddati yetib keldi" in reminder
    assert "Click" in reminder or "Payme" in reminder
    assert "tashakkur" in reminder.lower() or "rahmat" in reminder.lower()

def test_gentle_reminder_telegram_share_link():
    text = "Assalomu alaykum, hurmatli Eshmat aka! Do'konimizdan 500 000 so'm qarz muddati yetib keldi."
    share_url = generate_telegram_share_link(text)
    
    assert share_url.startswith("https://t.me/share/url?url=")
    encoded_part = share_url.replace("https://t.me/share/url?url=", "")
    decoded_part = urllib.parse.unquote(encoded_part)
    assert decoded_part == text

# ============================================================================
# 5. Moliyaviy Aniqlik va Tiyin Konvertatsiyasi Testlari (Fintech Integrity)
# ============================================================================

def test_tiyin_conversion_safety():
    to_tiyin = lambda x: int(round(float(x) * 100))
    from_tiyin = lambda x: int(round(float(x) / 100))
    
    assert to_tiyin(50000) == 5000000
    assert from_tiyin(5000000) == 50000
    assert to_tiyin(0.5) == 50
    assert from_tiyin(50) == 0

def test_format_number_precision():
    assert format_number(500000) == "500 000"
    assert format_number("1250000") == "1 250 000"
    assert format_number(0) == "0"
    assert format_number(7500.8) == "7 501"

