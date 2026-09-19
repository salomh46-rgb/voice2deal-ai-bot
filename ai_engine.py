import json
import urllib.request
import os
import re
import time

try:
    from config import GEMINI_API_KEY, GEMINI_MODELS as MODEL_CANDIDATES
except ImportError:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6JVDYUVVHaR7Pwpce0JcIWqBjU35JQaTPnGpq3Qxg3Kvg")
    MODEL_CANDIDATES = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

SYSTEM_INSTRUCTION = """Siz O'zbekiston savdo do'konlari, kassa, ombor va qarz daftari uchun ixtisoslashgan ENG AQLLI OVOZLI AI YORDAMCHISIZ.

VAZIFANGIZ:
Ovozli xabar yoki matndagi BARCHA aytilgan odamlar, summatar va amallarni 100% aniqlikda eshitib, QAT'IY JSON (yoki agar bir nechta odam bo'lsa JSON ARRAY: [ {...}, {...} ]) formatida chiqarish.

ASOSIY QOIDALAR:

1. BIR VAQTNING O'ZIDA BIR NECHTA MIJOZ AYTILGANDA (JUDA MUHIM):
   - Agar gapda 2 yoki undan ortiq odamning to'lovi/qarzi aytilsa (masalan: "Islomxon aka 70 ming, Javohir ukam 50 ming, Ukam 50 ming qarzini berdi"):
     -> HAR BIR ODAM UCHUN ALOHIDA OB'EKT YARATING VA RO'YXAT (ARRAY: [ {...}, {...}, {...} ]) QAYTARING!
     -> Hech qaysi odamni yoki summani birlashtirib yubormang yoki tashlab ketmang!

2. QARZ BERISH vs QARZ TO'LASH FARQI:
   A) QARZ TO'LOVI (operation_type: "debt_payment"):
      - "qarzini berdi", "qarzini to'ladi", "qarzini olib keldi", "qarzini yopdi", "pulini berdi"
      -> operation_type: "debt_payment", paid_amount: summa, debt_amount: 0

   B) QARZ BERILDI / NASIYA (operation_type: "debt_give" yoki "sale"):
      - "qarzi bor", "qarzga berdim", "qarz oldi", "nasiyaga yoz", "qarzga yozib qo'y"
      -> operation_type: "debt_give", paid_amount: 0, debt_amount: summa

3. MIJOZ ISM-SHARIFI:
   - "Islomxon aka", "Javohir ukam", "Ukam", "Sardor qassob", "Akmal akam" kabi to'liq aytilgan nomlarni xuddi aytilgandek client_name ga yozing.

4. OMOBOR / SKLADGA KIRIM (operation_type: "inventory_in"):
   - "skladga 50 ta kola 12 mingdan kirdi", "omborga 100 ta moy filtr kiritdim"
   -> operation_type: "inventory_in", items: [{"name": "...", "qty": ..., "price": ...}]

JAVOB FORMATI:
Agar 1 ta amal bo'lsa:
{
  "operation_type": "debt_payment | debt_give | sale | expense | inventory_in",
  "client_name": "Mijoz ismi",
  "total_amount": 50000,
  "paid_amount": 50000,
  "debt_amount": 0,
  "comment": "Izoh"
}

Agar bir nechta mijoz/amal bo'lsa (JSON Array):
[
  {
    "operation_type": "debt_payment",
    "client_name": "Islomxon aka",
    "total_amount": 70000,
    "paid_amount": 70000,
    "debt_amount": 0,
    "comment": "Islomxon aka 70 000 so'm qarzini to'ladi"
  },
  {
    "operation_type": "debt_payment",
    "client_name": "Javohir ukam",
    "total_amount": 50000,
    "paid_amount": 50000,
    "debt_amount": 0,
    "comment": "Javohir ukam 50 000 so'm qarzini to'ladi"
  },
  {
    "operation_type": "debt_payment",
    "client_name": "Ukam",
    "total_amount": 50000,
    "paid_amount": 50000,
    "debt_amount": 0,
    "comment": "Ukam 50 000 so'm qarzini to'ladi"
  }
]
"""

