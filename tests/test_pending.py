"""Payment amounts, history, duplicate submissions, and bill linking."""

from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path
import re
import tempfile
import unittest

from app import create_app
from billing import current_day
from database import get_db


class PendingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {'TESTING': True, 'SECRET_KEY': 'pending-test', 'DATABASE': str(Path(self.temp.name) / 'test.db')}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.create_token = self.get_token(self.client, '/pending/new')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf_token']

    def get_token(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(r'name="form_token" value="([^"]+)"', response.get_data(as_text=True))
        return unescape(match.group(1)) if match else None

    def post(self, path, **values):
        return self.client.post(path, data={'csrf_token': self.csrf, **values})

    def create(self, **changes):
        values = {'customer_name': 'ટેસ્ટ ગ્રાહક', 'date': current_day(), 'amount': '1000', 'form_token': self.create_token}
        values.update(changes)
        return self.post('/pending/new', **values)

    def payment(self, amount, token=None, **changes):
        if token is None:
            token = self.get_token(self.client, '/pending/1')
        values = {'amount': amount, 'date': current_day(), 'form_token': token}
        values.update(changes)
        return self.post('/pending/1/payments', **values)

    def test_create_retry_edit_and_restart(self):
        first = self.create(amount='૧૦૦૦.૦૧')
        self.assertEqual(first.status_code, 302)
        self.assertEqual(self.create(amount='૧૦૦૦.૦૧').location, first.location)
        response = self.post('/pending/1/edit', customer_name='બદલાયેલ ગ્રાહક', date=current_day(), amount='1100.25')
        self.assertEqual(response.status_code, 302)
        restarted = create_app(self.config).test_client()
        html = restarted.get('/pending/1').get_data(as_text=True)
        self.assertIn('બદલાયેલ ગ્રાહક', html)
        self.assertIn('₹1,100.25', html)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM pending_bills').fetchone()[0], 1)

    def test_partial_then_full_payment_and_filters(self):
        self.create()
        self.assertEqual(self.payment('૩૦૦').status_code, 302)
        html = self.client.get('/pending/1').get_data(as_text=True)
        self.assertIn('₹700.00', html)
        self.assertIn('₹300.00', html)
        self.assertEqual(self.payment('700').status_code, 302)
        html = self.client.get('/pending/1').get_data(as_text=True)
        self.assertIn('સંપૂર્ણ ચૂકવાઈ ગયું', html)
        self.assertNotIn('payment-amount', html)
        self.assertNotIn('ટેસ્ટ ગ્રાહક', self.client.get('/pending').get_data(as_text=True))
        self.assertIn('ટેસ્ટ ગ્રાહક', self.client.get('/pending?status=paid').get_data(as_text=True))
        self.assertIn('ટેસ્ટ ગ્રાહક', self.client.get('/pending?status=all&q=ટેસ્ટ').get_data(as_text=True))

    def test_duplicate_payment_only_recorded_once(self):
        self.create()
        token = self.get_token(self.client, '/pending/1')
        for _ in range(2):
            self.assertEqual(self.payment('300', token).status_code, 302)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute('SELECT COUNT(*) FROM pending_payments').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT SUM(amount_paise) FROM pending_payments').fetchone()[0], 30000)

    def test_overpayment_invalid_values_and_dates_rejected(self):
        self.create()
        for amount in ['1000.01', '0', '-1', 'NaN', '1.234']:
            self.assertEqual(self.payment(amount).status_code, 422)
        self.assertEqual(self.payment('1', date='2000-01-01').status_code, 422)
        self.assertEqual(self.payment('1', date='9999-01-01').status_code, 422)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM pending_payments').fetchone()[0], 0)

    def test_concurrent_payments_cannot_overpay(self):
        self.create()
        def pay(_):
            client = self.app.test_client()
            token = self.get_token(client, '/pending/1')
            with client.session_transaction() as session:
                csrf = session['csrf_token']
            return client.post('/pending/1/payments', data={'csrf_token': csrf, 'form_token': token, 'date': current_day(), 'amount': '700'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(pay, range(2)))
        self.assertEqual(sorted(statuses), [302, 422])
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT SUM(amount_paise) FROM pending_payments').fetchone()[0], 70000)

    def test_cannot_reduce_below_paid_or_delete_payment_history(self):
        self.create()
        self.payment('300')
        self.assertEqual(self.post('/pending/1/edit', customer_name='Name', date=current_day(), amount='200').status_code, 422)
        self.assertEqual(self.post('/pending/1/delete').status_code, 409)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM pending_bills').fetchone()[0], 1)
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM pending_payments').fetchone()[0], 1)

    def test_delete_without_payments_requires_post(self):
        self.create()
        self.assertEqual(self.client.get('/pending/1/delete').status_code, 200)
        self.assertEqual(self.client.get('/pending/1').status_code, 200)
        self.assertEqual(self.post('/pending/1/delete').status_code, 302)
        self.assertEqual(self.client.get('/pending/1').status_code, 404)

    def test_link_saved_bill_is_idempotent_and_preserves_sales(self):
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT INTO bills (bill_number, customer_name, bill_date, total_paise) VALUES ('PM-TEST', 'Saved customer', ?, 35000)", (current_day(),))
            db.commit()
        for _ in range(2):
            self.assertEqual(self.post('/pending/from-bill/1').status_code, 302)
        self.assertEqual(self.post('/pending/1/edit', amount='1').status_code, 302)
        self.payment('50')
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute('SELECT COUNT(*) FROM pending_bills').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT amount_paise FROM pending_bills').fetchone()[0], 35000)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bills').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT total_paise FROM bills').fetchone()[0], 35000)
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('₹350.00', html)
        self.assertIn('₹300.00', html)
        self.assertIn('ચુકવણી / બાકી વિગતો', self.client.get('/bills/1').get_data(as_text=True))

    def test_invalid_create_and_csrf(self):
        for change in [{'amount':'0'}, {'customer_name':' '}, {'date':'2026-02-30'}, {'form_token':'bad'}]:
            self.assertEqual(self.create(**change).status_code, 422)
        self.assertEqual(self.client.post('/pending/new', data={'amount':'10'}).status_code, 400)
        self.assertEqual(self.client.get('/pending/99999').status_code, 404)
        self.assertEqual(self.post('/pending/from-bill/99999').status_code, 404)


if __name__ == '__main__':
    unittest.main()
