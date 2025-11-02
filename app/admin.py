from dotenv import load_dotenv
load_dotenv()
import hashlib
import io
import secrets
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import current_user, login_required

from . import db
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .models import (
    APIKey,
    Carrier,
    CommissionRule,
    CommissionRuleSet,
    CommissionTransaction,
    CommissionOverride,
    CategoryTag,
    Office,
    Organization,
    PayrollEntry,
    PayrollRun,
    Producer,
    SubscriptionPlan,
    User,
    Workspace,
)
from .workspaces import get_accessible_workspaces, get_accessible_workspace_ids
from .resend_email import send_workspace_invitation
from .guides import get_role_guides, get_interactive_tour
from .marketing import build_plan_details
from .models import DEFAULT_NOTIFICATION_PREFERENCES


admin_bp = Blueprint("admin", __name__)


NOTIFICATION_LABELS = {
    "signup": "New signup alerts",
    "login": "Login alerts",
    "workspace_invite": "Workspace invitations",
    "plan_updates": "Plan and billing updates",
    "workspace_updates": "Workspace membership updates",
    "new_entries": "New import entries",
    "general_updates": "Product news",
}


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
    seat_usage = (
        User.query.filter_by(org_id=current_user.org_id)
        .filter(User.status == "active")
        .count()
    )
    seat_limit = None
    included_seats = None
    extra_seat_price = None
    seats_remaining = None
    if org.plan:
        included_seats = org.plan.included_users or org.plan.max_users
        extra_seat_price = org.plan.extra_user_price
        if included_seats:
            seat_limit = included_seats
    if seat_limit is not None:
        seats_remaining = max(seat_limit - seat_usage, 0)
    carrier_usage = Carrier.query.filter_by(org_id=current_user.org_id).count()
    producer_usage = Producer.query.filter_by(org_id=current_user.org_id).count()
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
        api_keys = (
            APIKey.query.filter_by(org_id=current_user.org_id)
            .order_by(APIKey.created_at.desc())
            .all()
        )
        plan_cards = build_plan_details(plans) if plans else []
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
        plan_cards = build_plan_details([org.plan]) if org.plan else []

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
    api_key_tokens = session.get("api_key_tokens", {})
    new_key_id = request.args.get("new_key_id")
    revealed_api_key = None
    if new_key_id and new_key_id in api_key_tokens:
        key_obj = next((key for key in api_keys if str(key.id) == new_key_id), None)
        if key_obj:
            revealed_api_key = {
                "id": key_obj.id,
                "label": key_obj.label,
                "token": api_key_tokens[new_key_id],
            }

    plan_details_map = {detail["id"]: detail for detail in plan_cards}
    if org.plan_id and org.plan_id not in plan_details_map and org.plan:
        supplemental = build_plan_details([org.plan])
        plan_details_map.update({detail["id"]: detail for detail in supplemental})
    current_plan_detail = plan_details_map.get(org.plan_id)
    plan_limits = current_plan_detail.get("limits") if current_plan_detail else None
    plan_permissions = {
        "can_invite_producers": True,
        "can_create_api_keys": False,
        "invite_disabled_reason": None,
    }
    if org.plan:
        plan_permissions["can_create_api_keys"] = org.plan.includes_api
        if seat_limit is not None and seat_usage >= seat_limit:
            if extra_seat_price:
                plan_permissions["invite_disabled_reason"] = (
                    f"You've used all {seat_limit} included seats. Additional users are ${float(extra_seat_price):.2f} per month."
                )
            else:
                plan_permissions["can_invite_producers"] = False
                plan_permissions[
                    "invite_disabled_reason"
                ] = f"{org.plan.name} includes up to {seat_limit} seats. Upgrade to add more teammates."

    total_users = len(users)
    notification_options = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    current_preferences = (
        current_user.notification_preferences or notification_options
    )
    notification_rollups = []
    if total_users:
        for key, default_enabled in notification_options.items():
            enabled_count = sum(1 for member in users if member.wants_notification(key))
            notification_rollups.append(
                {
                    "key": key,
                    "label": NOTIFICATION_LABELS.get(
                        key, key.replace("_", " ").title()
                    ),
                    "enabled": enabled_count,
                    "total": total_users,
                    "default_enabled": default_enabled,
                }
            )

    two_factor_org_totals = {
        "enabled": sum(1 for member in users if member.two_factor_enabled),
        "total": total_users,
    }

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
        revealed_api_key=revealed_api_key,
        downloadable_api_keys=set(api_key_tokens.keys()),
        plan_limits=plan_limits,
        current_plan_detail=current_plan_detail,
        plan_permissions=plan_permissions,
        seat_usage=seat_usage,
        seat_limit=seat_limit,
        seats_remaining=seats_remaining,
        included_seats=included_seats,
        extra_seat_price=extra_seat_price,
        carrier_usage=carrier_usage,
        producer_usage=producer_usage,
        notification_options=notification_options,
        notification_labels=NOTIFICATION_LABELS,
        user_notifications=current_preferences,
        two_factor_enabled=current_user.two_factor_enabled,
        notification_rollups=notification_rollups,
        two_factor_org_totals=two_factor_org_totals,
    )