def parse_voice_or_text(text=None, audio_bytes=None, mime_type="audio/ogg"):
    parts = [{"text": SYSTEM_INSTRUCTION}]
    
    if audio_bytes:
        import base64
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        parts.append({
            "inlineData": {
                "mimeType": mime_type,
                "data": b64_audio
            }
        })
        parts.append({"text": "Ovozli xabarni boshidan oxirigacha diqqat bilan eshiting. O'zbek tilidagi barcha ismlar va aytilgan summalarni (masalan '70 ming' -> 70000, '50 ming' -> 50000, 'yuz ming' -> 100000) aniqlang. Har bir odam uchun alohida ob'ekt tuzib, JSON ARRAY [ {...}, {...} ] ko'rinishida chiqaring:"})
    elif text:
        parts.append({"text": f"Foydalanuvchi xabari: {text}"})
    else:
        return None

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
            "response_mime_type": "application/json"
        }
    }

    last_api_error = None
    for attempt in range(2):
        for model in MODEL_CANDIDATES:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": GEMINI_API_KEY
                }
            )
            try:
                res = urllib.request.urlopen(req, timeout=15)
                if res.getcode() == 200:
                    res_json = json.loads(res.read().decode("utf-8"))
                    if res_json.get("candidates") and res_json["candidates"][0].get("content"):
                        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        print(f"AI RAW RESPONSE ({model}): {raw_text[:300]}", flush=True)
                        parsed = parse_json_safely(raw_text)
                        if parsed:
                            return parsed
            except Exception as e:
                err_str = str(e)
                last_api_error = err_str
                print(f"⚠️ Gemini API Error ({model}): {err_str}", flush=True)
                if "429" in err_str:
                    time.sleep(1.0)
                else:
                    time.sleep(0.2)
                continue

    if last_api_error:
        print(f"❌ All Gemini models failed with error: {last_api_error}", flush=True)
        return {"_error": "api_error", "message": last_api_error}

    return None

def parse_json_safely(raw):
    if not raw:
        return None
    try:
        return json.loads(raw.strip())
    except:
        pass
    clean = re.sub(r'```json', '', raw, flags=re.I)
    clean = re.sub(r'```', '', clean).strip()
    try:
        return json.loads(clean)
    except:
        pass
    # Try finding list [ ... ]
    s_arr = clean.find('[')
    e_arr = clean.rfind(']')
    if s_arr != -1 and e_arr != -1 and e_arr > s_arr:
        try:
            return json.loads(clean[s_arr:e_arr+1])
        except:
            pass
    # Try finding object { ... }
    s = clean.find('{')
    e = clean.rfind('}')
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(clean[s:e+1])
        except:
            pass
    return None

def generate_gentle_reminder(client_name, debt_amount, store_name="Do'konimiz", due_date=None):
    """
    Qarzdorlarga bitta tugma bilan muloyim Telegram eslatma yuborish generatori.
    """
    due_str = f" (To'lov muddati: {due_date})" if due_date else ""
    formatted_debt = f"{int(round(float(debt_amount))):,}".replace(",", " ")
    
    default_text = (
        f"Assalomu alaykum, hurmatli {client_name}!\n\n"
        f"'{store_name}' do'konimizdan olingan mahsulotlar uchun {formatted_debt} so'm qarz muddati yetib keldi.{due_str}\n\n"
        f"Iltimos, to'lovni o'zingizga qulay vaqtda amalga oshirishingizni so'raymiz. To'lovni do'konga kelib yoki qulay bo'lsa Click/Payme orqali yuborishingiz mumkin.\n\n"
        f"Hamkorligingiz va ishonchingiz uchun katta tashakkur!"
    )

    prompt = f"""Quyidagi mijozga do'kondan olgan nasiyasi (qarzi) haqida juda xushmuomala, hurmat bilan SMS yoki Telegram eslatma xabari yozib ber:
Mijoz ismi: {client_name}
Nasiya summasi: {formatted_debt} so'm
Do'kon nomi: {store_name}
Muddati: {due_str}

Talablar:
- Faqat 1 ta tayyor xabar matnini qaytar.
- O'zbek tilida (lotin alifbosida), juda muloyim, odobli bo'lsin.
- Boshlanishi: "Assalomu alaykum, hurmatli {client_name}! {store_name} do'konimizdan olingan mahsulotlar uchun {formatted_debt} so'm qarz muddati yetib keldi..."
- Click yoki Payme orqali to'lash imkoni borligini xushmuomalalik bilan eslatib o't.
- Hech qanday qo'shimcha izoh yoki sarlavhasiz, to'g'ridan-to'g'ri yuboriladigan matn bo'lsin.
"""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 800
        }
    }

    for model in MODEL_CANDIDATES:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY
            }
        )
        try:
            res = urllib.request.urlopen(req, timeout=12)
            if res.getcode() == 200:
                res_json = json.loads(res.read().decode("utf-8"))
                if res_json.get("candidates") and res_json["candidates"][0].get("content"):
                    gen_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if len(gen_text) > 30 and (client_name.lower() in gen_text.lower() or "hurmatli" in gen_text.lower()):
                        return gen_text
        except Exception:
            continue

    return default_text


