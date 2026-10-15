"""SQLite connections and a non-destructive, one-time catalogue import."""

import json
import sqlite3
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext

PROJECT_DIR = Path(__file__).resolve().parent


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=5)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create schema and seed once; never reset existing business data."""
    db = get_db()
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > 4:
        raise RuntimeError("Database is newer than this application supports.")
    if version == 0:
        db.executescript((PROJECT_DIR / "schema.sql").read_text(encoding="utf-8"))
    if version < 2:
        db.executescript((PROJECT_DIR / "migration_2.sql").read_text(encoding="utf-8"))
    if version < 3:
        db.executescript((PROJECT_DIR / "migration_3.sql").read_text(encoding="utf-8"))
    if version < 4:
        db.executescript((PROJECT_DIR / "migration_4.sql").read_text(encoding="utf-8"))

    # The lock and marker make imports safe across repeated starts/processes.
    with db:
        db.execute("BEGIN IMMEDIATE")
        seeded = db.execute(
            "SELECT value FROM app_metadata WHERE key = ?", ("catalogue_import_v1",)
        ).fetchone()
        if seeded is None:
            products = json.loads(
                (PROJECT_DIR / "data" / "initial_items.json").read_text(encoding="utf-8")
            )
            if db.execute("SELECT COUNT(*) FROM items").fetchone()[0]:
                raise RuntimeError("Catalogue already contains data without an import marker; automatic import stopped.")
            db.executemany(
                "INSERT INTO items (id, gujarati_name, search_name, price_paise) "
                "VALUES (:id, :gujarati_name, :search_name, :price_paise)",
                products,
            )
            db.execute(
                "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
                ("catalogue_import_v1", str(len(products))),
            )


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create missing tables and import initial products without clearing data."""
    init_db()
    count = get_db().execute("SELECT COUNT(*) FROM items").fetchone()[0]
    click.echo(f"Database ready. {count} products available.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    with app.app_context():
        init_db()
