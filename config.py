import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", os.environ.get("TELEGRAM_TOKEN", ""))
TELEGRAM_API = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}'
TELEGRAM_FILE_API = f'https://api.telegram.org/file/bot{TELEGRAM_TOKEN}'

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AQ.Ab8RN6JVDYUVVHaR7Pwpce0JcIWqBjU35JQaTPnGpq3Qxg3Kvg')
GEMINI_MODELS = [
    'gemini-2.5-flash',
    'gemini-2.0-flash',
    'gemini-1.5-flash'
]

ADMIN_ID = int(os.environ.get('ADMIN_ID', '1320855100'))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'voice2deal.db'))
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)
