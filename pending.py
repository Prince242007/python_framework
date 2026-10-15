"""Outstanding balances with atomic payment recording and duplicate protection."""

from datetime import date
from decimal import Decimal
import secrets

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from itsdangerous import BadData, URLSafeSerializer

from billing import current_day
from database import get_db
from money import parse_price

bp = Blueprint("pending", __name__, url_prefix="/pending")
LEDGER = """
    SELECT p.*, COALESCE(pay.paid_paise, 0) AS paid_paise,
           p.amount_paise - COALESCE(pay.paid_paise, 0) AS balance_paise,
           b.bill_number
    FROM pending_bills p
    LEFT JOIN (SELECT pending_bill_id, SUM(amount_paise) AS paid_paise
               FROM pending_payments GROUP BY pending_bill_id) pay
      ON pay.pending_bill_id = p.id
    LEFT JOIN bills b ON b.id = p.bill_id
"""


def get_pending(pending_id):
    entry = get_db().execute(LEDGER + " WHERE p.id=?", (pending_id,)).fetchone()
    if entry is None:
        abort(404)
    return entry


def valid_date(text):
    try:
        return date.fromisoformat(text).isoformat() == text
    except ValueError:
        return False


def serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="pending-actions")


def action_token(action):
    return serializer().dumps({"action": action, "nonce": secrets.token_hex(16)})


def read_token(value, action):
    try:
        data = serializer().loads(value) if len(value) < 300 else None
        if not isinstance(data, dict) or data.get("action") != action or not isinstance(data.get("nonce"), str):
            return None
        return data["nonce"]
    except BadData:
        return None


@bp.get("")
def index():
    query = request.args.get("q", "").strip()[:150]
    status = request.args.get("status", "open")
    if status not in ("open", "paid", "all"):
        status = "open"
    page = max(1, request.args.get("page", 1, type=int))
    where = " WHERE (instr(lower(customer_name), ?) > 0 OR instr(lower(COALESCE(bill_number, '')), ?) > 0)"
    if status == "open":
        where += " AND balance_paise > 0"
    elif status == "paid":
        where += " AND balance_paise = 0"
    db = get_db()
    base = f"SELECT * FROM ({LEDGER}) {where}"
    args = (query.lower(), query.lower())
    count = db.execute(f"SELECT COUNT(*) FROM ({base})", args).fetchone()[0]
    pages = max(1, (count + 29) // 30)
    page = min(page, pages)
    entries = db.execute(base + " ORDER BY date ASC, id ASC LIMIT 30 OFFSET ?", (*args, (page - 1) * 30)).fetchall()
    total = db.execute(f"SELECT COALESCE(SUM(balance_paise), 0) FROM ({LEDGER}) WHERE balance_paise > 0").fetchone()[0]
    return render_template("pending_index.html", entries=entries, query=query, status=status, count=count, pages=pages, page=page, total=total)


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<int:pending_id>/edit", methods=["GET", "POST"])
def form(pending_id=None):
    entry = get_pending(pending_id) if pending_id else None
    if entry and entry["bill_id"]:
        flash("આ વિગતો સાચવેલા બિલ સાથે જોડાયેલી છે અને બદલી શકાતી નથી.")
        return redirect(url_for("pending.detail", pending_id=pending_id))
    values = {"customer_name": entry["customer_name"] if entry else "", "date": entry["date"] if entry else current_day(), "amount": f"{Decimal(entry['amount_paise']) / 100:.2f}" if entry else ""}
    form_token = action_token("create") if not entry else ""
    errors = []
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in values}
        form_token = request.form.get("form_token", "")
        token = read_token(form_token, "create") if not entry else None
        if not entry and not token:
            errors.append("પાનું ફરી ખોલીને પ્રયત્ન કરો.")
        if not values["customer_name"] or len(values["customer_name"]) > 150:
            errors.append("ગ્રાહકનું નામ ૧ થી ૧૫૦ અક્ષરોમાં દાખલ કરો.")
        if not valid_date(values["date"]):
            errors.append("યોગ્ય તારીખ પસંદ કરો.")
        amount = parse_price(values["amount"])
        if amount is None:
            errors.append("યોગ્ય બાકી રકમ દાખલ કરો; વધુમાં વધુ બે દશાંશ.")
        if not errors:
            db = get_db()
            with db:
                db.execute("BEGIN IMMEDIATE")
                if entry:
                    entry = get_pending(pending_id)
                    first_payment = db.execute("SELECT MIN(date) FROM pending_payments WHERE pending_bill_id=?", (pending_id,)).fetchone()[0]
                    if amount < entry["paid_paise"]:
                        errors.append("કુલ રકમ મળેલી ચુકવણી કરતાં ઓછી હોઈ શકે નહીં.")
                    elif first_payment and values["date"] > first_payment:
                        errors.append("બિલની તારીખ પ્રથમ ચુકવણી પછીની હોઈ શકે નહીં.")
                    else:
                        db.execute("UPDATE pending_bills SET customer_name=?, date=?, amount_paise=? WHERE id=?", (values["customer_name"], values["date"], amount, pending_id))
                else:
                    duplicate = db.execute("SELECT pending_bill_id FROM pending_actions WHERE token=?", (token,)).fetchone()
                    if duplicate:
                        return redirect(url_for("pending.detail", pending_id=duplicate[0]))
                    cursor = db.execute("INSERT INTO pending_bills (customer_name, date, amount_paise) VALUES (?, ?, ?)", (values["customer_name"], values["date"], amount))
                    pending_id = cursor.lastrowid
                    db.execute("INSERT INTO pending_actions (token, action, pending_bill_id) VALUES (?, 'create', ?)", (token, pending_id))
            if not errors:
                flash("બાકી બિલની વિગતો સાચવી.")
                return redirect(url_for("pending.detail", pending_id=pending_id))
    return render_template("pending_form.html", entry=entry, values=values, errors=errors, form_token=form_token), 422 if errors else 200


