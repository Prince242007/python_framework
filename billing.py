"""Save complete bills atomically; printing only reads saved records."""

from datetime import date, datetime
import json
import re
import secrets
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from itsdangerous import BadData, BadSignature, URLSafeSerializer

from database import get_db
from money import DIGITS, parse_price

bp = Blueprint("billing", __name__, url_prefix="/bills")


def token_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="bill-submission")


def current_day():
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")


@bp.route("/new", methods=["GET", "POST"])
def new():
    db = get_db()
    catalogue = [dict(row) for row in db.execute("SELECT * FROM items ORDER BY id")]
    values = {"customer_name": "", "bill_date": current_day()}
    form_token = token_serializer().dumps(secrets.token_hex(16))
    rows = []
    errors = []
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in values}
        form_token = request.form.get("form_token", "")
        try:
            token = token_serializer().loads(form_token) if len(form_token) < 200 else None
            if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
                raise BadSignature("Invalid bill token")
        except BadData:
            errors.append("બિલનું પાનું ફરી ખોલીને પ્રયત્ન કરો.")
            token = None
        # Handle a retry even if the catalogue has changed since the first save.
        if token:
            saved = db.execute("SELECT bill_id FROM bill_submissions WHERE token=?", (token,)).fetchone()
            if saved:
                return redirect(url_for("billing.detail", bill_id=saved["bill_id"]))
        if not values["customer_name"] or len(values["customer_name"]) > 150:
            errors.append("ગ્રાહકનું નામ ૧ થી ૧૫૦ અક્ષરોમાં દાખલ કરો.")
        try:
            parsed_date = date.fromisoformat(values["bill_date"])
            if parsed_date.isoformat() != values["bill_date"]:
                raise ValueError
        except ValueError:
            errors.append("યોગ્ય બિલ તારીખ પસંદ કરો.")
        try:
            raw = request.form.get("items_json", "[]")
            if len(raw) > 100000:
                raise ValueError
            rows = json.loads(raw)
            if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
                rows = []
                raise ValueError
            parsed_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError
                item_id = str(row.get("item_id", ""))
                quantity = str(row.get("quantity", "")).strip().translate(DIGITS)
                price_paise = parse_price(row.get("price", ""))
                if not re.fullmatch(r"[0-9]{1,10}", item_id) or not re.fullmatch(r"[0-9]{1,6}", quantity):
                    raise ValueError
                if not 1 <= int(quantity) <= 100000 or price_paise is None:
                    raise ValueError
                parsed_rows.append((int(item_id), int(quantity), price_paise))
        except (ValueError, TypeError):
            errors.append("બિલમાં ૧ થી ૨૦૦ વસ્તુઓ ઉમેરો. દરેકનો જથ્થો અને ભાવ યોગ્ય હોવા જોઈએ.")
        if not errors:
            # Serialize saves so bill numbering and duplicate protection are atomic.
            with db:
                db.execute("BEGIN IMMEDIATE")
                saved = db.execute("SELECT bill_id FROM bill_submissions WHERE token=?", (token,)).fetchone()
                if saved:
                    return redirect(url_for("billing.detail", bill_id=saved["bill_id"]))
                snapshots = []
                for item_id, quantity, price_paise in parsed_rows:
                    item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
                    if item is None:
                        errors.append("પસંદ કરેલી વસ્તુ હવે યાદીમાં નથી. તેને દૂર કરીને બીજી વસ્તુ પસંદ કરો.")
                        break
                    snapshots.append((item_id, item["gujarati_name"], item["search_name"], quantity, price_paise))
                if not errors:
                    total = sum(row[3] * row[4] for row in snapshots)
                    if total > 9999999999999:
                        errors.append("બિલની કુલ રકમ ખૂબ મોટી છે. જથ્થો અને ભાવ તપાસો.")
                if not errors:
                    next_id = db.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM bills").fetchone()[0]
                    bill_number = f"PM-{values['bill_date'].replace('-', '')}-{next_id:05d}"
                    cursor = db.execute(
                        "INSERT INTO bills (bill_number, customer_name, bill_date, total_paise) VALUES (?, ?, ?, ?)",
                        (bill_number, values["customer_name"], values["bill_date"], total),
                    )
                    bill_id = cursor.lastrowid
                    db.executemany(
                        "INSERT INTO bill_items (bill_id, item_id, gujarati_name, search_name, quantity, price_paise) VALUES (?, ?, ?, ?, ?, ?)",
                        [(bill_id, *row) for row in snapshots],
                    )
                    db.execute("INSERT INTO bill_submissions (token, bill_id) VALUES (?, ?)", (token, bill_id))
            if not errors:
                flash("બિલ સાચવાઈ ગયું. હવે પ્રિન્ટ કરો અથવા PDF તરીકે સાચવો.")
                return redirect(url_for("billing.detail", bill_id=bill_id))
    return render_template(
        "bill_new.html", catalogue=catalogue, values=values,
        initial_rows=rows, errors=errors, form_token=form_token,
    ), 422 if errors else 200


@bp.get("")
def history():
    query = request.args.get("q", "").strip()[:150]
    page = max(1, request.args.get("page", 1, type=int))
    args = (query.lower(), query.lower())
    where = "WHERE instr(lower(customer_name), ?) > 0 OR instr(lower(bill_number), ?) > 0"
    db = get_db()
    count = db.execute(f"SELECT COUNT(*) FROM bills {where}", args).fetchone()[0]
    pages = max(1, (count + 29) // 30)
    page = min(page, pages)
    bills = db.execute(f"SELECT * FROM bills {where} ORDER BY bill_date DESC, id DESC LIMIT 30 OFFSET ?", (*args, (page - 1) * 30)).fetchall()
    return render_template("bill_history.html", bills=bills, query=query, count=count, page=page, pages=pages)


@bp.get("/<int:bill_id>")
def detail(bill_id):
    bill = get_db().execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()
    if bill is None:
        abort(404)
    items = get_db().execute("SELECT *, quantity * price_paise AS amount_paise FROM bill_items WHERE bill_id=? ORDER BY id", (bill_id,)).fetchall()
    submission = get_db().execute("SELECT token FROM bill_submissions WHERE bill_id=?", (bill_id,)).fetchone()
    pending_entry = get_db().execute("SELECT id FROM pending_bills WHERE bill_id=?", (bill_id,)).fetchone()
    return render_template("bill_detail.html", bill=bill, items=items, pending_entry=pending_entry, submission_token=token_serializer().dumps(submission["token"]) if submission else "")