@admin_bp.route("/users", methods=["POST"])
def create_user():
    org = Organization.query.get_or_404(current_user.org_id)
    plan = org.plan

    email = request.form.get("email")
    role = request.form.get("role", "producer")
    workspace_id_raw = request.form.get("workspace_id")
    workspace_id = int(workspace_id_raw) if workspace_id_raw else None
    display_name = request.form.get("display_name") or request.form.get("name")
    temporary_password = secrets.token_urlsafe(10)

    if not email:
        flash("Email is required.", "danger")
        return redirect(url_for("admin.index"))

    if User.query.filter_by(email=email).first():
        flash("Email already in use.", "danger")
        return redirect(url_for("admin.index"))

    if role == "agent" and current_user.role not in {"owner", "admin"}:
        flash("Only organization owners or admins can create agents.", "danger")
        return redirect(url_for("admin.index"))

    if plan:
        active_users = (
            User.query.filter_by(org_id=org.id)
            .filter(User.status == "active")
            .count()
        )
        included_limit = plan.included_users or plan.max_users
        if included_limit and active_users >= included_limit:
            if plan.extra_user_price:
                flash(
                    (
                        f"You've reached the {included_limit} seats included with {plan.name}. "
                        f"Additional users will be billed at ${float(plan.extra_user_price):.2f}/month each."
                    ),
                    "info",
                )
            else:
                flash(
                    f"{plan.name} includes up to {included_limit} active users. Upgrade your plan to invite more teammates.",
                    "warning",
                )
                return redirect(url_for("admin.index"))
    target_workspace = None
    invited_workspace = None
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

    user = User(email=email, role=role, org_id=org.id, must_change_password=True)
    user.set_password(temporary_password)
    db.session.add(user)
    db.session.flush()

    if role == "producer":
        if not target_workspace:
            db.session.rollback()
            flash("Workspace assignment is required for producers.", "danger")
            return redirect(url_for("admin.index"))
        producer = Producer(
            org_id=org.id,
            user_id=user.id,
            workspace_id=target_workspace.id,
            agent_id=target_workspace.agent_id
            or (current_user.id if current_user.role == "agent" else None),
            display_name=display_name or email.split("@")[0],
        )
        db.session.add(producer)
        invited_workspace = target_workspace
    elif role == "agent" and target_workspace:
        if target_workspace.agent_id and target_workspace.agent_id != user.id:
            flash("Workspace already has an agent assigned.", "warning")
        existing = Workspace.query.filter_by(
            org_id=current_user.org_id, agent_id=user.id
        ).first()
        if existing and existing.id != target_workspace.id:
            existing.agent_id = None
        target_workspace.agent_id = user.id
        invited_workspace = target_workspace

    if invited_workspace:
        user.record_workspace_membership(invited_workspace, role=role)

    db.session.commit()
    if invited_workspace and email:
        login_target = url_for(
            "main.dashboard", workspace_id=invited_workspace.id, _external=True
        )
        login_url = url_for(
            "auth.login",
            email=email,
            next=login_target,
            _external=True,
        )
        send_workspace_invitation(
            recipient=email,
            inviter=current_user,
            workspace=invited_workspace,
            role=role,
            temporary_password=temporary_password,
            login_url=login_url,
        )
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
    db.session.flush()
    if agent_user:
        agent_user.record_workspace_membership(workspace, role="agent")
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
    agent_user.record_workspace_membership(workspace, role="agent")
    db.session.commit()
    flash("Workspace agent updated.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/carriers", methods=["POST"])
