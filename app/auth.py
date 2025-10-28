from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from . import db
from .models import Organization, SubscriptionPlan, Subscription, User
from .nylas_email import send_signup_alert, send_signup_welcome


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.tier.asc()).all()

    if request.method == "POST":
        org_name = request.form.get("org_name")
        email = request.form.get("email")
        password = request.form.get("password")
        plan_id = request.form.get("plan_id")

        if not all([org_name, email, password, plan_id]):
            flash("All fields are required.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
        else:
            try:
                selected_plan_id = int(plan_id)
            except (TypeError, ValueError):
                flash("Select a valid plan.", "danger")
                return render_template("signup.html", plans=plans)

            plan = SubscriptionPlan.query.filter_by(id=selected_plan_id).first()
            if not plan:
                flash("Selected plan is no longer available.", "danger")
            else:
                trial_end = datetime.utcnow() + timedelta(days=15)
                org = Organization(
                    name=org_name,
                    plan_id=plan.id,
                    trial_ends_at=trial_end,
                )
                user = User(email=email, role="owner", organization=org)
                user.set_password(password)
                subscription = Subscription(
                    organization=org,
                    plan=plan.name,
                    status="trialing",
                    trial_end=trial_end,
                )
                db.session.add(org)
                db.session.add(user)
                db.session.add(subscription)
                db.session.commit()
                send_signup_welcome(user, org)
                send_signup_alert(user, org)
                login_user(user)
                flash("Welcome to TrackYourSheets!", "success")
                return redirect(url_for("main.onboarding"))

    return render_template("signup.html", plans=plans)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash("Logged in successfully.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.dashboard"))
        flash("Invalid credentials.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
