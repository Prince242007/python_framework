"""Product catalogue pages and validation."""

from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from database import get_db
from money import parse_price

bp = Blueprint("products", __name__, url_prefix="/items")


def find_item(item_id):
    item = get_db().execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        abort(404)
    return item


@bp.get("")
def index():
    query = request.args.get("q", "").strip()[:150]
    page = max(1, request.args.get("page", 1, type=int))
    where = "WHERE instr(lower(gujarati_name), ?) > 0 OR instr(lower(search_name), ?) > 0"
    args = (query.lower(), query.lower())
    db = get_db()
    count = db.execute(f"SELECT COUNT(*) FROM items {where}", args).fetchone()[0]
    pages = max(1, (count + 29) // 30)
    page = min(page, pages)
    items = db.execute(
        f"SELECT * FROM items {where} ORDER BY id LIMIT 30 OFFSET ?",
        (*args, (page - 1) * 30),
    ).fetchall()
    return render_template("items.html", items=items, query=query, count=count, page=page, pages=pages)


def item_form(item=None):
    values = {
        "gujarati_name": item["gujarati_name"] if item else "",
        "search_name": item["search_name"] if item else "",
        "price": f"{Decimal(item['price_paise']) / 100:.2f}" if item else "",
    }
    errors = {}
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in values}
        for key in ("gujarati_name", "search_name"):
            if not values[key] or len(values[key]) > 150:
                errors[key] = "નામ ૧ થી ૧૫૦ અક્ષરોમાં દાખલ કરો."
        price_paise = parse_price(values["price"])
        if price_paise is None:
            errors["price"] = "યોગ્ય ભાવ દાખલ કરો (₹૦.૦૧ થી ₹૯૯,૯૯,૯૯૯.૯૯; વધુમાં વધુ બે દશાંશ)."
        if not errors:
            db = get_db()
            with db:
                if item:
                    db.execute(
                        "UPDATE items SET gujarati_name=?, search_name=?, price_paise=? WHERE id=?",
                        (values["gujarati_name"], values["search_name"], price_paise, item["id"]),
                    )
                else:
                    db.execute(
                        "INSERT INTO items (gujarati_name, search_name, price_paise) VALUES (?, ?, ?)",
                        (values["gujarati_name"], values["search_name"], price_paise),
                    )
            flash("વસ્તુમાં ફેરફાર સાચવ્યા." if item else "નવી વસ્તુ ઉમેરાઈ ગઈ.")
            return redirect(url_for("products.index"))
    return render_template("item_form.html", item=item, values=values, errors=errors), 422 if errors else 200


@bp.route("/new", methods=["GET", "POST"])
def add():
    return item_form()


@bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
def edit(item_id):
    return item_form(find_item(item_id))


@bp.route("/<int:item_id>/delete", methods=["GET", "POST"])
def delete(item_id):
    item = find_item(item_id)
    if request.method == "POST":
        db = get_db()
        with db:
            db.execute("DELETE FROM items WHERE id = ?", (item_id,))
        flash("વસ્તુ કાઢી નાખી. અગાઉના બિલની વિગતો સાચવેલી રહેશે.")
        return redirect(url_for("products.index"))
    return render_template("item_delete.html", item=item)
