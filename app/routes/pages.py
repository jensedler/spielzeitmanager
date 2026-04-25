from flask import Blueprint, render_template, redirect, url_for, request, session, current_app

pages_bp = Blueprint("pages", __name__)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("pages.login"))
        return f(*args, **kwargs)
    return decorated


@pages_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == current_app.config["APP_PASSWORD"]:
            session["authenticated"] = True
            return redirect(url_for("pages.index"))
        error = "Falsches Passwort"
    return render_template("login.html", error=error)


@pages_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("pages.login"))


@pages_bp.route("/")
@login_required
def index():
    return redirect(url_for("pages.games"))


@pages_bp.route("/players")
@login_required
def players():
    return render_template("players.html")


@pages_bp.route("/games")
@login_required
def games():
    return render_template("games.html")


@pages_bp.route("/games/<int:game_id>")
@login_required
def game(game_id):
    return render_template("game.html", game_id=game_id)


@pages_bp.route("/up")
def healthcheck():
    return "OK", 200
