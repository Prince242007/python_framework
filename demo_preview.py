"""Run a disposable demo at http://127.0.0.1:5002 without changing business records."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app import create_app
from billing import current_day
from database import get_db


def prepare_demo(app):
    today = current_day()
    year, month, day = map(int, today.split('-'))
    salary_month = today[:7] if day >= 10 else (date(year, month, 1).fromordinal(date(year, month, 1).toordinal()-1)).strftime('%Y-%m')
    with app.app_context():
        db = get_db()
        for number, name, total in [(1, 'ડેમો ગ્રાહક', 35000), (2, 'Demo Retail Customer', 90000)]:
            db.execute('INSERT INTO bills (id, bill_number, customer_name, bill_date, total_paise) VALUES (?, ?, ?, ?, ?)', (number, f'PM-DEMO-{number:05d}', name, today, total))
        item1 = db.execute('SELECT * FROM items WHERE id=1').fetchone()
        item2 = db.execute('SELECT * FROM items WHERE id=2').fetchone()
        db.executemany('INSERT INTO bill_items (bill_id,item_id,gujarati_name,search_name,quantity,price_paise) VALUES (?,?,?,?,?,?)', [(1,1,item1['gujarati_name'],item1['search_name'],2,10000),(1,2,item2['gujarati_name'],item2['search_name'],3,5000),(2,1,item1['gujarati_name'],item1['search_name'],9,10000)])
        db.execute('INSERT INTO pending_bills (bill_id,date,customer_name,amount_paise) VALUES (2,?,?,90000)',(today,'Demo Retail Customer'))
        db.execute('INSERT INTO pending_payments (pending_bill_id,date,amount_paise) VALUES (1,?,30000)',(today,))
        db.execute('INSERT INTO workers (name,hourly_rate_paise) VALUES (?,5000)',('ડેમો કર્મચારી',))
        db.executemany('INSERT INTO worker_hours (worker_id,date,hours,hourly_rate_paise) VALUES (1,?,10,5000)', [(f'{salary_month}-{d:02d}',) for d in range(1,11)])
        db.execute('INSERT INTO worker_advances (worker_id,date,reason,amount_paise) VALUES (1,?,?,100000)',(f'{salary_month}-10','વ્યક્તિગત ખર્ચ'))
        db.commit()
    return salary_month


if __name__ == '__main__':
    with TemporaryDirectory(prefix='prince-masala-demo-') as directory:
        demo = create_app({'DATABASE':str(Path(directory)/'demo.sqlite3'),'SECRET_KEY':'disposable-demo-only'})
        month = prepare_demo(demo)
        print(f'Disposable demonstration data. Salary example month: {month}')
        demo.run(host='127.0.0.1',port=5002,debug=False)
