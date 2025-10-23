from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import db
from .models import (
    APIKey,
    Carrier,
    CommissionRule,
    CommissionRuleSet,
    Organization,
    SubscriptionPlan,
    User,
)


admin_bp = Blueprint("admin", __name__)


def require_admin():
    if current_user.role not in {"owner", "admin"}:
        flash("You do not have access to the admin panel.", "danger")
        return False
    return True


@admin_bp.before_request
@login_required
def ensure_logged_in():
    if not require_admin():
        return redirect(url_for("main.dashboard"))


@admin_bp.route("/")
def index():
    org = Organization.query.get(current_user.org_id)
    users = User.query.filter_by(org_id=current_user.org_id).order_by(User.email.asc()).all()
    carriers = Carrier.query.filter_by(org_id=current_user.org_id).order_by(Carrier.name.asc()).all()
    rulesets = CommissionRuleSet.query.filter_by(org_id=current_user.org_id).all()
    api_keys = APIKey.query.filter_by(org_id=current_user.org_id).all()
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.tier.asc()).all()
    return render_template(
        "admin/index.html",
        org=org,
        users=users,
        carriers=carriers,
        rulesets=rulesets,
        api_keys=api_keys,
        plans=plans,
    )


@admin_bp.route("/users", methods=["POST"])
def create_user():
    email = request.form.get("email")
    role = request.form.get("role", "producer")
    if not email:
        flash("Email is required.", "danger")
    elif User.query.filter_by(email=email).first():
        flash("Email already in use.", "danger")
    else:
        user = User(email=email, role=role, org_id=current_user.org_id)
        user.set_password(request.form.get("password", "ChangeMe123!"))
        db.session.add(user)
        db.session.commit()
        flash("User created.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    user = User.query.filter_by(id=user_id, org_id=current_user.org_id).first_or_404()
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("User removed.", "info")
    return redirect(url_for("admin.index"))


@admin_bp.route("/carriers", methods=["POST"])
def create_carrier():
    name = request.form.get("name")
    download_type = request.form.get("download_type", "csv")
    if not name:
        flash("Carrier name is required.", "danger")
    else:
        carrier = Carrier(name=name, download_type=download_type, org_id=current_user.org_id)
        db.session.add(carrier)
        db.session.commit()
        flash("Carrier added.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/rulesets", methods=["POST"])
def create_ruleset():
    name = request.form.get("name")
    if not name:
        flash("Ruleset name is required.", "danger")
        return redirect(url_for("admin.index"))

    ruleset = CommissionRuleSet(name=name, org_id=current_user.org_id)
    db.session.add(ruleset)
    db.session.commit()
    flash("Ruleset created.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/rules/<int:ruleset_id>", methods=["GET", "POST"])
def manage_rules(ruleset_id):
    ruleset = CommissionRuleSet.query.filter_by(id=ruleset_id, org_id=current_user.org_id).first_or_404()
    if request.method == "POST":
        basis = request.form.get("basis")
        rate = request.form.get("rate")
        flat_amount = request.form.get("flat_amount")
        new_vs_renewal = request.form.get("new_vs_renewal")
        priority = request.form.get("priority", 0)

        rule = CommissionRule(
            ruleset=ruleset,
            match_fields={"lob": request.form.get("lob")},
            basis=basis,
            rate=rate or None,
            flat_amount=flat_amount or None,
            new_vs_renewal=new_vs_renewal,
            priority=int(priority),
        )
        db.session.add(rule)
        db.session.commit()
        flash("Rule added.", "success")
        return redirect(url_for("admin.manage_rules", ruleset_id=ruleset.id))

    rules = CommissionRule.query.filter_by(ruleset_id=ruleset.id).order_by(CommissionRule.priority.asc()).all()
    return render_template("admin/rules.html", ruleset=ruleset, rules=rules)


@admin_bp.route("/rules/<int:rule_id>/delete", methods=["POST"])
def delete_rule(rule_id):
    rule = CommissionRule.query.get_or_404(rule_id)
    if rule.ruleset.org_id != current_user.org_id:
        flash("Not authorized.", "danger")
    else:
        db.session.delete(rule)
        db.session.commit()
        flash("Rule removed.", "info")
    return redirect(url_for("admin.manage_rules", ruleset_id=rule.ruleset_id))


@admin_bp.route("/api-keys", methods=["POST"])
def create_api_key():
    label = request.form.get("label")
    if not label:
        flash("Label required.", "danger")
        return redirect(url_for("admin.index"))

    token_hash = f"demo-{label}"  # Placeholder for secure hashing implementation
    key = APIKey(org_id=current_user.org_id, label=label, token_hash=token_hash, scopes=["imports", "reports"])
    db.session.add(key)
    db.session.commit()
    flash("API key placeholder created. Update with secure token before production.", "warning")
    return redirect(url_for("admin.index"))