@bp.get("/<int:pending_id>")
def detail(pending_id):
    return detail_page(pending_id)


def detail_page(pending_id, errors=None, values=None, form_token=None, status=200):
    payments = get_db().execute("SELECT * FROM pending_payments WHERE pending_bill_id=? ORDER BY date DESC, id DESC", (pending_id,)).fetchall()
    return render_template("pending_detail.html", entry=get_pending(pending_id), payments=payments, errors=errors or [], values=values or {"date": current_day(), "amount": ""}, form_token=form_token or action_token(f"pay:{pending_id}")), status


@bp.post("/<int:pending_id>/payments")
def pay(pending_id):
    entry = get_pending(pending_id)
    values = {key: request.form.get(key, "").strip() for key in ("date", "amount")}
    form_token = request.form.get("form_token", "")
    token = read_token(form_token, f"pay:{pending_id}")
    amount = parse_price(values["amount"])
    errors = []
    if not token:
        errors.append("પાનું ફરી ખોલીને પ્રયત્ન કરો.")
    if amount is None:
        errors.append("યોગ્ય ચુકવણીની રકમ દાખલ કરો.")
    if not valid_date(values["date"]) or values["date"] < entry["date"] or values["date"] > current_day():
        errors.append("ચુકવણીની તારીખ બિલની તારીખથી આજની તારીખ વચ્ચે હોવી જોઈએ.")
    if not errors:
        db = get_db()
        with db:
            db.execute("BEGIN IMMEDIATE")
            duplicate = db.execute("SELECT pending_bill_id FROM pending_actions WHERE token=?", (token,)).fetchone()
            if duplicate:
                return redirect(url_for("pending.detail", pending_id=duplicate[0]))
            entry = get_pending(pending_id)
            if amount > entry["balance_paise"]:
                errors.append("ચુકવણી બાકી રકમ કરતાં વધારે હોઈ શકે નહીં.")
            else:
                cursor = db.execute("INSERT INTO pending_payments (pending_bill_id, date, amount_paise) VALUES (?, ?, ?)", (pending_id, values["date"], amount))
                db.execute("INSERT INTO pending_actions (token, action, pending_bill_id, payment_id) VALUES (?, 'pay', ?, ?)", (token, pending_id, cursor.lastrowid))
        if not errors:
            flash("ચુકવણી સાચવી. બાકી રકમ અપડેટ થઈ ગઈ.")
            return redirect(url_for("pending.detail", pending_id=pending_id))
    return detail_page(pending_id, errors, values, form_token, 422)


@bp.post("/from-bill/<int:bill_id>")
def from_bill(bill_id):
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        bill = db.execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()
        if bill is None:
            abort(404)
        entry = db.execute("SELECT id FROM pending_bills WHERE bill_id=?", (bill_id,)).fetchone()
        if entry:
            pending_id = entry[0]
        else:
            pending_id = db.execute("INSERT INTO pending_bills (bill_id, date, customer_name, amount_paise) VALUES (?, ?, ?, ?)", (bill_id, bill["bill_date"], bill["customer_name"], bill["total_paise"])).lastrowid
    flash("આ બિલ બાકી બિલની યાદીમાં છે.")
    return redirect(url_for("pending.detail", pending_id=pending_id))


@bp.route("/<int:pending_id>/delete", methods=["GET", "POST"])
def delete(pending_id):
    entry = get_pending(pending_id)
    if request.method == "POST":
        db = get_db()
        with db:
            db.execute("BEGIN IMMEDIATE")
            entry = get_pending(pending_id)
            if entry["paid_paise"]:
                return detail_page(pending_id, ["ચુકવણીનો ઇતિહાસ ધરાવતું બિલ કાઢી શકાતું નથી."], status=409)
            db.execute("DELETE FROM pending_bills WHERE id=?", (pending_id,))
        flash("બાકી બિલની નોંધ કાઢી. મૂળ સાચવેલું બિલ બદલાયું નથી.")
        return redirect(url_for("pending.index"))
    return render_template("pending_delete.html", entry=entry)
