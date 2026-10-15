"""Worker attendance, advances, and monthly salary statements."""

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re
import secrets

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from itsdangerous import BadData, URLSafeSerializer

from billing import current_day
from database import get_db
from money import DIGITS, parse_price

bp = Blueprint("salary", __name__, url_prefix="/workers")


def find_worker(worker_id):
    worker = get_db().execute("SELECT * FROM workers WHERE id=?", (worker_id,)).fetchone()
    if worker is None:
        abort(404)
    return worker


def month_value(value):
    value = value or current_day()[:7]
    try:
        first = date.fromisoformat(value + "-01")
        if len(value) != 7 or first.strftime("%Y-%m") != value:
            raise ValueError
    except ValueError:
        abort(400)
    return value


def valid_work_date(value):
    try:
        return date.fromisoformat(value).isoformat() == value and value <= current_day()
    except ValueError:
        return False


def parse_hours(value):
    text = value.strip().translate(DIGITS)
    if len(text) > 5 or not re.fullmatch(r"[0-9]{1,2}(?:\.[0-9]{1,2})?", text):
        return None
    hours = Decimal(text)
    return hours if 0 <= hours <= 24 else None


def earned(entry):
    return int((Decimal(str(entry["hours"])) * entry["hourly_rate_paise"]).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def monthly_summary(worker_id, month):
    entries = [dict(row) for row in get_db().execute("SELECT * FROM worker_hours WHERE worker_id=? AND substr(date,1,7)=? ORDER BY date", (worker_id, month))]
    for row in entries:
        row["earned_paise"] = earned(row)
    advances = get_db().execute("SELECT * FROM worker_advances WHERE worker_id=? AND substr(date,1,7)=? ORDER BY date, id", (worker_id, month)).fetchall()
    gross = sum(row["earned_paise"] for row in entries)
    advance = sum(row["amount_paise"] for row in advances)
    return {"entries": entries, "advances": advances, "hours": sum((Decimal(str(row["hours"])) for row in entries), Decimal(0)), "gross": gross, "advance": advance, "net": gross - advance, "payable": max(0, gross - advance), "excess": max(0, advance - gross)}


def serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="worker-actions")


def make_token(action):
    return serializer().dumps({"action": action, "nonce": secrets.token_hex(16)})


def read_token(value, action):
    try:
        data = serializer().loads(value) if len(value) < 300 else None
        if isinstance(data, dict) and data.get("action") == action and isinstance(data.get("nonce"), str):
            return data["nonce"]
    except BadData:
        pass
    return None


@bp.get("")
def index():
    month = month_value(request.args.get("month"))
    query = request.args.get("q", "").strip()[:150]
    workers = [dict(row) for row in get_db().execute("SELECT * FROM workers WHERE instr(lower(name), ?) > 0 ORDER BY id", (query.lower(),))]
    for worker in workers:
        worker["summary"] = monthly_summary(worker["id"], month)
    return render_template("workers.html", workers=workers, month=month, query=query)


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<int:worker_id>/edit", methods=["GET", "POST"])
def form(worker_id=None):
    worker = find_worker(worker_id) if worker_id else None
    values = {"name": worker["name"] if worker else "", "rate": f"{Decimal(worker['hourly_rate_paise']) / 100:.2f}" if worker else ""}
    form_token = make_token("worker") if not worker else ""
    errors = []
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in values}
        form_token = request.form.get("form_token", "")
        token = read_token(form_token, "worker") if not worker else None
        if not worker and not token:
            errors.append("પાનું ફરી ખોલીને પ્રયત્ન કરો.")
        if not values["name"] or len(values["name"]) > 150:
            errors.append("કર્મચારીનું નામ ૧ થી ૧૫૦ અક્ષરોમાં દાખલ કરો.")
        rate = parse_price(values["rate"])
        if rate is None:
            errors.append("યોગ્ય કલાક દીઠ દર દાખલ કરો.")
        if not errors:
            db = get_db()
            with db:
                db.execute("BEGIN IMMEDIATE")
                if worker:
                    db.execute("UPDATE workers SET name=?, hourly_rate_paise=? WHERE id=?", (values["name"], rate, worker_id))
                else:
                    previous = db.execute("SELECT worker_id FROM worker_actions WHERE token=?", (token,)).fetchone()
                    if previous:
                        return redirect(url_for("salary.detail", worker_id=previous[0]))
                    worker_id = db.execute("INSERT INTO workers (name, hourly_rate_paise) VALUES (?, ?)", (values["name"], rate)).lastrowid
                    db.execute("INSERT INTO worker_actions (token, action, worker_id) VALUES (?, 'worker', ?)", (token, worker_id))
            flash("કર્મચારીની વિગતો સાચવી. અગાઉના કામના દર બદલાયા નથી.")
            return redirect(url_for("salary.detail", worker_id=worker_id))
    return render_template("worker_form.html", worker=worker, values=values, errors=errors, form_token=form_token), 422 if errors else 200