def create_carrier():
    org = Organization.query.get_or_404(current_user.org_id)
    plan = org.plan

    name = request.form.get("name")
    download_type = request.form.get("download_type", "csv")
    if not name:
        flash("Carrier name is required.", "danger")
    else:
        carrier = Carrier(name=name, download_type=download_type, org_id=org.id)
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
    if current_user.role not in {"owner", "admin"}:
        flash("Only owners and admins can create API keys.", "danger")
        return redirect(url_for("admin.index"))

    org = Organization.query.get_or_404(current_user.org_id)
    if not org.plan or not org.plan.includes_api:
        flash("API access is available on the Scale plan. Upgrade to generate API keys.", "warning")
        return redirect(url_for("admin.index"))

    label = request.form.get("label")
    if not label:
        flash("Label required.", "danger")
        return redirect(url_for("admin.index"))

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    key = APIKey(
        org_id=current_user.org_id,
        label=label,
        token_hash=token_hash,
        token_prefix=raw_token[:8],
        token_last4=raw_token[-4:],
        scopes=["imports", "reports"],
    )
    db.session.add(key)
    db.session.commit()
    token_store = session.get("api_key_tokens", {})
    token_store[str(key.id)] = raw_token
    session["api_key_tokens"] = token_store
    session.modified = True
    flash("API key generated. Copy or download it now; it will not be shown again.", "success")
    return redirect(url_for("admin.index", new_key_id=key.id))


@admin_bp.route("/api-keys/<int:key_id>/download")
def download_api_key(key_id: int):
    if current_user.role not in {"owner", "admin"}:
        flash("You do not have access to this API key.", "danger")
        return redirect(url_for("admin.index"))

    token_store = session.get("api_key_tokens", {})
    token = token_store.get(str(key_id))
    if not token:
        flash("API keys can only be downloaded immediately after creation.", "warning")
        return redirect(url_for("admin.index"))

    key = APIKey.query.filter_by(id=key_id, org_id=current_user.org_id).first_or_404()
    if not key.is_active:
        flash("This API key has been revoked and cannot be downloaded.", "danger")
        return redirect(url_for("admin.index"))

    filename = f"{key.label.lower().replace(' ', '_')}_api_key.txt"
    content = (
        "TrackYourSheets API key\n"
        f"Label: {key.label}\n"
        f"Token: {token}\n"
        f"Generated: {key.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
    )
    buffer = io.BytesIO(content.encode("utf-8"))
    token_store.pop(str(key_id), None)
    session["api_key_tokens"] = token_store
    session.modified = True
    return send_file(
        buffer,
        mimetype="text/plain",
        as_attachment=True,
        download_name=filename,
    )


@admin_bp.route("/api-keys/<int:key_id>/revoke", methods=["POST"])
def revoke_api_key(key_id: int):
    if current_user.role not in {"owner", "admin"}:
        flash("Only owners and admins can revoke API keys.", "danger")
        return redirect(url_for("admin.index"))

    key = APIKey.query.filter_by(id=key_id, org_id=current_user.org_id).first_or_404()
    if not key.is_active:
        flash("API key already revoked.", "info")
        return redirect(url_for("admin.index"))

    key.revoked_at = datetime.utcnow()
    db.session.add(key)
    db.session.commit()
    token_store = session.get("api_key_tokens", {})
    if str(key_id) in token_store:
        token_store.pop(str(key_id), None)
        session["api_key_tokens"] = token_store
        session.modified = True
    flash("API key revoked.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/leaderboard")
def leaderboard():
    workspace_ids = get_accessible_workspace_ids(current_user)
    txn_query = CommissionTransaction.query.filter_by(org_id=current_user.org_id)
    if workspace_ids:
        txn_query = txn_query.filter(
            CommissionTransaction.workspace_id.in_(workspace_ids)
        )

    totals = (
        txn_query.with_entities(
            CommissionTransaction.producer_id,
            func.coalesce(func.sum(CommissionTransaction.amount), 0),
            func.coalesce(func.sum(CommissionTransaction.premium), 0),
            func.count(CommissionTransaction.id),
        )
        .group_by(CommissionTransaction.producer_id)
        .all()
    )

    producer_ids = [row[0] for row in totals if row[0]]
    producers = {}
    if producer_ids:
        producers = {
            producer.id: producer
            for producer in Producer.query.filter(
                Producer.id.in_(producer_ids),
                Producer.org_id == current_user.org_id,
            ).all()
        }

    rows = []
    unassigned = next((row for row in totals if row[0] is None), None)
    for producer_id, commission_sum, premium_sum, txn_count in totals:
        producer_obj = producers.get(producer_id)
        rows.append(
            {
                "producer": producer_obj,
                "producer_id": producer_id,
                "display_name": producer_obj.display_name if producer_obj else "Unassigned",
                "workspace": producer_obj.workspace.name if producer_obj and producer_obj.workspace else "—",
                "commission": float(commission_sum or 0),
                "premium": float(premium_sum or 0),
                "transactions": int(txn_count or 0),
            }
        )

    rows.sort(key=lambda item: item["commission"], reverse=True)

    return render_template(
        "admin/leaderboard.html",
        leaderboard=rows,
        accessible_workspace_ids=workspace_ids,
        unassigned=unassigned,
    )


