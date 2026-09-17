import os
from datetime import datetime

def format_number(n):
    try:
        return f"{int(round(float(n))):,}".replace(",", " ")
    except Exception:
        return str(n)

def generate_thermal_receipt_text(tx_data, store_data=None, paper_width="58mm"):
    """
    Do'konlar va xaridorlar uchun professional 58mm/80mm chek matnini generatsiya qiladi.
    58mm uchun 32 ta belgi kengligi, 80mm uchun 42 ta belgi kengligi ishlatiladi.
    """
    if store_data is None:
        store_data = {}

    store_name = store_data.get("store_name", "Mening Do'konim")
    store_code = store_data.get("store_code", "DK-0000")
    
    tx_id = tx_data.get("tx_id") or tx_data.get("id") or "1"
    client_name = tx_data.get("client_name") or "Noma'lum Xaridor"
    total_amount = format_number(tx_data.get("total_amount", tx_data.get("total", 0)))
    paid_amount = format_number(tx_data.get("paid_amount", tx_data.get("paid", 0)))
    debt_amount = format_number(tx_data.get("debt_amount", tx_data.get("debt", 0)))
    due_date = tx_data.get("due_date")
    items = tx_data.get("items") or []
    op_type = tx_data.get("operation_type") or ("debt_give" if float(tx_data.get("debt_amount", 0) or 0) > 0 else "sale")
    
    date_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    is_80 = (paper_width == "80mm")
    col_width = 42 if is_80 else 32
    
    lines = []
    div_line = "-" * col_width
    double_div = "=" * col_width

    # Header
    lines.append(double_div)
    lines.append(store_name[:col_width].center(col_width))
    lines.append(f"Do'kon: {store_code}"[:col_width].center(col_width))
    lines.append(f"Chek #{tx_id}  {date_str}"[:col_width])
    lines.append(div_line)
    lines.append(f"Mijoz: {client_name}"[:col_width])
    lines.append(div_line)

    # Mahsulotlar jadvali
    if items:
        if is_80:
            lines.append("Nomi               Soni  Narxi    Jami")
            lines.append(div_line)
            for it in items:
                name = str(it.get("name", "Mahsulot"))[:16]
                qty = str(it.get("qty", 1))[:4]
                price = format_number(it.get("price", 0))[:8]
                tot = format_number(it.get("total", float(it.get("qty", 1)) * float(it.get("price", 0))))[:9]
                lines.append(f"{name:<16} {qty:<4} {price:<8} {tot:>8}")
        else:
            lines.append("Nomi         Soni Narxi   Jami")
            lines.append(div_line)
            for it in items:
                name = str(it.get("name", "Mahsulot"))[:12]
                qty = str(it.get("qty", 1))[:3]
                price = format_number(it.get("price", 0))[:6]
                tot = format_number(it.get("total", float(it.get("qty", 1)) * float(it.get("price", 0))))[:7]
                lines.append(f"{name:<12} {qty:<3} {price:<6} {tot:>7}")
    else:
        op_label = "Nasiya savdo" if op_type in ["debt_give", "nasiya"] else ("Qarz to'lovi" if op_type == "debt_payment" else "Savdo amali")
        lines.append(f"{op_label:<18} {total_amount:>10} so'm"[:col_width])

    lines.append(double_div)
    lines.append(f"JAMI SUMMA: {total_amount} so'm"[:col_width])
    lines.append(f"TO'LANDI:   {paid_amount} so'm"[:col_width])
    
    debt_val = float(tx_data.get("debt_amount", tx_data.get("debt", 0)) or 0)
    if debt_val > 0:
        lines.append(f"NASIYA (QARZ): {debt_amount} so'm"[:col_width])
        if due_date:
            lines.append(f"Muddati: {due_date}"[:col_width])
            
    lines.append(div_line)
    lines.append("XARIDINGIZ UCHUN TASHAKKUR!".center(col_width))
    lines.append("Voice2Deal AI Kassa".center(col_width))
    lines.append(double_div)

    return "\n".join(lines)


