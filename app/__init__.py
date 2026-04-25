import os
import secrets
from flask import Flask
from .models import db


def create_app():
    app = Flask(__name__, static_folder="../static", static_url_path="/static")

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///spielzeit.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["APP_PASSWORD"] = os.environ.get("APP_PASSWORD", "changeme")

    db.init_app(app)

    with app.app_context():
        db.create_all()

    from .routes.pages import pages_bp
    from .routes.api import api_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