def generate_telegram_share_link(reminder_text):
    """
    Eslatmani bitta tugma bilan mijozga yuborish uchun Telegram Share URL havolasini yaratadi.
    """
    encoded_text = urllib.parse.quote(reminder_text.strip())
    return f"https://t.me/share/url?url={encoded_text}"



def generate_ai_business_report(data):
    store_name = data.get("store_name", "Do'kon")
    sales = data.get("sales", {})
    expense = data.get("expense", 0)
    top_debtors = data.get("top_debtors", [])
    inventory = data.get("inventory", [])
    
    total_sales = f"{int(sales.get('total_volume', 0)):,}".replace(",", " ")
    total_cash = f"{int(sales.get('total_cash', 0)):,}".replace(",", " ")
    total_debt = f"{int(sales.get('total_debt', 0)):,}".replace(",", " ")
    total_expense = f"{int(expense):,}".replace(",", " ")
    
    debtors_text = "\n".join([f"- {d['name']}: {int(d['total_debt']):,} so'm (oxirgi savdo: {str(d['last_deal_date'])[:10]})" for d in top_debtors]) or "Hozircha qarzdorlar yo'q."
    inv_text = "\n".join([f"- {i['name']}: {int(i['quantity'])} {i.get('unit','dona')}" for i in inventory]) or "Sklad ma'lumotlari kiritilmagan."

    prompt = f"""Siz tajribali O'zbekiston chakana savdo va biznes tahlilchisi (Business Consultant AI)siz.
Quyidagi do'kon ko'rsatkichlarini tahlil qilib, do'kon egasiga qisqa, londa va juda foydali BIZNES MASLAHATI va HISOBOT tuzib bering:

Do'kon: {store_name}
Savdolar soni: {sales.get('total_orders', 0)} ta
Jami savdo aylanmasi: {total_sales} so'm
Naqd tushum: {total_cash} so'm
Yangi nasiyalar (qarzlar): {total_debt} so'm
Do'kon xarajatlari: {total_expense} so'm

Top qarzdorlar:
{debtors_text}

Sklad qoldiqlari (kam qolganlar):
{inv_text}

Tahlil talablari:
1. 📊 Moliyaviy holat bahosi (Naqd pul va Nasiya balansi nisbati).
2. ⚠️ Qarzlar xavfi va kimdan birinchi bo'lib undirish kerakligi.
3. 📦 Omborni boshqarish (qaysi tovarlarni tezda sotib olish kerak).
4. 💡 Foydani oshirish bo'yicha 2 ta aniq amaliy maslahat.
Javob o'zbek tilida, emoji belgilar bilan chiroyli va tushunarli formatda bo'lsin.
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1000
        }
    }

    for model in MODEL_CANDIDATES:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY
            }
        )
        try:
            res = urllib.request.urlopen(req, timeout=15)
            if res.getcode() == 200:
                res_json = json.loads(res.read().decode("utf-8"))
                if res_json.get("candidates") and res_json["candidates"][0].get("content"):
                    return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            continue

    return (
        f"📊 <b>«{store_name}» Biznes Tahlili</b>\n\n"
        f"💰 <b>Jami aylanma:</b> {total_sales} so'm (Naqd: {total_cash} so'm, Nasiya: {total_debt} so'm)\n"
        f"📉 <b>Xarajatlar:</b> {total_expense} so'm\n\n"
        f"💡 <b>Tavsiya:</b> Nasiyalarni o'z vaqtida yig'ish va kam qolgan tovarlarni omborga kiritishni tavsiya qilamiz."
    )


def answer_ai_support(question_text, role="owner", store_name="Do'kon"):
    prompt = f"""Siz Voice2Deal — O'zbekistondagi 1-raqamli Ovozli Savdo, Ombor (Sklad) va Qarz Daftari AI tizimining rasmiy 24/7 QO'LLAB-QUVVATLASH MUTAXASSISI (AI Support Assistant)siz.

