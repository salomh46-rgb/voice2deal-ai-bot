import sqlite3
import os
import io
import tempfile
from datetime import datetime

def export_kassa_excel(telegram_id):
    """
    Do'konning barcha savdolari va qarzdorlar ro'yxatini toza Excel (.csv) qilib saqlaydi va fayl yo'lini qaytaradi.
    """
    from database import get_db, get_user_context
    ctx = get_user_context(telegram_id)
    store = ctx["store"]
    store_id = store["id"]
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
    SELECT created_at, client_name, type, total_amount, paid_amount, debt_amount, due_date, comment
    FROM transactions 
    WHERE store_id = ? 
    ORDER BY created_at DESC
    """, (store_id,))
    tx_rows = [dict(r) for r in c.fetchall()]

    c.execute("""
    SELECT name, phone, total_debt, last_deal_date 
    FROM clients 
    WHERE store_id = ? AND total_debt > 0 
    ORDER BY total_debt DESC
    """, (store_id,))
    debtor_rows = [dict(r) for r in c.fetchall()]
    conn.close()

    output = io.StringIO()
    output.write("=====================================================\n")
    store_title = store.get('store_name', 'Mening Do\'konim')
    output.write(f"DO'KON HISOBOTI: {store_title}\n")
    output.write(f"Sana: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write("=====================================================\n\n")

    output.write("--- 1. QARZDORLAR (NASIYA DAFTARI) ---\n")
    output.write("Mijoz Ismi;Telefon;Qarz Summasi (so'm);Oxirgi Savdo Sanasi\n")
    for r in debtor_rows:
        ph = r.get('phone') or 'Noma\'lum'
        output.write(f"{r['name']};{ph};{int(r['total_debt']):,};{r['last_deal_date']}\n")

    output.write("\n--- 2. BARCHA SAVDO VA TRANZAKSIYALAR ---\n")
    output.write("Sana;Mijoz;Amal Turi;Jami Summa;Naqd To'landi;Nasiya Qarz;Qaytarish Muddati;Izoh\n")
    for t in tx_rows:
        output.write(f"{t['created_at']};{t['client_name']};{t['type']};{int(t['total_amount']):,};{int(t['paid_amount']):,};{int(t['debt_amount']):,};{t['due_date'] or ''};{t['comment'] or ''}\n")

    file_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(file_dir, exist_ok=True)
    filename = f"hisobot_{store_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(file_dir, filename)
    
    with open(filepath, "w", encoding="utf-8-sig") as f:
        f.write(output.getvalue())
        
    return filepath
