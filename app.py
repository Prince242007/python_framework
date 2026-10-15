"""Prince Masala's Flask entry point."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import secrets
import hmac
from zoneinfo import ZoneInfo

from flask import Flask, abort, render_template, request, session

from database import get_db, init_app
from products import bp as products_bp
from billing import bp as billing_bp
from pending import bp as pending_bp
from salary import bp as salary_bp


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=str(Path(app.instance_path) / "prince_masala.sqlite3"),
    )
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get("SECRET_KEY"):
        secret_file = Path(app.instance_path) / "secret_key"
        try:
            with secret_file.open("x", encoding="utf-8") as stream:
                secret_file.chmod(0o600)
                stream.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config["SECRET_KEY"] = secret_file.read_text(encoding="utf-8")
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    init_app(app)
    app.register_blueprint(products_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(pending_bp)
    app.register_blueprint(salary_bp)

    @app.template_filter("money")
    def money(paise):
        return f"{Decimal(paise) / 100:,.2f}"

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def check_form_token():
        if request.method == "POST":
            expected = session.get("csrf_token", "")
            supplied = request.form.get("csrf_token", "")
            if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
                abort(400)

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", title="ફરી પ્રયત્ન કરો", message="પાનું ફરી ખોલીને વિગતો સાચવો."), 400

    @app.errorhandler(404)
    def not_found(error):
        return render_template("error.html", title="પાનું મળ્યું નથી", message="મુખ્ય પાનેથી ફરી શરૂ કરો."), 404

    @app.get("/")
    def home():
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        summary = get_db().execute(
            "SELECT COUNT(*) AS bill_count, COALESCE(SUM(total_paise), 0) AS total_paise "
            "FROM bills WHERE bill_date = ?", (now.strftime("%Y-%m-%d"),),
        ).fetchone()
        return render_template(
            "home.html",
            today=now.strftime("%d/%m/%Y"),
            product_count=get_db().execute("SELECT COUNT(*) FROM items").fetchone()[0],
            summary=summary,
            pending_total=get_db().execute("SELECT COALESCE(SUM(amount_paise), 0) - (SELECT COALESCE(SUM(amount_paise), 0) FROM pending_payments) FROM pending_bills").fetchone()[0],
        )

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
