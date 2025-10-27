from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import db
from .models import (
    APIKey,
    Carrier,
    CommissionRule,
    CommissionRuleSet,
    Office,
    Organization,
    Producer,
    SubscriptionPlan,
    User,
    Workspace,
)
from .workspaces import get_accessible_workspaces, get_accessible_workspace_ids


admin_bp = Blueprint("admin", __name__)


def require_admin():
    if current_user.role not in {"owner", "admin", "agent"}:
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
    org = Organization.query.get_or_404(current_user.org_id)
    workspace_ids = get_accessible_workspace_ids(current_user)
    if current_user.role in {"owner", "admin"}:
        offices = (
            Office.query.filter_by(org_id=current_user.org_id)
            .order_by(Office.name.asc())
            .all()
        )
        workspaces = (
            Workspace.query.filter_by(org_id=current_user.org_id)
            .order_by(Workspace.name.asc())
            .all()
        )
        users = (
            User.query.filter_by(org_id=current_user.org_id)
            .order_by(User.email.asc())
            .all()
        )
        plans = SubscriptionPlan.query.order_by(SubscriptionPlan.tier.asc()).all()
        api_keys = APIKey.query.filter_by(org_id=current_user.org_id).all()
    else:
        workspaces = get_accessible_workspaces(current_user)
        unique_offices = {ws.office for ws in workspaces if ws and ws.office}
        offices = sorted(unique_offices, key=lambda o: o.name)
        users = [current_user]
        if workspace_ids:
            producer_users = (
                User.query.join(Producer, User.id == Producer.user_id)
                .filter(
                    Producer.workspace_id.in_(workspace_ids),
                    User.org_id == current_user.org_id,
                )
                .order_by(User.email.asc())
                .all()
            )
            users.extend([user for user in producer_users if user.id != current_user.id])
        plans = []
        api_keys = []

    carriers = (
        Carrier.query.filter_by(org_id=current_user.org_id)
        .order_by(Carrier.name.asc())
        .all()
    )
    rulesets = CommissionRuleSet.query.filter_by(org_id=current_user.org_id).all()
    producers = []
    if workspace_ids:
        producers = (
            Producer.query.filter(Producer.workspace_id.in_(workspace_ids))
            .order_by(Producer.display_name.asc())
            .all()
        )
    return render_template(
        "admin/index.html",
        org=org,
        users=users,
        offices=offices,
        workspaces=workspaces,
        producers=producers,
        carriers=carriers,
        rulesets=rulesets,
        api_keys=api_keys,
        plans=plans,
        accessible_workspace_ids=workspace_ids,
    )


