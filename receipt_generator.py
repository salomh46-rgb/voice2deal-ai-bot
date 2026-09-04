import os
from datetime import datetime

def format_number(n):
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return str(n)

def generate_thermal_receipt_text(tx_data, store_data):
    """
    Do'konlar va xaridorlar uchun professional 58mm/80mm chek matnini generatsiya qiladi.
    """
    store_name = store_data.get("store_name", "Mening Do\'konim")
    store_code = store_data.get("store_code", "DK-0000")
    
    tx_id = tx_data.get("tx_id") or "1"
    client_name = tx_data.get("client_name") or "Noma'lum Xaridor"
    total_amount = format_number(tx_data.get("total_amount", 0))
    paid_amount = format_number(tx_data.get("paid_amount", 0))
    debt_amount = format_number(tx_data.get("debt_amount", 0))
    due_date = tx_data.get("due_date")
    items = tx_data.get("items") or []
    
    date_str = datetime.now().strftime("%d.%m.%Y  %H:%M")
    
    receipt = []
    receipt.append("╔════════════════════════════════════════╗")
    receipt.append(f"║ {store_name.center(38)} ║")
    receipt.append(f"║ {'Do\'kon Kodi: ' + store_code:<38} ║")
    receipt.append(f"║ {'Chek №: #' + str(tx_id):<20} {date_str:>17} ║")
    receipt.append("╠════════════════════════════════════════╣")
    receipt.append(f"║ Mijoz: {client_name:<31} ║")
    receipt.append("╟────────────────────────────────────────╢")
    receipt.append("║ Nomi            Soni    Narxi    Jami  ║")
    receipt.append("╟────────────────────────────────────────╢")
    
    if items:
        for idx, it in enumerate(items, 1):
            name = str(it.get("name", "Mahsulot"))[:14]
            qty = str(it.get("qty", 1))[:4]
            price = format_number(it.get("price", 0))[:8]
            tot = format_number(it.get("total", 0))[:8]
            line = f"║ {name:<14} {qty:<6} {price:<8} {tot:>6} ║"
            receipt.append(line)
    else:
        receipt.append(f"║ {'Savdo amali':<26} {total_amount:>11} ║")
        
    receipt.append("╠════════════════════════════════════════╣")
    receipt.append(f"║ JAMI SUMMA:{total_amount:>27} so'm ║")
    receipt.append(f"║ NAQD TO'LANDI:{paid_amount:>24} so'm ║")
    if float(tx_data.get("debt_amount", 0)) > 0:
        receipt.append(f"║ ⏳ NASIYA (QARZ):{debt_amount:>20} so'm ║")
        if due_date:
            receipt.append(f"║ Qaytarish muddati: {due_date:<19} ║")
    receipt.append("╠════════════════════════════════════════╣")
    receipt.append("║     XARIDINGIZ UCHUN TASHAKKUR!        ║")
    receipt.append("║  [QR: https://t.me/Ovozli_SavdoBOT]    ║")
    receipt.append("╚════════════════════════════════════════╝")
    
    return "\n".join(receipt)