@bp.get("/<int:worker_id>")
def detail(worker_id):
    month = month_value(request.args.get("month"))
    return render_template("worker_detail.html", worker=find_worker(worker_id), month=month, summary=monthly_summary(worker_id, month))


@bp.route("/<int:worker_id>/hours/new", methods=["GET", "POST"])
@bp.route("/<int:worker_id>/hours/<int:entry_id>/edit", methods=["GET", "POST"])
def hours(worker_id, entry_id=None):
    worker = find_worker(worker_id)
    db = get_db()
    entry = db.execute("SELECT * FROM worker_hours WHERE id=? AND worker_id=?", (entry_id, worker_id)).fetchone() if entry_id else None
    if entry_id and entry is None:
        abort(404)
    values = {"date": entry["date"] if entry else current_day(), "hours": str(entry["hours"]) if entry else ""}
    errors = []
    if request.method == "POST":
        values = {"date": entry["date"] if entry else request.form.get("date", "").strip(), "hours": request.form.get("hours", "").strip()}
        amount = parse_hours(values["hours"])
        if amount is None:
            errors.append("કલાક ૦ થી ૨૪ વચ્ચે દાખલ કરો; વધુમાં વધુ બે દશાંશ (૭.૫ એટલે ૭ કલાક ૩૦ મિનિટ).")
        if not valid_work_date(values["date"]):
            errors.append("આજની અથવા અગાઉની યોગ્ય તારીખ પસંદ કરો.")
        if not errors:
            with db:
                db.execute("BEGIN IMMEDIATE")
                worker = find_worker(worker_id)
                existing = db.execute("SELECT id FROM worker_hours WHERE worker_id=? AND date=?", (worker_id, values["date"])).fetchone()
                if entry:
                    # Correct hours while retaining the originally recorded rate.
                    db.execute("UPDATE worker_hours SET hours=? WHERE id=? AND worker_id=?", (float(amount), entry_id, worker_id))
                elif existing:
                    errors.append("આ તારીખના કલાક પહેલેથી નોંધાયેલા છે. કર્મચારીની વિગતોમાંથી તે નોંધ સુધારો.")
                else:
                    db.execute("INSERT INTO worker_hours (worker_id, date, hours, hourly_rate_paise) VALUES (?, ?, ?, ?)", (worker_id, values["date"], float(amount), worker["hourly_rate_paise"]))
            if not errors:
                flash("કામના કલાક સાચવ્યા.")
                return redirect(url_for("salary.detail", worker_id=worker_id, month=values["date"][:7]))
    return render_template("worker_hours.html", worker=worker, entry=entry, values=values, errors=errors, today=current_day()), 422 if errors else 200