@admin_bp.route("/leaderboard/<int:producer_id>")
def producer_sales(producer_id: int):
    producer = Producer.query.filter_by(
        id=producer_id, org_id=current_user.org_id
    ).first_or_404()

    workspace_ids = get_accessible_workspace_ids(current_user)
    if current_user.role == "agent" and workspace_ids and producer.workspace_id not in workspace_ids:
        flash("You do not have access to this producer's transactions.", "danger")
        return redirect(url_for("admin.leaderboard"))

    if request.args.get("clear"):
        return redirect(url_for("admin.producer_sales", producer_id=producer.id))

    category_filter = request.args.get("category")
    product_filter = request.args.get("product_type")
    status_filter = request.args.get("status")

    txn_query = CommissionTransaction.query.filter_by(
        org_id=current_user.org_id, producer_id=producer.id
    )
    if workspace_ids:
        txn_query = txn_query.filter(
            CommissionTransaction.workspace_id.in_(workspace_ids)
        )
    if category_filter:
        txn_query = txn_query.filter(
            func.lower(CommissionTransaction.category) == category_filter.lower()
        )
    if product_filter:
        txn_query = txn_query.filter(
            func.lower(CommissionTransaction.product_type) == product_filter.lower()
        )
    if status_filter:
        txn_query = txn_query.filter(
            func.lower(CommissionTransaction.status) == status_filter.lower()
        )

    transactions = (
        txn_query.order_by(CommissionTransaction.txn_date.desc(), CommissionTransaction.id.desc())
        .limit(500)
        .all()
    )

    totals = {
        "commission": sum(float(txn.amount or 0) for txn in transactions),
        "premium": sum(float(txn.premium or 0) for txn in transactions),
        "count": len(transactions),
    }

    categories = _get_category_names(current_user.org_id)
    product_types = sorted(
        {txn.product_type for txn in transactions if txn.product_type}
    )
    statuses = sorted({txn.status for txn in transactions if txn.status})

    return render_template(
        "admin/producer_sales.html",
        producer=producer,
        transactions=transactions,
        totals=totals,
        categories=categories,
        product_types=product_types,
        statuses=statuses,
        active_filters={
            "category": category_filter,
            "product_type": product_filter,
            "status": status_filter,
        },
    )


