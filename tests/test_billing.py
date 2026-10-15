"""Billing calculations, duplicate protection and saved invoice behaviour."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from html import unescape
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from zoneinfo import ZoneInfo

from app import create_app
from database import get_db, PROJECT_DIR


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {"TESTING": True, "SECRET_KEY": "billing-test", "DATABASE": str(Path(self.temp.name) / "test.db")}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.form_token, self.csrf = self.tokens(self.client)

    def tokens(self, client):
        html = client.get('/bills/new').get_data(as_text=True)
        token = unescape(re.search(r'id="form-token" value="([^"]+)"', html).group(1))
        with client.session_transaction() as session:
            csrf = session['csrf_token']
        return token, csrf

    def payload(self, **changes):
        payload = {
            'csrf_token': self.csrf, 'form_token': self.form_token,
            'customer_name': 'ગુજરાતી ગ્રાહક',
            'bill_date': datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m-%d'),
            'items_json': json.dumps([{'item_id': 1, 'quantity': 2, 'price': '100'}, {'item_id': 2, 'quantity': 3, 'price': '50'}]),
        }
        payload.update(changes)
        return payload

    def test_save_exact_total_snapshot_and_dashboard(self):
        response = self.client.post('/bills/new', data=self.payload(total_paise='1'))
        self.assertEqual(response.status_code, 302)
        html = self.client.get(response.location).get_data(as_text=True)
        self.assertIn('ગુજરાતી ગ્રાહક', html)
        self.assertIn('₹350.00', html)
        self.assertIn('ખજૂર ઠળિયા વાળો', html)
        self.assertIn('data-submission-token=', html)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute('SELECT total_paise FROM bills').fetchone()[0], 35000)
            self.assertEqual(db.execute('SELECT price_paise FROM bill_items ORDER BY id').fetchone()[0], 10000)
            self.assertEqual(db.execute('SELECT price_paise FROM items WHERE id=1').fetchone()[0], 6000)
        self.assertIn('₹350.00', self.client.get('/').get_data(as_text=True))

    def test_repeated_submit_and_reprint_only_count_once(self):
        first = self.client.post('/bills/new', data=self.payload())
        retry = self.client.post('/bills/new', data=self.payload())
        self.assertEqual(first.location, retry.location)
        for _ in range(3):
            self.assertEqual(self.client.get(first.location).status_code, 200)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM bills').fetchone()[0], 1)
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM bill_items').fetchone()[0], 2)

    def test_concurrent_retry_saves_once(self):
        def save(_):
            client = self.app.test_client()
            _, csrf = self.tokens(client)
            response = client.post('/bills/new', data=self.payload(csrf_token=csrf))
            return response.status_code, response.location
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 302)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM bills').fetchone()[0], 1)

    def test_invalid_input_does_not_save_partial_bill(self):
        bad_rows = ['broken json', '{}', '[]', '[null]', '[1]', json.dumps([{'item_id': 1, 'quantity': '1.5', 'price': '10'}]), json.dumps([{'item_id': 1, 'quantity': 1, 'price': 'NaN'}]), json.dumps([{'item_id': 1, 'quantity': 0, 'price': '10'}]), json.dumps([{'item_id': 1, 'quantity': 1, 'price': '1.234'}]), json.dumps([{'item_id': 99999, 'quantity': 1, 'price': '10'}])]
        for rows in bad_rows:
            with self.subTest(rows=rows):
                self.assertEqual(self.client.post('/bills/new', data=self.payload(items_json=rows)).status_code, 422)
        for changes in [{'customer_name': ' '}, {'bill_date': '2026-02-30'}, {'form_token': 'fake'}]:
            self.assertEqual(self.client.post('/bills/new', data=self.payload(**changes)).status_code, 422)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM bills').fetchone()[0], 0)
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM bill_items').fetchone()[0], 0)

    def test_gujarati_numbers_and_decimal_precision(self):
        rows = [{'item_id': 1, 'quantity': '૩', 'price': '૦.૧૦'}]
        self.assertEqual(self.client.post('/bills/new', data=self.payload(items_json=json.dumps(rows))).status_code, 302)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT total_paise FROM bills').fetchone()[0], 30)

    def test_snapshot_survives_catalogue_changes_and_restart(self):
        response = self.client.post('/bills/new', data=self.payload())
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE items SET gujarati_name='Changed', price_paise=1 WHERE id=1")
            db.execute('DELETE FROM items WHERE id=2')
            db.commit()
        restarted = create_app(self.config).test_client()
        html = restarted.get(response.location).get_data(as_text=True)
        self.assertIn('ખજૂર ઠળિયા વાળો', html)
        self.assertIn('ખજૂર ઠળિયા વગરનો', html)
        self.assertIn('₹350.00', html)
        retry = self.client.post('/bills/new', data=self.payload())
        self.assertEqual(retry.location, response.location)

    def test_history_search_and_missing_bill(self):
        self.client.post('/bills/new', data=self.payload())
        html = self.client.get('/bills', query_string={'q': 'ગુજરાતી'}).get_data(as_text=True)
        self.assertIn('ગુજરાતી ગ્રાહક', html)
        self.assertIn('₹350.00', html)
        self.assertEqual(self.client.get('/bills/99999').status_code, 404)

    def test_missing_csrf_and_too_many_lines_rejected(self):
        self.assertEqual(self.client.post('/bills/new', data=self.payload(csrf_token='')).status_code, 400)
        rows = [{'item_id': 1, 'quantity': 1, 'price': '1'}] * 201
        self.assertEqual(self.client.post('/bills/new', data=self.payload(items_json=json.dumps(rows))).status_code, 422)

    def test_version_one_database_upgrade_preserves_existing_bill(self):
        old_path = Path(self.temp.name) / 'old.db'
        with closing(sqlite3.connect(old_path)) as db, db:
            db.executescript((PROJECT_DIR / 'schema.sql').read_text())
            db.execute("INSERT INTO bills (bill_number, customer_name, bill_date, total_paise) VALUES ('old-1', 'Existing', '2026-10-01', 500)")
        upgraded = create_app({**self.config, 'DATABASE': str(old_path)})
        with upgraded.app_context():
            self.assertEqual(get_db().execute('PRAGMA user_version').fetchone()[0], 4)
            self.assertEqual(get_db().execute('SELECT total_paise FROM bills').fetchone()[0], 500)
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM bill_submissions').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