@bp.route("/<int:worker_id>/advances/new", methods=["GET", "POST"])
def advance(worker_id):
    worker = find_worker(worker_id)
    values = {"date": current_day(), "reason": "", "amount": ""}
    form_token = make_token(f"advance:{worker_id}")
    errors = []
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in values}
        form_token = request.form.get("form_token", "")
        token = read_token(form_token, f"advance:{worker_id}")
        amount = parse_price(values["amount"])
        if not token:
            errors.append("પાનું ફરી ખોલીને પ્રયત્ન કરો.")
        if amount is None:
            errors.append("યોગ્ય એડવાન્સ રકમ દાખલ કરો.")
        if not valid_work_date(values["date"]):
            errors.append("આજની અથવા અગાઉની યોગ્ય તારીખ પસંદ કરો.")
        if not values["reason"] or len(values["reason"]) > 250:
            errors.append("એડવાન્સનું કારણ ૧ થી ૨૫૦ અક્ષરોમાં દાખલ કરો.")
        if not errors:
            db = get_db()
            with db:
                db.execute("BEGIN IMMEDIATE")
                previous = db.execute("SELECT worker_id FROM worker_actions WHERE token=?", (token,)).fetchone()
                if previous:
                    return redirect(url_for("salary.detail", worker_id=worker_id, month=values["date"][:7]))
                find_worker(worker_id)
                advance_id = db.execute("INSERT INTO worker_advances (worker_id, date, reason, amount_paise) VALUES (?, ?, ?, ?)", (worker_id, values["date"], values["reason"], amount)).lastrowid
                db.execute("INSERT INTO worker_actions (token, action, worker_id, advance_id) VALUES (?, 'advance', ?, ?)", (token, worker_id, advance_id))
            flash("એડવાન્સ સાચવ્યો.")
            return redirect(url_for("salary.detail", worker_id=worker_id, month=values["date"][:7]))
    return render_template("worker_advance.html", worker=worker, values=values, errors=errors, form_token=form_token, today=current_day()), 422 if errors else 200


@bp.route("/<int:worker_id>/advances/<int:advance_id>/delete", methods=["GET", "POST"])
def delete_advance(worker_id, advance_id):
    worker = find_worker(worker_id)
    db = get_db()
    advance = db.execute("SELECT * FROM worker_advances WHERE id=? AND worker_id=?", (advance_id, worker_id)).fetchone()
    if advance is None:
        abort(404)
    if request.method == "POST":
        with db:
            db.execute("DELETE FROM worker_advances WHERE id=? AND worker_id=?", (advance_id, worker_id))
        flash("એડવાન્સની નોંધ કાઢી. તે મહિનાની પગાર ગણતરી અપડેટ થઈ.")
        return redirect(url_for("salary.detail", worker_id=worker_id, month=advance["date"][:7]))
    return render_template("worker_delete.html", worker=worker, advance=advance, blocked=False)


@bp.route("/<int:worker_id>/delete", methods=["GET", "POST"])
def delete_worker(worker_id):
    worker = find_worker(worker_id)
    db = get_db()
    def has_records():
        return db.execute("SELECT EXISTS(SELECT 1 FROM worker_hours WHERE worker_id=?) OR EXISTS(SELECT 1 FROM worker_advances WHERE worker_id=?)", (worker_id, worker_id)).fetchone()[0]
    blocked = has_records()
    if request.method == "POST":
        with db:
            db.execute("BEGIN IMMEDIATE")
            blocked = has_records()
            if not blocked:
                db.execute("DELETE FROM workers WHERE id=?", (worker_id,))
        if not blocked:
            flash("કર્મચારીની નોંધ કાઢી.")
            return redirect(url_for("salary.index"))
    return render_template("worker_delete.html", worker=worker, advance=None, blocked=blocked), 409 if request.method == "POST" and blocked else 200


@bp.get("/<int:worker_id>/statement")
def statement(worker_id):
    month = month_value(request.args.get("month"))
    summary = monthly_summary(worker_id, month)
    by_day = {row["date"]: row for row in summary["entries"]}
    year, number = map(int, month.split("-"))
    days = [{"date": f"{month}-{day:02d}", "entry": by_day.get(f"{month}-{day:02d}")} for day in range(1, calendar.monthrange(year, number)[1] + 1)]
    return render_template("salary_statement.html", worker=find_worker(worker_id), month=month, summary=summary, days=days)