Foydalanuvchi roli: {role}
Do'kon nomi: {store_name}
Foydalanuvchi savoli yoki muammosi: "{question_text}"

TIZIM IMKONIYATLARI VA QO'LLANMASI:
1. 🎙 OVOZLI VA MATNLI SAVDO KIRITISH:
   - Mikrofonni bosib ovoz yuboriladi yoki chatga yoziladi.
   - Misollar:
     • Savdo va nasiya: «Akmal akaga 2 ta moy filtr berdim 50 mingdan, 30 mingini berdi, 70 ming qarz»
     • Qarz to'lovi: «Akmal aka 70 ming qarzini to'ladi» yoki bir nechta odam: «Islomxon aka 70 ming, Javohir 50 ming qarzini to'lashdi»
     • Qarz berish (nasiya): «Sardor aka 100 ming qarzga oldi»
     • Xarajat: «Do'kon arendasiga 1 million to'ladim»
     • Ombor/Sklad: «Skladga 50 ta Coca-Cola 12 mingdan kirdi»

2. 📦 SKLAD & TOVAR QOLDIQLARI:
   - Tovarlar ovoz orqali kiritilganda omborga qo'shiladi. Har bir tovar sotilganda avtomatik ravishda ombordagi qoldiqdan kamayib boradi.

3. 👥 XODIMLAR VA SOTUVCHILARNI ULASH:
   - Do'kon egasi «👥 Xodimlarim» bo'limidan do'kon kodini (masalan DK-1052) olib sotuvchiga beradi.
   - Sotuvchi botga ulanib o'sha kodni kiritadi. Sotuvchi kiritgan savdolar darhol do'kon egasiga tushadi. Sotuvchi o'z hisobini «📊 Mening smenam» orqali ko'radi.

4. 👑 OBUNA VA TO'LOVLAR:
   - Oylik Standart (49 000 so'm), Oylik Pro (89 000 so'm), Yillik VIP (390 000 so'm). Karta: 4916 9903 0500 7954 (JAVOHIRBEK A.). To'lov cheki yuborilgach, admin tasdiqlaydi.

5. ⏳ QARZDORLAR VA AI ESLATMALAR:
   - «⏳ Qarzdorlar daftari» orqali qarzdorlar ko'rinadi. «🔔 Eslatma matni» tugmasi orqali xushmuomala tayyor SMS matn olinadi.

6. 📥 EXCEL HISOBOT:
   - «📥 Excel hisobot» tugmasi orqali barcha savdo va qarzlar .xlsx jadvalida yuklab olinadi.

TALABLAR:
- Foydalanuvchi savoliga o'zbek tilida juda muloyim, tushunarli, lo'nda va amaliy maslahat bering.
- Har doim javob oxirida: «💡 Agar muammoni hal qilib bo'lmasa, pastdagi '👨‍💻 Adminga xabar yuborish' tugmasini bosib to'g'ridan-to'g'ri mutaxassisga yozishingiz mumkin.» deb xushmuomalalik bilan eslatib o'ting.
"""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1000
        }
    }

    for model in MODEL_CANDIDATES:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY
            }
        )
        try:
            res = urllib.request.urlopen(req, timeout=15)
            if res.getcode() == 200:
                res_json = json.loads(res.read().decode("utf-8"))
                if res_json.get("candidates") and res_json["candidates"][0].get("content"):
                    return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            continue

    return (
        "Assalomu alaykum! Voice2Deal tizimidan foydalanish bo'yicha savolingiz qabul qilindi.\n\n"
        "💡 <b>Tezkor yo'riqnoma:</b>\n"
        "• Savdo/qarz kiritish uchun shunchaki ovoz yuboring (masalan: <i>«Akmal akaga 2 ta filtr berdim 50 mingdan»</i>)\n"
        "• Xodimlarni ulash uchun <code>👥 Xodimlarim</code> bo'limidagi Do'kon Kodidan foydalaning.\n"
        "• Agar savolingiz bo'lsa, '👨‍💻 Adminga xabar yuborish' tugmasini bosing."
    )

