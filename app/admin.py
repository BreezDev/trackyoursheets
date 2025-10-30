from dotenv import load_dotenv
load_dotenv()
import hashlib
import io
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
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
    Producer,
    SubscriptionPlan,
    User,
    Workspace,
)
from .workspaces import get_accessible_workspaces, get_accessible_workspace_ids
from .nylas_email import send_workspace_invitation
from .guides import get_role_guides
from .marketing import build_plan_details


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
    seat_usage = (
        User.query.filter_by(org_id=current_user.org_id)
        .filter(User.status == "active")
        .count()
    )
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
    }
    if org.plan:
        plan_permissions["can_invite_producers"] = org.plan.includes_producer_portal
        plan_permissions["can_create_api_keys"] = org.plan.includes_api

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
        carrier_usage=carrier_usage,
        producer_usage=producer_usage,
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

    if plan:
        active_users = (
            User.query.filter_by(org_id=org.id)
            .filter(User.status == "active")
            .count()
        )
        if plan.max_users and active_users >= plan.max_users:
            flash(
                f"{plan.name} includes up to {plan.max_users} active users. Upgrade your plan to invite more teammates.",
                "warning",
            )
            return redirect(url_for("admin.index"))
        if role == "producer" and not plan.includes_producer_portal:
            flash(
                "Producer portals are not included in your current plan. Upgrade to invite producers.",
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

    user = User(email=email, role=role, org_id=org.id)
    user.set_password(password)
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

    db.session.commit()
    if invited_workspace and email:
        send_workspace_invitation(
            recipient=email,
            inviter=current_user,
            workspace=invited_workspace,
            role=role,
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
    org = Organization.query.get_or_404(current_user.org_id)
    plan = org.plan

    name = request.form.get("name")
    download_type = request.form.get("download_type", "csv")
    if not name:
        flash("Carrier name is required.", "danger")
    else:
        if plan and plan.max_carriers:
            existing_carriers = Carrier.query.filter_by(org_id=org.id).count()
            if existing_carriers >= plan.max_carriers:
                flash(
                    f"{plan.name} includes up to {plan.max_carriers} carriers. Upgrade your plan to add more connections.",
                    "warning",
                )
                return redirect(url_for("admin.index"))
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


@admin_bp.route("/how-to")
def how_to():
    sections = get_role_guides()
    return render_template(
        "guide.html",
        sections=sections,
        back_to=url_for("admin.index"),
    )


def _get_category_names(org_id: int):
    tags = (
        CategoryTag.query.filter_by(org_id=org_id, kind="status")
        .order_by(CategoryTag.name.asc())
        .all()
    )
    return [tag.name for tag in tags]

