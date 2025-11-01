from dotenv import load_dotenv
load_dotenv()
from datetime import datetime

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    current_app,
    session,
)
from flask_login import current_user, login_required, login_user, logout_user

from . import db
from .models import Organization, SubscriptionPlan, Subscription, User
from .resend_email import (
    send_login_notification,
    send_signup_alert,
    send_signup_welcome,
    send_two_factor_code_email,
)
from sqlalchemy import func
from .marketing import build_plan_details


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.tier.asc()).all()
    default_plan = plans[0] if plans else None
    plan_cards = build_plan_details(plans)
    plan_details_map = {detail["id"]: detail for detail in plan_cards}
    default_plan_detail = plan_details_map.get(default_plan.id) if default_plan else None

    if request.method == "POST":
        org_name = request.form.get("org_name")
        email = request.form.get("email")
        password = request.form.get("password")

        if not all([org_name, email, password]):
            flash("All fields are required.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
        elif not default_plan:
            flash("No plans are configured yet. Please contact support.", "danger")
        else:
            stripe_gateway = current_app.extensions.get("stripe_gateway")
            if not stripe_gateway or not getattr(stripe_gateway, "is_configured", False):
                flash("Stripe payments are not configured. Contact support for assistance.", "danger")
                return render_template(
                    "signup.html",
                    plans=plans,
                    default_plan=default_plan,
                    default_plan_detail=default_plan_detail,
                    plan_details=plan_cards,
                    plan_details_map=plan_details_map,
                )

            org = Organization(
                name=org_name,
                plan_id=default_plan.id,
                trial_ends_at=None,
            )
            user = User(email=email, role="owner", organization=org)
            user.set_password(password)
            subscription = Subscription(
                organization=org,
                plan=default_plan.name,
                status="incomplete",
            )
            db.session.add(org)
            db.session.add(user)
            db.session.add(subscription)

            try:
                db.session.flush()
            except Exception:
                db.session.rollback()
                flash("We couldn't create your workspace. Please try again.", "danger")
                return render_template(
                    "signup.html",
                    plans=plans,
                    default_plan=default_plan,
                    default_plan_detail=default_plan_detail,
                    plan_details=plan_cards,
                    plan_details_map=plan_details_map,
                )

            seat_quantity = 1
            success_url = url_for(
                "auth.signup_complete",
                _external=True,
            )
            success_url = f"{success_url}?session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = url_for("auth.signup_cancelled", _external=True)

            try:
                checkout_url = stripe_gateway.create_checkout_session(
                    organization=org,
                    plan=default_plan,
                    quantity=seat_quantity,
                    success_url=success_url,
                    cancel_url=cancel_url,
                    client_reference_id=str(user.id),
                    metadata={"flow": "signup"},
                    subscription_metadata={
                        "plan_id": str(default_plan.id),
                        "user_id": str(user.id),
                        "flow": "signup",
                    },
                )
            except Exception:
                current_app.logger.exception("Stripe checkout creation failed during signup")
                db.session.rollback()
                flash(
                    "We couldn't start Stripe checkout. Please verify your billing details and try again.",
                    "danger",
                )
                return render_template(
                    "signup.html",
                    plans=plans,
                    default_plan=default_plan,
                    default_plan_detail=default_plan_detail,
                    plan_details=plan_cards,
                    plan_details_map=plan_details_map,
                )

            db.session.commit()
            flash("Redirecting to secure checkout to activate your subscription.", "info")
            return redirect(checkout_url)

    return render_template(
        "signup.html",
        plans=plans,
        default_plan=default_plan,
        default_plan_detail=default_plan_detail,
        plan_details=plan_cards,
        plan_details_map=plan_details_map,
    )


@auth_bp.route("/signup/cancelled")
def signup_cancelled():
    flash(
        "Your Stripe checkout was cancelled. You can restart the signup anytime to activate your workspace.",
        "warning",
    )
    return redirect(url_for("auth.signup"))


@auth_bp.route("/signup/complete")
def signup_complete():
    session_id = request.args.get("session_id")
    if not session_id:
        flash("Checkout session missing. Please contact support.", "danger")
        return redirect(url_for("auth.login"))

    stripe_gateway = current_app.extensions.get("stripe_gateway")
    if not stripe_gateway or not getattr(stripe_gateway, "is_configured", False):
        flash("Stripe integration is not configured. Please contact support.", "danger")
        return redirect(url_for("auth.login"))

    try:
        session = stripe_gateway.retrieve_checkout_session(session_id)
    except Exception:
        current_app.logger.exception("Failed to retrieve Stripe checkout session")
        flash("We couldn't verify your payment. Please contact support.", "danger")
        return redirect(url_for("auth.login"))

    if getattr(session, "status", None) != "complete":
        flash("Checkout is not complete yet. Please finish payment in Stripe.", "warning")
        return redirect(url_for("auth.login"))

    user_id = getattr(session, "client_reference_id", None)
    if not user_id:
        flash("We couldn't locate your account. Please contact support.", "danger")
        return redirect(url_for("auth.login"))

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        flash("We couldn't locate your account. Please contact support.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.get(user_id_int)
    if not user:
        flash("We couldn't locate your account. Please contact support.", "danger")
        return redirect(url_for("auth.login"))

    org = user.organization
    if not org:
        flash("Your organization was not found. Please contact support.", "danger")
        return redirect(url_for("auth.login"))

    subscription_record = Subscription.query.filter_by(org_id=org.id).first()
    if not subscription_record:
        subscription_record = Subscription(org_id=org.id)
        db.session.add(subscription_record)

    stripe_subscription = getattr(session, "subscription", None)
    plan_id = None
    plan_name = None

    if stripe_subscription and getattr(stripe_subscription, "metadata", None):
        plan_id = stripe_subscription.metadata.get("plan_id") or stripe_subscription.metadata.get("plan")
        plan_name = stripe_subscription.metadata.get("plan")
    if not plan_id and getattr(session, "metadata", None):
        plan_id = session.metadata.get("plan_id") or session.metadata.get("plan")
        plan_name = plan_name or session.metadata.get("plan")

    resolved_plan = None
    if plan_id and str(plan_id).isdigit():
        resolved_plan = SubscriptionPlan.query.get(int(plan_id))
    if not resolved_plan and plan_name:
        resolved_plan = SubscriptionPlan.query.filter(func.lower(SubscriptionPlan.name) == plan_name.lower()).first()

    if resolved_plan:
        org.plan_id = resolved_plan.id
        plan_name = resolved_plan.name

    subscription_record.plan = plan_name or subscription_record.plan
    subscription_record.status = getattr(stripe_subscription, "status", None) or "active"
    subscription_record.stripe_sub_id = getattr(stripe_subscription, "id", None)

    trial_end_timestamp = getattr(stripe_subscription, "trial_end", None)
    if trial_end_timestamp:
        subscription_record.trial_end = datetime.utcfromtimestamp(trial_end_timestamp)
        org.trial_ends_at = subscription_record.trial_end
    else:
        subscription_record.trial_end = None
        org.trial_ends_at = None

    db.session.commit()

    send_signup_welcome(user, org)
    send_signup_alert(user, org)

    if user.two_factor_enabled:
        code = user.generate_two_factor_code()
        db.session.commit()
        send_two_factor_code_email(user.email, code, intent="signup")
        session["two_factor_user_id"] = user.id
        session["two_factor_intent"] = "signup"
        session["two_factor_after_signup"] = True
        flash(
            "Enter the verification code we emailed you to finish setting up your account.",
            "info",
        )
        return redirect(url_for("auth.two_factor"))

    login_user(user)
    user.last_login = datetime.utcnow()
    db.session.commit()
    if user.wants_notification("login"):
        send_login_notification(user.email, ip_address=request.remote_addr)
    flash("Welcome to TrackYourSheets! Your subscription is active.", "success")
    return redirect(url_for("main.onboarding"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if user.two_factor_enabled:
                code = user.generate_two_factor_code()
                db.session.commit()
                send_two_factor_code_email(user.email, code, intent="login")
                session["two_factor_user_id"] = user.id
                session["two_factor_intent"] = "login"
                session["two_factor_next"] = request.args.get("next")
                flash(
                    "Enter the verification code we emailed you to finish signing in.",
                    "info",
                )
                return redirect(url_for("auth.two_factor"))

            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            if user.wants_notification("login"):
                send_login_notification(user.email, ip_address=request.remote_addr)
            flash("Logged in successfully.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.dashboard"))
        flash("Invalid credentials.", "danger")

    return render_template("login.html")


@auth_bp.route("/two-factor", methods=["GET", "POST"])
def two_factor():
    user_id = session.get("two_factor_user_id")
    if not user_id:
        flash("Your verification session expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    user = User.query.get(user_id)
    if not user:
        session.pop("two_factor_user_id", None)
        flash("We couldn't find that account. Please sign in again.", "danger")
        return redirect(url_for("auth.login"))

    intent = session.get("two_factor_intent", "login")

    if request.method == "POST":
        code = request.form.get("code")
        if user.verify_two_factor_code(code):
            user.clear_two_factor_challenge()
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            next_page = session.pop("two_factor_next", None)
            is_signup = session.pop("two_factor_after_signup", False)
            session.pop("two_factor_user_id", None)
            session.pop("two_factor_intent", None)
            if user.wants_notification("login"):
                send_login_notification(user.email, ip_address=request.remote_addr)
            if is_signup:
                flash("Account verified! Welcome to TrackYourSheets.", "success")
                return redirect(url_for("main.onboarding"))
            flash("Logged in successfully.", "success")
            return redirect(next_page or url_for("main.dashboard"))

        flash("That security code was invalid or expired. Try again.", "danger")

    return render_template(
        "two_factor.html",
        email=user.email,
        intent=intent,
    )


@auth_bp.route("/two-factor/resend", methods=["POST"])
def resend_two_factor():
    user_id = session.get("two_factor_user_id")
    if not user_id:
        flash("Your verification session expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    user = User.query.get(user_id)
    if not user:
        session.pop("two_factor_user_id", None)
        flash("We couldn't find that account. Please sign in again.", "danger")
        return redirect(url_for("auth.login"))

    if not user.two_factor_enabled:
        session.pop("two_factor_user_id", None)
        session.pop("two_factor_intent", None)
        session.pop("two_factor_next", None)
        session.pop("two_factor_after_signup", None)
        flash("Two-factor authentication is not enabled for this account.", "info")
        return redirect(url_for("auth.login"))

    code = user.generate_two_factor_code()
    db.session.commit()
    intent = session.get("two_factor_intent", "login")
    send_two_factor_code_email(user.email, code, intent=intent)
    flash("We've sent a fresh verification code to your email.", "info")
    return redirect(url_for("auth.two_factor"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