def generate_thermal_receipt_html(tx_data, store_data=None, paper_width="58mm"):
    """
    Bozor termal printerlari (58mm/80mm) uchun to'g'ridan-to'g'ri chop etishga tayyor
    yuqori aniqlikdagi monoxrom HTML/CSS shabloni.
    """
    if store_data is None:
        store_data = {}

    store_name = store_data.get("store_name", "Mening Do'konim")
    store_code = store_data.get("store_code", "DK-0000")
    
    tx_id = tx_data.get("tx_id") or tx_data.get("id") or "1"
    client_name = tx_data.get("client_name") or "Noma'lum Xaridor"
    total_amount = format_number(tx_data.get("total_amount", tx_data.get("total", 0)))
    paid_amount = format_number(tx_data.get("paid_amount", tx_data.get("paid", 0)))
    debt_amount = format_number(tx_data.get("debt_amount", tx_data.get("debt", 0)))
    due_date = tx_data.get("due_date")
    items = tx_data.get("items") or []
    op_type = tx_data.get("operation_type") or ("debt_give" if float(tx_data.get("debt_amount", 0) or 0) > 0 else "sale")
    
    date_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    width_css = "58mm" if paper_width == "58mm" else "80mm"
    
    items_html = ""
    if items:
        for it in items:
            name = it.get("name", "Mahsulot")
            qty = it.get("qty", 1)
            price = format_number(it.get("price", 0))
            tot = format_number(it.get("total", float(qty) * float(it.get("price", 0))))
            items_html += f"""
            <tr>
                <td style="text-align: left; padding: 2px 0;">{name}</td>
                <td style="text-align: center; padding: 2px 0;">{qty}</td>
                <td style="text-align: right; padding: 2px 0;">{price}</td>
                <td style="text-align: right; padding: 2px 0; font-weight: bold;">{tot}</td>
            </tr>
            """
    else:
        op_label = "Nasiya savdo" if op_type in ["debt_give", "nasiya"] else ("Qarz to'lovi" if op_type == "debt_payment" else "Savdo amali")
        items_html = f"""
        <tr>
            <td colspan="3" style="text-align: left; padding: 4px 0;">{op_label}</td>
            <td style="text-align: right; padding: 4px 0; font-weight: bold;">{total_amount} so'm</td>
        </tr>
        """

    debt_val = float(tx_data.get("debt_amount", tx_data.get("debt", 0)) or 0)
    debt_block = ""
    if debt_val > 0:
        debt_block = f"""
        <div style="display: flex; justify-content: space-between; font-weight: bold; margin-top: 2px; color: #000;">
            <span>NASIYA (QARZ):</span>
            <span>{debt_amount} so'm</span>
        </div>
        """
        if due_date:
            debt_block += f"""
            <div style="display: flex; justify-content: space-between; font-size: 11px; margin-top: 1px;">
                <span>Qaytarish muddati:</span>
                <span>{due_date}</span>
            </div>
            """

    html = f"""<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<title>Kvitansiya #{tx_id} - {store_name}</title>
<style>
  @page {{
    size: {width_css} auto;
    margin: 0;
  }}
  body {{
    margin: 0;
    padding: 6px;
    background: #fff;
    color: #000;
    font-family: 'Courier New', Courier, monospace;
    font-size: 12px;
    line-height: 1.25;
    width: {width_css};
    max-width: 100%;
    box-sizing: border-box;
  }}
  .center {{ text-align: center; }}
  .bold {{ font-weight: bold; }}
  .divider {{ border-top: 1px dashed #000; margin: 4px 0; }}
  .double-divider {{ border-top: 2px solid #000; margin: 5px 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  .barcode {{
    font-family: monospace;
    letter-spacing: 4px;
    font-size: 14px;
    margin-top: 4px;
  }}
  @media print {{
    body {{
      width: {width_css};
      padding: 0;
    }}
    .no-print {{ display: none !important; }}
  }}
</style>
</head>
<body>
  <div class="center bold" style="font-size: 15px;">{store_name}</div>
  <div class="center" style="font-size: 11px;">Do'kon kodi: {store_code}</div>
  <div class="center" style="font-size: 11px;">Chek: #{tx_id} | {date_str}</div>
  <div class="divider"></div>
  
  <div style="font-size: 12px;">Mijoz: <b>{client_name}</b></div>
  <div class="divider"></div>

  <table>
    <thead>
      <tr style="border-bottom: 1px solid #000;">
        <th style="text-align: left;">Nomi</th>
        <th style="text-align: center;">Soni</th>
        <th style="text-align: right;">Narx</th>
        <th style="text-align: right;">Jami</th>
      </tr>
    </thead>
    <tbody>
      {items_html}
    </tbody>
  </table>

  <div class="double-divider"></div>
  
  <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: bold;">
    <span>JAMI:</span>
    <span>{total_amount} so'm</span>
  </div>
  <div style="display: flex; justify-content: space-between; font-size: 12px; margin-top: 2px;">
    <span>To'landi:</span>
    <span>{paid_amount} so'm</span>
  </div>
  {debt_block}

  <div class="divider"></div>
  <div class="center" style="font-size: 11px;">Xaridingiz uchun rahmat!</div>
  <div class="center barcode">||| | |||| | ||||| |||</div>
  <div class="center" style="font-size: 10px; color: #555;">Voice2Deal AI * O'zbekiston</div>
</body>
</html>"""
    return html

