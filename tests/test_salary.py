"""Monthly earnings, rate history, attendance validation, and advances."""

from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path
import re
import tempfile
import unittest

from app import create_app
from database import get_db
from salary import monthly_summary


class SalaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {'TESTING': True, 'SECRET_KEY': 'salary-test', 'DATABASE': str(Path(self.temp.name)/'test.db')}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.worker_token = self.token(self.client, '/workers/new')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf_token']

    def token(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(r'name="form_token" value="([^"]+)"', response.get_data(as_text=True))
        return unescape(match.group(1)) if match else None

    def post(self, path, **values):
        return self.client.post(path, data={'csrf_token': self.csrf, **values})

    def create(self, rate='50'):
        return self.post('/workers/new', name='ટેસ્ટ કર્મચારી', rate=rate, form_token=self.worker_token)

    def advance(self, amount='1000', day='2020-02-10', token=None):
        token = token or self.token(self.client, '/workers/1/advances/new')
        return self.post('/workers/1/advances/new', amount=amount, date=day, reason='વ્યક્તિગત ખર્ચ', form_token=token)

    def test_full_month_formula_and_printable_statement(self):
        self.assertEqual(self.create().status_code, 302)
        for day in range(1,11):
            response = self.post('/workers/1/hours/new', date=f'2020-02-{day:02d}', hours='૧૦')
            self.assertEqual(response.status_code, 302)
        self.assertEqual(self.advance().status_code, 302)
        with self.app.app_context():
            summary = monthly_summary(1, '2020-02')
            self.assertEqual(summary['hours'], 100)
            self.assertEqual(summary['gross'], 500000)
            self.assertEqual(summary['advance'], 100000)
            self.assertEqual(summary['payable'], 400000)
        html = self.client.get('/workers/1/statement?month=2020-02').get_data(as_text=True)
        for value in ['₹4,000.00', '₹5,000.00', '₹1,000.00', '29/02', 'વ્યક્તિગત ખર્ચ', 'પ્રિન્ટ / PDF']:
            self.assertIn(value, html)
        self.assertNotIn('30/02', html)

    def test_rate_change_and_hours_edit_preserve_history(self):
        self.create()
        self.post('/workers/1/hours/new', date='2020-02-01', hours='8')
        self.post('/workers/1/edit', name='ટેસ્ટ કર્મચારી', rate='100')
        self.post('/workers/1/hours/new', date='2020-02-02', hours='8')
        self.assertEqual(self.post('/workers/1/hours/1/edit', date='2020-02-02', hours='9').status_code, 302)
        with self.app.app_context():
            rows = get_db().execute('SELECT * FROM worker_hours ORDER BY id').fetchall()
            self.assertEqual(rows[0]['date'], '2020-02-01')
            self.assertEqual(rows[0]['hourly_rate_paise'], 5000)
            self.assertEqual(rows[1]['hourly_rate_paise'], 10000)
            self.assertEqual(monthly_summary(1,'2020-02')['gross'], 125000)

    def test_other_month_advances_excluded_and_excess_explicit(self):
        self.create()
        self.advance('500', '2020-01-10')
        self.post('/workers/1/hours/new', date='2020-02-01', hours='2')
        with self.app.app_context():
            self.assertEqual(monthly_summary(1,'2020-02')['advance'], 0)
            self.assertEqual(monthly_summary(1,'2020-02')['payable'], 10000)
        self.advance('150', '2020-02-10')
        with self.app.app_context():
            summary = monthly_summary(1,'2020-02')
            self.assertEqual(summary['payable'],0)
            self.assertEqual(summary['excess'],5000)
        html = self.client.get('/workers/1?month=2020-02').get_data(as_text=True)
        self.assertIn('₹50.00 વધારે',html)

    def test_duplicate_worker_and_advance_submissions(self):
        self.create()
        self.create()
        token = self.token(self.client,'/workers/1/advances/new')
        self.advance(token=token)
        self.advance(token=token)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM workers').fetchone()[0],1)
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM worker_advances').fetchone()[0],1)

    def test_concurrent_advance_retry_saves_once(self):
        self.create()
        token = self.token(self.client, '/workers/1/advances/new')
        def save(_):
            client = self.app.test_client()
            self.token(client,'/workers/1/advances/new')
            with client.session_transaction() as session:
                csrf = session['csrf_token']
            return client.post('/workers/1/advances/new', data={'csrf_token':csrf,'form_token':token,'date':'2020-02-10','reason':'Test','amount':'100'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(save,range(2))),[302,302])
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM worker_advances').fetchone()[0],1)

    def test_hours_validation_and_one_record_per_day(self):
        self.create()
        for hours in ['-1','25','NaN','Infinity','1.234','1e2']:
            self.assertEqual(self.post('/workers/1/hours/new',date='2020-02-01',hours=hours).status_code,422)
        for day in ['2020-02-30','9999-01-01','not a date']:
            self.assertEqual(self.post('/workers/1/hours/new',date=day,hours='8').status_code,422)
        self.assertEqual(self.post('/workers/1/hours/new',date='2020-02-01',hours='૦').status_code,302)
        self.assertEqual(self.post('/workers/1/hours/new',date='2020-02-01',hours='8').status_code,422)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM worker_hours').fetchone()[0],1)
            self.assertEqual(get_db().execute('SELECT hours FROM worker_hours').fetchone()[0],0)

    def test_rounding_is_per_day_to_nearest_paisa(self):
        self.create(rate='૦.૫૦')
        self.post('/workers/1/hours/new', date='2020-02-01',hours='0.01')
        self.post('/workers/1/hours/new', date='2020-02-02',hours='0.01')
        with self.app.app_context():
            self.assertEqual(monthly_summary(1,'2020-02')['gross'],2)

    def test_advance_deletion_and_worker_history_protection(self):
        self.create()
        self.advance()
        self.assertEqual(self.post('/workers/1/delete').status_code,409)
        self.assertEqual(self.client.get('/workers/1/advances/1/delete').status_code,200)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM worker_advances').fetchone()[0],1)
        self.assertEqual(self.post('/workers/1/advances/1/delete').status_code,302)
        self.post('/workers/1/hours/new',date='2020-02-01',hours='8')
        self.assertEqual(self.post('/workers/1/delete').status_code,409)

    def test_empty_worker_can_be_deleted(self):
        self.create()
        self.assertEqual(self.client.get('/workers/1/delete').status_code,200)
        self.assertEqual(self.post('/workers/1/delete').status_code,302)
        self.assertEqual(self.client.get('/workers/1').status_code,404)

    def test_validation_missing_records_and_restart(self):
        self.assertEqual(self.post('/workers/new',name=' ',rate='50',form_token=self.worker_token).status_code,422)
        self.assertEqual(self.create(rate='0').status_code,422)
        self.create()
        token = self.token(self.client,'/workers/1/advances/new')
        self.assertEqual(self.post('/workers/1/advances/new',amount='NaN',date='2020-02-01',reason='',form_token=token).status_code,422)
        self.post('/workers/1/hours/new',date='2020-02-01',hours='8')
        self.assertEqual(self.client.get('/workers/1/hours/999/edit').status_code,404)
        self.assertEqual(self.client.get('/workers/999').status_code,404)
        self.assertEqual(self.client.get('/workers/1?month=2020-13').status_code,400)
        self.assertEqual(self.client.post('/workers/1/hours/new',data={'date':'2020-02-02','hours':'8'}).status_code,400)
        restarted=create_app(self.config).test_client()
        self.assertIn('₹400.00',restarted.get('/workers/1?month=2020-02').get_data(as_text=True))
        self.assertIn('ટેસ્ટ કર્મચારી',restarted.get('/workers?q=ટેસ્ટ&month=2020-02').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
