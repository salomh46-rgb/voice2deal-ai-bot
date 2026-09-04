# 🎙 Voice2Deal AI — Ovozli Savdo, Ombor & Nasiya Daftari AI Tizimi

<div align="center">

[![Telegram Bot](https://img.shields.io/badge/Telegram_Bot-%40Ovozli__SavdoBOT-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/Ovozli_SavdoBOT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Google Gemini AI](https://img.shields.io/badge/Google_Gemini-3.1_Flash-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![SQLite WAL](https://img.shields.io/badge/Database-SQLite_WAL-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<p align="center">
  <b>O'zbekiston do'kondorlari va tadbirkorlari uchun sun'iy intellekt (AI) asosida ishlovchi avtomatlashtirilgan kassa, ombor va nasiya daftari Telegram boti.</b>
</p>

</div>

---

## ✨ Asosiy Imkoniyatlar

- 🎙 **Ovozli Savdo Kiritish:** Do'kondor o'zbek tilida (har qanday lahja va tezlikda) ovoz yuboradi — AI tushunib, kassa, qarz yoki omborga avtomatik yozadi.
- ⚡️ **Bir vaqtda bir nechta mijoz:** «*Islomxon aka 70 ming, Javohir 50 ming qarzlarini to'lashdi*» kabi murakkab ovozlarni alohida ajratib yozish.
- 👥 **Xodimlar (Sotuvchilar) Tizimi:** Xo'jayin do'kon kodi orqali cheksiz sotuvchilarni ulaydi. Sotuvchi kiritgan savdolar darhol xo'jayin kassa hisobotida aks etadi.
- 📦 **Avtomatlashtirilgan Ombor (Sklad):** Tovar sotilishi bilan ombordan avtomatik kamayish va 5 tadan kam qolganda ogohlantirish.
- 🧾 **Elektron Chek & Kvitansiya:** Har bir savdo uchun mijozga yuboriladigan chiroyli QR-kodli elektron chek.
- 🤖 **24/7 AI Maslahatchi & Tirik Support:** Savollarga javob beruvchi sun'iy intellekt va adminga 2 tomonlama xabar yuborish.
- 🛡 **Self-Healing & Auto-Recovery:** SQLite WAL yuqori tezlikli rejim, Gemini fallback modellar zanjiri va har 5 daqiqada o'z-o'zini ta'mirlovchi Sentinel Watchdog.
- 🗄 **Avtomatik Zaxira (Backup):** Har 12 soatda bazani adminga avtomatik yuborish va `/health` diagnostikasi.

---

## 🏛 Tizim Arxitekturasi

```
+-------------------------------------------------------------+
|              Telegram Foydalanuvchisi / Sotuvchi            |
+-------------------------------------------------------------+
                              | (Ovozli xabar / Matn)
                              v
+-------------------------------------------------------------+
|                   bot.py (Polling & Routing)                |
+-------------------------------------------------------------+
        |                                       |
        v                                       v
+-----------------------+           +-----------------------+
|    ai_engine.py       |           |     database.py       |
|  - Gemini 3.1 Flash   |           |  - SQLite WAL Mode    |
|  - Fallback Chain     |           |  - Concurrency Lock   |
|  - Regex Self-Repair  |           |  - Auto-Integrity     |
+-----------------------+           +-----------------------+
        |                                       |
        +-------------------+-------------------+
                            |
                            v
+-------------------------------------------------------------+
|              self_healing_watchdog.py (Sentinel)            |
|     (5 daqiqalik monitoring, Auto-Repair, Admin Alert)      |
+-------------------------------------------------------------+
```

---

## 🚀 VPS Serverga O'rnatish (Deployment)

### 1-Usul: Docker orqali (Tavsiya etiladi ⭐️)

1. Serveringizga (Ubuntu/Debian) kiring va repozitoriyni klonlang:
   ```bash
   git clone https://github.com/salomh46-rgb/voice2deal-ai-bot.git
   cd voice2deal-ai-bot
   ```

2. `.env` faylini yarating va API kalitlaringizni kiriting:
   ```bash
   cp .env.example .env
   nano .env
   ```

3. O'rnatish skriptini ishga tushiring:
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

4. Loglarni real-time kuzatish:
   ```bash
   docker compose logs -f
   ```

---

### 2-Usul: Systemd (Linux Service) orqali

1. Loyihani `/opt/voice2deal_ai` papkasiga yuklang:
   ```bash
   git clone https://github.com/salomh46-rgb/voice2deal-ai-bot.git /opt/voice2deal_ai
   cd /opt/voice2deal_ai
   pip3 install -r requirements.txt
   ```

2. Systemd servis faylini o'rnating:
   ```bash
   sudo cp voice2deal.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable voice2deal
   sudo systemctl start voice2deal
   ```

3. Servis holatini tekshirish:
   ```bash
   sudo systemctl status voice2deal
   ```

---

## ⚙️ Sozlamalar (.env)

```env
TELEGRAM_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key
ADMIN_ID=1320855100
```

---

## 👨‍💻 Muallif & Dasturchi
- **Dasturchi:** [Jasper](https://github.com/salomh46-rgb)
- **Portfolio:** [bestportfoliyo-o4z2.vercel.app](https://bestportfoliyo-o4z2.vercel.app/)
- **Telegram Bot:** [@Ovozli_SavdoBOT](https://t.me/Ovozli_SavdoBOT)
- **Admin ID:** `1320855100`

---

<div align="center">
  <b>⭐️ Agar loyiha sizga ma'qul kelgan bo'lsa, repozitoriyga Star (⭐️) bosishni unutmang!</b>
</div>
