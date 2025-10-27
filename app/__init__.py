import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev_secret"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL",
            "sqlite:///trackyoursheets.db",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=os.path.join(app.instance_path, "uploads"),
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from . import models  # noqa: F401
    from .auth import auth_bp
    from .main import main_bp
    from .admin import admin_bp
    from .imports import imports_bp
    from .reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(imports_bp, url_prefix="/imports")
    app.register_blueprint(reports_bp, url_prefix="/reports")

    login_manager.login_view = "auth.login"

    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from .models import SubscriptionPlan

        plans = SubscriptionPlan.query.order_by(SubscriptionPlan.tier.asc()).all()
        return {
            "available_plans": plans,
            "current_year": datetime.utcnow().year,
        }

    @app.cli.command("init-db")
    def init_db_command():
        """Initialise the database and seed default plans."""
        from .models import SubscriptionPlan

        db.create_all()

        if SubscriptionPlan.query.count() == 0:
            starter = SubscriptionPlan(
                name="Starter",
                tier=1,
                price_per_user=59,
                max_users=3,
                max_carriers=3,
                max_rows_per_month=5000,
                includes_quickbooks=False,
                includes_producer_portal=False,
                includes_api=False,
            )
            growth = SubscriptionPlan(
                name="Growth",
                tier=2,
                price_per_user=89,
                max_users=10,
                max_carriers=10,
                max_rows_per_month=25000,
                includes_quickbooks=True,
                includes_producer_portal=True,
                includes_api=False,
            )
            scale = SubscriptionPlan(
                name="Scale",
                tier=3,
                price_per_user=129,
                max_users=999,
                max_carriers=999,
                max_rows_per_month=999999,
                includes_quickbooks=True,
                includes_producer_portal=True,
                includes_api=True,
            )
            db.session.add_all([starter, growth, scale])
            db.session.commit()
            print("Seeded subscription plans.")
        print("Database ready.")

    return app
