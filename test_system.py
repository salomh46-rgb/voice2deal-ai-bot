import unittest
import sys
sys.stdout.reconfigure(encoding='utf-8')

from ai_engine import parse_voice_or_text
from database import record_transaction, get_kassa_summary, get_debtors_list
from excel_export import export_kassa_excel
from bot import handle_user_input

class TestVoice2Deal(unittest.TestCase):
    def test_database_and_kassa(self):
        telegram_id = 77712345
        ai_data = {
            'operation_type': 'sale',
            'client_name': 'Rustam aka',
            'client_phone': '+998901234567',
            'items': [{'name': 'Moy filtr', 'qty': 5, 'price': 40000, 'total': 200000}],
            'total_amount': 200000,
            'paid_amount': 100000,
            'debt_amount': 100000,
            'due_date': 'Dushanba'
        }
        tx = record_transaction(telegram_id, ai_data, 'Test xabar')
        self.assertIsNotNone(tx.get('tx_id'))
        
        summary = get_kassa_summary(telegram_id)
        self.assertGreaterEqual(summary['today']['total_sales'], 200000)
        self.assertGreaterEqual(summary['overall_debt'], 100000)
        print('Database & Kassa Test OK!', flush=True)

    def test_excel_export(self):
        telegram_id = 77712345
        csv_bytes = export_kassa_excel(telegram_id)
        self.assertGreater(len(csv_bytes), 50)
        print('Excel/CSV Export Test OK!', flush=True)

    def test_bot_interaction(self):
        telegram_id = 77712345
        res = handle_user_input(telegram_id, 'Javohirbek', text='/start')
        self.assertIn('Voice2Deal', res['text'])
        print('Bot /start test OK!', flush=True)

        res_kassa = handle_user_input(telegram_id, 'Javohirbek', text='/kassa')
        self.assertIn('KASSA HISOBOTI', res_kassa['text'])
        print('Bot /kassa test OK!', flush=True)

        res_qarz = handle_user_input(telegram_id, 'Javohirbek', text='/qarzlar')
        self.assertIn('NASIYA DAFTARI', res_qarz['text'])
        print('Bot /qarzlar test OK!', flush=True)

if __name__ == '__main__':
    unittest.main()