@admin_bp.route("/commission-overrides/apply", methods=["POST"])
def apply_commission_override():
    txn_ids = request.form.getlist("transaction_ids")
    override_mode = request.form.get("override_mode")
    override_value_raw = request.form.get("override_value")
    notes = request.form.get("notes") or None
    return_to = (
        request.form.get("return_url")
        or request.referrer
        or url_for("admin.leaderboard")
    )

    if not txn_ids:
        flash("Select at least one transaction to override.", "warning")
        return redirect(return_to)

    if override_mode not in {"flat", "percent", "split"}:
        flash("Choose a valid override type.", "danger")
        return redirect(return_to)

    try:
        override_value = Decimal(override_value_raw)
    except (InvalidOperation, TypeError):
        flash("Enter a valid numeric override value.", "danger")
        return redirect(return_to)

    txn_query = CommissionTransaction.query.filter(
        CommissionTransaction.id.in_(txn_ids),
        CommissionTransaction.org_id == current_user.org_id,
    )
    transactions = txn_query.all()

    if not transactions:
        flash("No matching transactions found for override.", "danger")
        return redirect(return_to)

    accessible_ids = set(get_accessible_workspace_ids(current_user))
    applied = 0
    now = datetime.utcnow()

    def _to_decimal(value):
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    for txn in transactions:
        if current_user.role == "agent" and accessible_ids and txn.workspace_id not in accessible_ids:
            continue

        override = CommissionOverride(
            org_id=current_user.org_id,
            transaction_id=txn.id,
            override_type=override_mode,
            applied_by=current_user.id,
            notes=notes,
            applied_at=now,
        )

        if override_mode == "flat":
            override.flat_amount = override_value
            txn.manual_amount = override_value
            txn.amount = override_value
            txn.commission = override_value
            txn.override_source = "manual_flat"
        elif override_mode == "percent":
            override.percent = override_value
            base = txn.premium or txn.amount or txn.commission
            if base is not None:
                calculated = _to_decimal(base) * (override_value / Decimal("100"))
                txn.amount = calculated
                txn.manual_amount = calculated
                txn.commission = calculated
            txn.override_source = "manual_percent"
        elif override_mode == "split":
            override.split_pct = override_value
            txn.manual_split_pct = override_value
            txn.split_pct = override_value
            base = txn.commission if txn.commission is not None else txn.amount
            if base is None and txn.premium is not None:
                base = txn.premium
            if base is not None:
                calculated = _to_decimal(base) * (override_value / Decimal("100"))
                txn.amount = calculated
                txn.manual_amount = calculated
                txn.commission = calculated
            txn.override_source = "manual_split"

        txn.override_applied_at = now
        txn.override_applied_by = current_user.id
        db.session.add(override)
        db.session.add(txn)
        applied += 1

    if not applied:
        flash("No transactions were updated. Check your permissions.", "warning")
        return redirect(return_to)

    db.session.commit()
    flash(f"Applied overrides to {applied} transaction(s).", "success")
    return redirect(return_to)


@admin_bp.route("/transactions/<int:txn_id>/edit", methods=["POST"])
def edit_transaction(txn_id: int):
    txn = CommissionTransaction.query.filter_by(
        id=txn_id,
        org_id=current_user.org_id,
    ).first_or_404()

    accessible_ids = set(get_accessible_workspace_ids(current_user))
    if (
        current_user.role == "agent"
        and accessible_ids
        and txn.workspace_id not in accessible_ids
    ):
        abort(403)

    return_to = request.form.get("return_url") or request.referrer or url_for(
        "admin.leaderboard"
    )

    manual_amount_raw = request.form.get("manual_amount")
    manual_split_raw = request.form.get("manual_split_pct")
    status_value = (request.form.get("status") or "").strip() or None
    note_body = (request.form.get("notes") or "").strip() or None

    manual_amount = None
    if manual_amount_raw:
        try:
            manual_amount = Decimal(manual_amount_raw)
        except (InvalidOperation, TypeError):
            flash("Enter a valid manual commission amount.", "danger")
            return redirect(return_to)

    manual_split = None
    if manual_split_raw:
        try:
            manual_split = Decimal(manual_split_raw)
        except (InvalidOperation, TypeError):
            flash("Enter a valid manual split percentage.", "danger")
            return redirect(return_to)

    if manual_amount is not None:
        txn.manual_amount = manual_amount
        txn.amount = manual_amount
        txn.commission = manual_amount
        txn.override_source = "manual_edit"
    elif request.form.get("clear_manual_amount"):
        txn.manual_amount = None
        if txn.override_source == "manual_edit":
            txn.override_source = None

    if manual_split is not None:
        txn.manual_split_pct = manual_split
        txn.split_pct = manual_split
        txn.override_source = txn.override_source or "manual_edit"
    elif request.form.get("clear_manual_split"):
        txn.manual_split_pct = None

    if status_value:
        txn.status = status_value

    if note_body or manual_amount is not None or manual_split is not None:
        override = CommissionOverride(
            org_id=current_user.org_id,
            transaction_id=txn.id,
            override_type="manual_edit",
            flat_amount=manual_amount,
            split_pct=manual_split,
            applied_by=current_user.id,
            notes=note_body,
        )
        db.session.add(override)

    txn.override_applied_at = datetime.utcnow()
    txn.override_applied_by = current_user.id
    db.session.add(txn)
    db.session.commit()

    flash("Commission settings updated for the sale.", "success")
    return redirect(return_to)