@admin_bp.route("/users", methods=["POST"])
def create_user():
    email = request.form.get("email")
    role = request.form.get("role", "producer")
    workspace_id_raw = request.form.get("workspace_id")
    workspace_id = int(workspace_id_raw) if workspace_id_raw else None
    display_name = request.form.get("display_name") or request.form.get("name")
    password = request.form.get("password", "ChangeMe123!")

    if not email:
        flash("Email is required.", "danger")
        return redirect(url_for("admin.index"))

    if User.query.filter_by(email=email).first():
        flash("Email already in use.", "danger")
        return redirect(url_for("admin.index"))

    if role == "agent" and current_user.role not in {"owner", "admin"}:
        flash("Only organization owners or admins can create agents.", "danger")
        return redirect(url_for("admin.index"))

    target_workspace = None
    if role in {"agent", "producer"}:
        accessible_ids = set(get_accessible_workspace_ids(current_user))
        if workspace_id is None:
            accessible = get_accessible_workspaces(current_user)
            if len(accessible) == 1:
                target_workspace = accessible[0]
            else:
                flash("Select a workspace for this user.", "warning")
                return redirect(url_for("admin.index"))
        else:
            target_workspace = Workspace.query.filter_by(
                id=workspace_id, org_id=current_user.org_id
            ).first()
            if not target_workspace:
                flash("Workspace not found.", "danger")
                return redirect(url_for("admin.index"))
            if current_user.role == "agent" and target_workspace.id not in accessible_ids:
                flash("You cannot add users to that workspace.", "danger")
                return redirect(url_for("admin.index"))

    user = User(email=email, role=role, org_id=current_user.org_id)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    if role == "producer":
        if not target_workspace:
            db.session.rollback()
            flash("Workspace assignment is required for producers.", "danger")
            return redirect(url_for("admin.index"))
        producer = Producer(
            org_id=current_user.org_id,
            user_id=user.id,
            workspace_id=target_workspace.id,
            agent_id=target_workspace.agent_id
            or (current_user.id if current_user.role == "agent" else None),
            display_name=display_name or email.split("@")[0],
        )
        db.session.add(producer)
    elif role == "agent" and target_workspace:
        if target_workspace.agent_id and target_workspace.agent_id != user.id:
            flash("Workspace already has an agent assigned.", "warning")
        existing = Workspace.query.filter_by(
            org_id=current_user.org_id, agent_id=user.id
        ).first()
        if existing and existing.id != target_workspace.id:
            existing.agent_id = None
        target_workspace.agent_id = user.id

    db.session.commit()
    flash(f"{role.title()} user created.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    user = User.query.filter_by(id=user_id, org_id=current_user.org_id).first_or_404()
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
    else:
        if user.role == "agent" and getattr(user, "managed_workspace", None):
            user.managed_workspace.agent_id = None
        if user.producer:
            db.session.delete(user.producer)
        db.session.delete(user)
        db.session.commit()
        flash("User removed.", "info")
    return redirect(url_for("admin.index"))


@admin_bp.route("/offices", methods=["POST"])
def create_office():
    if current_user.role not in {"owner", "admin"}:
        flash("Only organization owners or admins can create offices.", "danger")
        return redirect(url_for("admin.index"))

    name = request.form.get("name")
    timezone = request.form.get("timezone")
    if not name:
        flash("Office name is required.", "danger")
        return redirect(url_for("admin.index"))

    office = Office(org_id=current_user.org_id, name=name, timezone=timezone or None)
    db.session.add(office)
    db.session.commit()
    flash("Office created.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/workspaces", methods=["POST"])
def create_workspace():
    if current_user.role not in {"owner", "admin"}:
        flash("Only organization owners or admins can create workspaces.", "danger")
        return redirect(url_for("admin.index"))

    name = request.form.get("name")
    office_id_raw = request.form.get("office_id")
    agent_id_raw = request.form.get("agent_id")

    if not name or not office_id_raw:
        flash("Workspace name and office are required.", "danger")
        return redirect(url_for("admin.index"))

    office = Office.query.filter_by(id=int(office_id_raw), org_id=current_user.org_id).first()
    if not office:
        flash("Office not found.", "danger")
        return redirect(url_for("admin.index"))

    agent_user = None
    if agent_id_raw:
        agent_user = User.query.filter_by(id=int(agent_id_raw), org_id=current_user.org_id).first()
        if not agent_user or agent_user.role != "agent":
            flash("Select a valid agent user.", "danger")
            return redirect(url_for("admin.index"))
        existing = Workspace.query.filter_by(org_id=current_user.org_id, agent_id=agent_user.id).first()
        if existing:
            existing.agent_id = None

    workspace = Workspace(
        org_id=current_user.org_id,
        office_id=office.id,
        name=name,
        agent_id=agent_user.id if agent_user else None,
    )
    db.session.add(workspace)
    db.session.commit()
    flash("Workspace created.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/workspaces/<int:workspace_id>/assign-agent", methods=["POST"])
def assign_workspace_agent(workspace_id):
    workspace = Workspace.query.filter_by(id=workspace_id, org_id=current_user.org_id).first_or_404()
    if current_user.role not in {"owner", "admin", "agent"}:
        flash("Not authorized to assign agents.", "danger")
        return redirect(url_for("admin.index"))

    if current_user.role == "agent" and workspace.agent_id not in {None, current_user.id}:
        flash("This workspace is managed by another agent.", "danger")
        return redirect(url_for("admin.index"))

    agent_user_id = request.form.get("agent_user_id")
    if not agent_user_id:
        flash("Select an agent to assign.", "danger")
        return redirect(url_for("admin.index"))

    agent_user = User.query.filter_by(id=int(agent_user_id), org_id=current_user.org_id).first()
    if not agent_user or agent_user.role != "agent":
        flash("Invalid agent selected.", "danger")
        return redirect(url_for("admin.index"))

    existing = Workspace.query.filter_by(org_id=current_user.org_id, agent_id=agent_user.id).first()
    if existing and existing.id != workspace.id:
        existing.agent_id = None

    workspace.agent_id = agent_user.id
    db.session.commit()
    flash("Workspace agent updated.", "success")
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
