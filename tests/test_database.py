"""Run with: python -m unittest discover -s tests -v"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from database import PROJECT_DIR, get_db, init_db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {"TESTING": True, "DATABASE": str(Path(self.temp.name) / "test.sqlite3")}
        self.app = create_app(self.config)

    def test_import_matches_all_original_products(self):
        expected = json.loads((PROJECT_DIR / "data/initial_items.json").read_text())
        with self.app.app_context():
            rows = get_db().execute("SELECT * FROM items ORDER BY id").fetchall()
            self.assertEqual(len(rows), 277)
            self.assertEqual([dict(row) for row in rows], expected)
            self.assertEqual(get_db().execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_restart_preserves_edits_deletions_and_does_not_duplicate(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE items SET price_paise = 12345 WHERE id = 1")
            db.execute("DELETE FROM items WHERE id = 2")
            db.commit()
            init_db()
        restarted = create_app(self.config)
        with restarted.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM items").fetchone()[0], 276)
            self.assertEqual(db.execute("SELECT price_paise FROM items WHERE id=1").fetchone()[0], 12345)
            self.assertIsNone(db.execute("SELECT id FROM items WHERE id=2").fetchone())
        self.assertIn("276".encode(), restarted.test_client().get("/").data)

    def test_empty_catalogue_is_not_reseeded_after_initial_import(self):
        with self.app.app_context():
            db = get_db()
            db.execute("DELETE FROM items")
            db.commit()
            init_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM items").fetchone()[0], 0)

    def test_validation_and_daily_hours_uniqueness(self):
        with self.app.app_context():
            db = get_db()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE items SET price_paise = -100 WHERE id = 1")
            db.execute("INSERT INTO workers (name, hourly_rate_paise) VALUES ('Worker', 5000)")
            sql = "INSERT INTO worker_hours (worker_id, date, hours, hourly_rate_paise) VALUES (?, ?, ?, ?)"
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(sql, (999, '2026-10-15', 8, 5000))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(sql, (1, '2026-10-15', 25, 5000))
            db.execute(sql, (1, '2026-10-15', 8, 5000))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(sql, (1, '2026-10-15', 5, 5000))

    def test_catalogue_deletion_keeps_original_bill_name_and_rate(self):
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT INTO bills (bill_number, customer_name, bill_date, total_paise) VALUES ('PM-1', 'Customer', '2026-10-15', 12000)")
            db.execute("INSERT INTO bill_items (bill_id, item_id, gujarati_name, search_name, quantity, price_paise) VALUES (1, 1, 'ખજૂર ઠળિયા વાળો', 'khajur thaliya valo', 2, 6000)")
            db.execute("DELETE FROM items WHERE id = 1")
            row = db.execute("SELECT * FROM bill_items").fetchone()
            self.assertIsNone(row['item_id'])
            self.assertEqual(row['gujarati_name'], 'ખજૂર ઠળિયા વાળો')
            self.assertEqual(row['price_paise'], 6000)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM bills WHERE id = 1")

    def test_init_command_is_repeatable(self):
        runner = self.app.test_cli_runner()
        for _ in range(2):
            result = runner.invoke(args=["init-db"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("277 products", result.output)


if __name__ == "__main__":
    unittest.main()