@admin_bp.route("/categories", methods=["GET", "POST"])
def manage_categories():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        kind = request.form.get("kind") or "status"
        if not name:
            flash("Category name is required.", "danger")
            return redirect(url_for("admin.manage_categories"))
        tag = CategoryTag(
            org_id=current_user.org_id,
            name=name,
            kind=kind,
            is_default=False,
        )
        db.session.add(tag)
        try:
            db.session.commit()
            flash("Category added.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Category already exists for this organization.", "warning")
        return redirect(url_for("admin.manage_categories"))

    categories = (
        CategoryTag.query.filter_by(org_id=current_user.org_id)
        .order_by(CategoryTag.kind.asc(), CategoryTag.name.asc())
        .all()
    )
    return render_template("admin/categories.html", categories=categories)


@admin_bp.route("/categories/<int:category_id>/update", methods=["POST"])
def update_category(category_id: int):
    tag = CategoryTag.query.filter_by(
        id=category_id, org_id=current_user.org_id
    ).first_or_404()
    name = (request.form.get("name") or "").strip()
    kind = request.form.get("kind") or tag.kind
    if not name:
        flash("Category name cannot be empty.", "danger")
        return redirect(url_for("admin.manage_categories"))

    tag.name = name
    tag.kind = kind
    try:
        db.session.commit()
        flash("Category updated.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Another category already uses that name.", "warning")
    return redirect(url_for("admin.manage_categories"))


@admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
def delete_category(category_id: int):
    tag = CategoryTag.query.filter_by(
        id=category_id, org_id=current_user.org_id
    ).first_or_404()
    db.session.delete(tag)
    db.session.commit()
    flash("Category removed.", "info")
    return redirect(url_for("admin.manage_categories"))


