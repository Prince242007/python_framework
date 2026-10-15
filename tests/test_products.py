"""Catalogue flows use an isolated database; the real catalogue stays untouched."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app import create_app
from database import get_db


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-key", "DATABASE": str(Path(self.temp.name) / "test.db")})
        self.client = self.app.test_client()
        self.client.get("/items/new")
        with self.client.session_transaction() as session:
            self.token = session["csrf_token"]

    def post(self, path, **data):
        return self.client.post(path, data={"csrf_token": self.token, **data})

    def test_bilingual_search_pagination_and_literal_query(self):
        for query, expected in [("KHAJUR", "ખજૂર ઠળિયા વાળો"), ("ખજૂર", "ખજૂર ઠળિયા વાળો")]:
            response = self.client.get("/items", query_string={"q": query})
            self.assertEqual(response.status_code, 200)
            self.assertIn(expected, response.get_data(as_text=True))
        self.assertIn("#31", self.client.get("/items?page=2").get_data(as_text=True))
        self.assertNotIn("#1</span>", self.client.get("/items?page=2").get_data(as_text=True))
        self.assertIn("વસ્તુ મળી નથી.", self.client.get("/items?q=%25").get_data(as_text=True))

    def test_add_and_edit_exact_price_with_gujarati_digits(self):
        response = self.post("/items/new", gujarati_name="ટેસ્ટ વસ્તુ", search_name="test item", price="૧૨૩.૪૫")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            item = get_db().execute("SELECT * FROM items WHERE search_name='test item'").fetchone()
            self.assertEqual(item['price_paise'], 12345)
            item_id = item['id']
        response = self.post(f"/items/{item_id}/edit", gujarati_name="નવી વસ્તુ", search_name="new item", price="50.01")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            row = get_db().execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            self.assertEqual(row['gujarati_name'], 'નવી વસ્તુ')
            self.assertEqual(row['price_paise'], 5001)

    def test_invalid_prices_and_names_do_not_change_data(self):
        for price in ["0", "-1", "NaN", "Infinity", "1.234", "1e3", "99999999999999"]:
            with self.subTest(price=price):
                response = self.post("/items/new", gujarati_name="ટેસ્ટ", search_name="test", price=price)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.post("/items/new", gujarati_name=" ", search_name="test", price="10").status_code, 422)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM items").fetchone()[0], 277)

    def test_csrf_required_and_unicode_token_is_rejected(self):
        for token in ["", "wrong", "ગુજરાતી"]:
            response = self.client.post("/items/1/delete", data={"csrf_token": token})
            self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertIsNotNone(get_db().execute("SELECT * FROM items WHERE id=1").fetchone())

    def test_delete_requires_post_and_missing_item_returns_404(self):
        self.assertEqual(self.client.get("/items/1/delete").status_code, 200)
        with self.app.app_context():
            self.assertIsNotNone(get_db().execute("SELECT * FROM items WHERE id=1").fetchone())
        self.assertEqual(self.post("/items/1/delete").status_code, 302)
        self.assertEqual(self.client.get("/items/1/edit").status_code, 404)
        self.assertEqual(self.client.get("/items/99999/delete").status_code, 404)

    def test_search_output_is_escaped(self):
        html = self.client.get("/items", query_string={"q": '<script>alert(1)</script>'}).get_data(as_text=True)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_dashboard_totals_only_include_today(self):
        today = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        with self.app.app_context():
            db = get_db()
            db.executemany("INSERT INTO bills (bill_number, customer_name, bill_date, total_paise) VALUES (?, ?, ?, ?)", [
                ('today-1', 'Test', today, 10001), ('today-2', 'Test', today, 24999),
                ('old', 'Test', '2000-01-01', 999999),
            ])
            db.commit()
        for _ in range(2):
            html = self.client.get("/").get_data(as_text=True)
            self.assertIn('₹350.00', html)
            self.assertIn('<strong>2</strong>', html)


if __name__ == '__main__':
    unittest.main()
