from dotenv import load_dotenv
load_dotenv()
import json
import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import inspect, text


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

    app.config.setdefault("RESEND_API_KEY", os.environ.get("RESEND_API_KEY"))
    app.config.setdefault("RESEND_FROM_EMAIL", os.environ.get("RESEND_FROM_EMAIL"))
    app.config.setdefault("RESEND_FROM_NAME", os.environ.get("RESEND_FROM_NAME", "TrackYourSheets"))
    app.config.setdefault("RESEND_REPLY_TO", os.environ.get("RESEND_REPLY_TO"))
    app.config.setdefault("RESEND_ALERT_RECIPIENTS", os.environ.get("RESEND_ALERT_RECIPIENTS"))
    app.config.setdefault(
        "RESEND_NOTIFICATION_EMAILS",
        os.environ.get("RESEND_NOTIFICATION_EMAILS"),
    )
    app.config.setdefault(
        "RESEND_SIGNUP_ALERT_EMAILS",
        os.environ.get("RESEND_SIGNUP_ALERT_EMAILS"),
    )

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from . import models  # noqa: F401

    with app.app_context():
        db.create_all()
        _ensure_schema_extensions()
        _ensure_master_admin()
        _seed_default_categories()
    from .auth import auth_bp
    from .main import main_bp
    from .admin import admin_bp
    from .imports import imports_bp
    from .reports import reports_bp
    from .stripe_integration import init_stripe

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(imports_bp, url_prefix="/imports")
    app.register_blueprint(reports_bp, url_prefix="/reports")

    init_stripe(app)

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
                price_per_user=79,
                max_users=5,
                max_carriers=5,
                max_rows_per_month=15000,
                includes_quickbooks=False,
                includes_producer_portal=True,
                includes_api=False,
            )
            growth = SubscriptionPlan(
                name="Growth",
                tier=2,
                price_per_user=129,
                max_users=25,
                max_carriers=25,
                max_rows_per_month=100000,
                includes_quickbooks=True,
                includes_producer_portal=True,
                includes_api=False,
            )
            scale = SubscriptionPlan(
                name="Scale",
                tier=3,
                price_per_user=189,
                max_users=250,
                max_carriers=999,
                max_rows_per_month=500000,
                includes_quickbooks=True,
                includes_producer_portal=True,
                includes_api=True,
            )
            db.session.add_all([starter, growth, scale])
            db.session.commit()
            print("Seeded subscription plans.")
        print("Database ready.")

    return app


def _ensure_schema_extensions() -> None:
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    if "users" in existing_tables:
        columns = {col["name"] for col in inspector.get_columns("users")}
        migrations = []
        if "notification_preferences" not in columns:
            migrations.append(
                "ALTER TABLE users ADD COLUMN notification_preferences TEXT"
            )
        if "two_factor_enabled" not in columns:
            migrations.append(
                "ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN NOT NULL DEFAULT 1"
            )
        if "two_factor_secret" not in columns:
            migrations.append(
                "ALTER TABLE users ADD COLUMN two_factor_secret VARCHAR(255)"
            )
        if "two_factor_expires_at" not in columns:
            migrations.append(
                "ALTER TABLE users ADD COLUMN two_factor_expires_at DATETIME"
            )

        if migrations:
            with db.engine.begin() as conn:
                for statement in migrations:
                    conn.execute(text(statement))

        if "notification_preferences" not in columns:
            from .models import DEFAULT_NOTIFICATION_PREFERENCES

            default_json = json.dumps(DEFAULT_NOTIFICATION_PREFERENCES)
            with db.engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE users SET notification_preferences = :default WHERE notification_preferences IS NULL"
                    ),
                    {"default": default_json},
                )

        if "two_factor_enabled" not in columns:
            with db.engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE users SET two_factor_enabled = 1 WHERE two_factor_enabled IS NULL"
                    )
                )

    if "api_keys" in existing_tables:
        columns = {col["name"] for col in inspector.get_columns("api_keys")}
        migrations = []
        if "token_prefix" not in columns:
            migrations.append("ALTER TABLE api_keys ADD COLUMN token_prefix VARCHAR(16)")
        if "token_last4" not in columns:
            migrations.append("ALTER TABLE api_keys ADD COLUMN token_last4 VARCHAR(4)")
        if "revoked_at" not in columns:
            migrations.append("ALTER TABLE api_keys ADD COLUMN revoked_at DATETIME")
        if migrations:
            with db.engine.begin() as conn:
                for statement in migrations:
                    conn.execute(text(statement))

    if "commission_txns" in existing_tables:
        columns = {col["name"] for col in inspector.get_columns("commission_txns")}
        migrations = []
        if "manual_amount" not in columns:
            migrations.append("ALTER TABLE commission_txns ADD COLUMN manual_amount NUMERIC(12,2)")
        if "manual_split_pct" not in columns:
            migrations.append("ALTER TABLE commission_txns ADD COLUMN manual_split_pct NUMERIC(5,2)")
        if "override_source" not in columns:
            migrations.append("ALTER TABLE commission_txns ADD COLUMN override_source VARCHAR(32)")
        if "override_applied_at" not in columns:
            migrations.append("ALTER TABLE commission_txns ADD COLUMN override_applied_at DATETIME")
        if "override_applied_by" not in columns:
            migrations.append("ALTER TABLE commission_txns ADD COLUMN override_applied_by INTEGER")
        if migrations:
            with db.engine.begin() as conn:
                for statement in migrations:
                    conn.execute(text(statement))


def _seed_default_categories() -> None:
    from .models import CategoryTag, Organization

    default_lines = ["Auto", "Home", "Renters", "Life"]
    default_statuses = ["Raw", "Existing", "Renewal"]

    for org in Organization.query.all():
        for name in default_lines:
            _get_or_create_category(org.id, name, "line")
        for name in default_statuses:
            _get_or_create_category(org.id, name, "status")


def _get_or_create_category(org_id: int, name: str, kind: str) -> None:
    from .models import CategoryTag

    exists = CategoryTag.query.filter_by(
        org_id=org_id, name=name, kind=kind
    ).first()
    if exists:
        return
    tag = CategoryTag(org_id=org_id, name=name, kind=kind, is_default=True)
    db.session.add(tag)
    db.session.commit()


def _ensure_master_admin() -> None:
    """Create a fallback master admin user if one does not already exist."""

    from .models import Organization, SubscriptionPlan, User

    master_email = os.environ.get("MASTER_ADMIN_EMAIL", "insurance@audimi.co.site")
    master_password = os.environ.get("MASTER_ADMIN_PASSWORD", "Tofu")
    master_org_name = os.environ.get("MASTER_ADMIN_ORG_NAME", "Master Admin")

    if not master_email or not master_password:
        return

    existing_user = User.query.filter_by(email=master_email).first()
    if existing_user:
        return

    master_org = Organization.query.filter_by(name=master_org_name).first()
    if not master_org:
        plan = SubscriptionPlan.query.order_by(SubscriptionPlan.tier.asc()).first()
        master_org = Organization(name=master_org_name, plan_id=plan.id if plan else None)
        db.session.add(master_org)
        db.session.flush()
    elif master_org.plan_id is None:
        plan = SubscriptionPlan.query.order_by(SubscriptionPlan.tier.asc()).first()
        if plan:
            master_org.plan_id = plan.id
            db.session.add(master_org)

    user = User(email=master_email, role="owner", org_id=master_org.id)
    user.set_password(master_password)
    db.session.add(user)
    db.session.commit()