@admin_bp.route("/payroll", methods=["GET", "POST"])
def payroll_dashboard():
    if not require_admin():
        return redirect(url_for("admin.index"))

    org = Organization.query.get_or_404(current_user.org_id)
    today = datetime.utcnow().date()
    default_start = today - timedelta(days=14)
    default_end = today

    def _parse_date(value: str | None, fallback):
        if not value:
            return fallback
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return fallback

    date_from = _parse_date(request.values.get("date_from"), default_start)
    date_to = _parse_date(request.values.get("date_to"), default_end)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    txn_query = CommissionTransaction.query.filter_by(org_id=current_user.org_id)
    txn_query = txn_query.filter(
        CommissionTransaction.txn_date >= date_from,
        CommissionTransaction.txn_date <= date_to,
    )

    status_rows = (
        txn_query.with_entities(
            CommissionTransaction.status.label("status"),
            func.count(CommissionTransaction.id).label("count"),
            func.coalesce(func.sum(CommissionTransaction.amount), 0).label("amount"),
        )
        .group_by(CommissionTransaction.status)
        .all()
    )
    status_summary = [
        {
            "status": row.status or "unspecified",
            "count": row.count,
            "amount": Decimal(row.amount or 0),
        }
        for row in status_rows
    ]

    payroll_rows_raw = (
        txn_query.join(Producer, CommissionTransaction.producer_id == Producer.id, isouter=True)
        .join(User, Producer.user_id == User.id, isouter=True)
        .with_entities(
            CommissionTransaction.producer_id.label("producer_id"),
            Producer.display_name.label("producer_name"),
            User.id.label("user_id"),
            func.coalesce(func.sum(CommissionTransaction.amount), 0).label("commission_total"),
            func.count(CommissionTransaction.id).label("transaction_count"),
        )
        .group_by(
            CommissionTransaction.producer_id,
            Producer.display_name,
            User.id,
        )
        .all()
    )

    payroll_rows = []
    total_commission = Decimal("0")
    for row in payroll_rows_raw:
        amount = Decimal(row.commission_total or 0)
        payroll_rows.append(
            {
                "producer_id": row.producer_id,
                "producer_name": row.producer_name or "Unassigned",
                "user_id": row.user_id,
                "transaction_count": row.transaction_count,
                "commission_total": amount,
                "average_amount": (amount / row.transaction_count) if row.transaction_count else Decimal("0"),
            }
        )
        total_commission += amount

    payroll_rows.sort(key=lambda item: item["producer_name"].lower())

    recent_transactions = (
        txn_query.options(
            joinedload(CommissionTransaction.producer),
            joinedload(CommissionTransaction.workspace),
        )
        .order_by(CommissionTransaction.txn_date.desc(), CommissionTransaction.id.desc())
        .limit(10)
        .all()
    )

    previous_runs = (
        PayrollRun.query.filter_by(org_id=current_user.org_id)
        .order_by(PayrollRun.created_at.desc())
        .limit(5)
        .all()
    )

    stripe_gateway = current_app.extensions.get("stripe_gateway")
    stripe_ready = bool(stripe_gateway and stripe_gateway.is_configured)

    if request.method == "POST":
        if not payroll_rows:
            flash("No commission transactions found for the selected period.", "warning")
        else:
            run = PayrollRun(
                org_id=current_user.org_id,
                period_start=date_from,
                period_end=date_to,
                total_commission=total_commission,
                total_adjustments=Decimal("0"),
                total_payout=total_commission,
                status="pending_payout",
                created_by_id=current_user.id,
                processing_notes=request.form.get("notes") or None,
            )
            db.session.add(run)
            db.session.flush()
            for row in payroll_rows:
                entry = PayrollEntry(
                    org_id=current_user.org_id,
                    payroll_run_id=run.id,
                    producer_id=row["producer_id"],
                    user_id=row["user_id"],
                    producer_snapshot=row["producer_name"],
                    commission_total=row["commission_total"],
                    adjustments=Decimal("0"),
                    payout_amount=row["commission_total"],
                    notes=f"Auto-generated from commissions {date_from.isoformat()} – {date_to.isoformat()}",
                )
                db.session.add(entry)

            payout_message = None
            if stripe_ready and total_commission > 0:
                try:
                    payout = stripe_gateway.create_commission_payout(
                        organization=org,
                        amount=total_commission,
                        memo=f"Commission payroll {date_from.isoformat()} – {date_to.isoformat()}",
                        metadata={"payroll_run_id": run.id},
                    )
                except Exception as exc:  # pragma: no cover - Stripe failure path
                    payout = None
                    run.processing_notes = f"Stripe payout error: {exc}"
                    current_app.logger.exception(
                        "Stripe payout error",
                        extra={"payroll_run_id": run.id},
                    )
                else:
                    if payout:
                        run.stripe_payout_id = payout.get("id")
                        run.stripe_payout_status = payout.get("status")
                        if payout.get("status") in {"paid", "succeeded"}:
                            run.status = "processed"
                            run.processed_at = datetime.utcnow()
                        else:
                            run.status = "processing"
                        payout_message = payout.get("message")
            else:
                run.processing_notes = (run.processing_notes or "") + " Stripe payout not attempted; gateway unavailable."

            db.session.commit()
            if run.stripe_payout_id:
                flash(
                    "Payroll run created and payout submitted to Stripe." + (f" {payout_message}" if payout_message else ""),
                    "success",
                )
            else:
                flash(
                    "Payroll run created. Review the entries and send payouts manually when ready.",
                    "info",
                )
            return redirect(
                url_for(
                    "admin.payroll_dashboard",
                    date_from=date_from.isoformat(),
                    date_to=date_to.isoformat(),
                )
            )

    return render_template(
        "admin/payroll.html",
        org=org,
        active_tab="payroll",
        date_from=date_from,
        date_to=date_to,
        payroll_rows=payroll_rows,
        total_commission=total_commission,
        status_summary=status_summary,
        recent_transactions=recent_transactions,
        previous_runs=previous_runs,
        stripe_ready=stripe_ready,
    )


@admin_bp.route("/how-to")
def how_to():
    sections = get_role_guides()
    tour_steps = get_interactive_tour()
    return render_template(
        "guide.html",
        sections=sections,
        back_to=url_for("admin.index"),
        tour_steps=tour_steps,
    )


@admin_bp.route("/security", methods=["POST"])
def update_security_preferences():
    selected = request.form.getlist("notifications")
    two_factor_enabled = bool(request.form.get("two_factor_enabled"))
    current_user.set_notification_preferences(selected)
    current_user.two_factor_enabled = two_factor_enabled
    if not two_factor_enabled:
        current_user.clear_two_factor_challenge()
    db.session.commit()
    flash("Security preferences updated.", "success")
    return redirect(url_for("admin.index") + "#security")


def _get_category_names(org_id: int):
    tags = (
        CategoryTag.query.filter_by(org_id=org_id, kind="status")
        .order_by(CategoryTag.name.asc())
        .all()
    )
    return [tag.name for tag in tags]

