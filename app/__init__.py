import os
import secrets
from flask import Flask
from .models import db


def create_app():
    app = Flask(__name__, static_folder="../static", static_url_path="/static")

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    db_url = os.environ.get("DATABASE_URL", "sqlite:///spielzeit.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["APP_PASSWORD"] = os.environ.get("APP_PASSWORD", "changeme")

    db.init_app(app)

    # Run schema migrations before SQLAlchemy touches the DB
    import sys, os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
    from migrate import run_migrations
    run_migrations()

    with app.app_context():
        db.create_all()

    from .routes.pages import pages_bp
    from .routes.api import api_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
