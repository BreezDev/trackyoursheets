from dotenv import load_dotenv
load_dotenv()
import re
from datetime import date, datetime, timedelta
from typing import Sequence

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    jsonify,
    abort,
    url_for,
    flash,
    redirect,
    session,
)
from flask_login import current_user, login_required

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from werkzeug.security import generate_password_hash

from werkzeug.routing import BuildError
from markupsafe import Markup, escape

from .models import (
    AuditLog,
    CommissionTransaction,
    ImportBatch,
    Workspace,
    WorkspaceNote,
    WorkspaceChatMessage,
    MessageThread,
    MessageParticipant,
    ConversationMessage,
    Organization,
    SubscriptionPlan,
    Subscription,
    Coupon,
    User,
    Producer,
    Carrier,
    DEFAULT_NOTIFICATION_PREFERENCES,
)
from .guides import get_role_guides, get_interactive_tour
from .workspaces import get_accessible_workspace_ids, get_accessible_workspaces, user_can_access_workspace
from . import db
from .resend_email import (
    send_notification_email,
    send_two_factor_code_email,
    send_workspace_chat_notification,
    send_workspace_update_notification,
)
from .marketing import (
    build_plan_details,
    marketing_highlights,
    marketing_integrations,
    marketing_metrics,
    marketing_operations_pillars,
    marketing_personas,
    marketing_testimonials,
    marketing_timeline,
    marketing_top_questions,
)


main_bp = Blueprint("main", __name__)


MENTION_PATTERN = re.compile(r"@([A-Za-z0-9_.+-]+)")


def _display_user_name(user):
    if not user:
        return "Unknown user"
    if hasattr(user, "display_name_for_ui"):
        return user.display_name_for_ui
    if getattr(user, "email", None):
        return user.email
    return "Unknown user"


def _format_timestamp(value):
    if not value:
        return None
    return value.strftime("%b %d, %Y %I:%M %p")


def _note_meta(note):
    if not note:
        return None
    return {
        "editor": _display_user_name(note.owner),
        "timestamp": _format_timestamp(note.updated_at),
        "iso": note.updated_at.isoformat() if note.updated_at else None,
    }


def _dedupe_emails(emails: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for email in emails:
        if not email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(email)
    return unique


def _billing_contacts(organization) -> list[str]:
    if not organization or not getattr(organization, "users", None):
        return []
    emails: list[str] = []
    for user in organization.users:
        if user.role in {"owner", "admin"} and getattr(user, "email", None):
            if user.wants_notification("plan_updates"):
                emails.append(user.email)
    return _dedupe_emails(emails)


def _workspace_recipients(workspace, *, preference: str, exclude_user_id: int | None = None) -> list[str]:
    if not workspace or not getattr(workspace, "organization", None):
        return []
    recipients: list[str] = []
    for member in workspace.organization.users:
        if member.id == exclude_user_id:
            continue
        if not getattr(member, "email", None):
            continue
        if not member.wants_notification(preference):
            continue
        recipients.append(member.email)
    agent = getattr(workspace, "agent", None)
    if agent and agent.id != exclude_user_id and getattr(agent, "email", None):
        if agent.wants_notification(preference):
            recipients.append(agent.email)
    return _dedupe_emails(recipients)


def _serialize_chat_message(message: WorkspaceChatMessage) -> dict:
    return {
        "id": message.id,
        "content": message.content,
        "content_html": str(_render_chat_message_html(message)),
        "author": _display_user_name(message.author),
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "created_at_display": _format_timestamp(message.created_at),
    }


def _calculate_premium_totals(
    org_id: int, workspace_ids: Sequence[int] | None
) -> dict[str, float]:
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    quarter_index = (today.month - 1) // 3
    start_of_quarter = date(today.year, quarter_index * 3 + 1, 1)
    start_of_year = date(today.year, 1, 1)

    def _sum_since(start_date: date | None) -> float:
        query = CommissionTransaction.query.filter_by(org_id=org_id)
        if workspace_ids:
            query = query.filter(
                or_(
                    CommissionTransaction.workspace_id.in_(workspace_ids),
                    CommissionTransaction.batch.has(
                        ImportBatch.workspace_id.in_(workspace_ids)
                    ),
                )
            )
        if start_date:
            query = query.filter(CommissionTransaction.txn_date >= start_date)
        total = (
            query.with_entities(
                func.coalesce(func.sum(CommissionTransaction.premium), 0)
            ).scalar()
            or 0
        )
        return float(total)

    return {
        "today": _sum_since(today),
        "week": _sum_since(start_of_week),
        "month": _sum_since(start_of_month),
        "quarter": _sum_since(start_of_quarter),
        "year": _sum_since(start_of_year),
    }


def _render_chat_message_html(message: WorkspaceChatMessage) -> Markup:
    content = message.content or ""
    parts: list[Markup] = []
    last_index = 0
    for match in MENTION_PATTERN.finditer(content):
        start, end = match.span()
        if start > last_index:
            parts.append(escape(content[last_index:start]))
        handle = escape(match.group(1))
        parts.append(
            Markup(
                f'<span class="badge rounded-pill bg-primary-soft text-primary">@{handle}</span>'
            )
        )
        last_index = end
    if last_index < len(content):
        parts.append(escape(content[last_index:]))
    if not parts:
        parts.append(escape(content))
    combined = Markup("").join(parts)
    return Markup(str(combined).replace("\n", "<br>"))


def _audit_actor_label(actor, actor_id: int | None) -> str:
    if actor:
        return _display_user_name(actor)
    if actor_id is None:
        return "System automation"
    return f"User #{actor_id}"


def _serialize_audit_event(event: AuditLog, actor_lookup: dict[int, User]) -> dict:
    actor = actor_lookup.get(event.actor_user_id) if actor_lookup else None
    return {
        "id": event.id,
        "action": event.action,
        "entity": event.entity,
        "entity_id": event.entity_id,
        "actor_display": _audit_actor_label(actor, event.actor_user_id),
        "timestamp": event.ts,
        "timestamp_display": _format_timestamp(event.ts),
        "before": event.before,
        "after": event.after,
    }


@main_bp.route("/")
def landing():
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.tier.asc()).all()
    plan_details = build_plan_details(plans)

    try:
        api_guide_url = url_for("main.api_guide")
    except BuildError:
        api_guide_url = url_for("main.guide")

    resource_links = [
        {
            "title": "Role-based onboarding guide",
            "description": "Step-by-step directions for admins, HR, finance, and producers—accessible anytime in-app.",
            "href": url_for("main.guide"),
            "icon": "bi-journal-text",
        },
        {
            "title": "Team signup Excel template",
            "description": "Collect emails, roles, base salaries, and workspace assignments in one spreadsheet during onboarding.",
            "href": url_for("static", filename="downloads/signup_template.xlsx"),
            "icon": "bi-file-earmark-spreadsheet",
        },
        {
            "title": "Messaging & collaboration tips",
            "description": "Use workspace chat, private conversations, and shared boards to keep every office aligned.",
            "href": url_for("main.messages_home"),
            "icon": "bi-chat-dots",
        },
    ]

    return render_template(
        "landing.html",
        plan_details=plan_details,
        hero_metrics=marketing_metrics(),
        feature_sections=marketing_highlights(),
        operations_pillars=marketing_operations_pillars(),
        persona_sections=marketing_personas(),
        integrations=marketing_integrations(),
        testimonials=marketing_testimonials(),
        top_questions=marketing_top_questions(),
        timeline_steps=marketing_timeline(),
        api_guide_url=api_guide_url,
        show_dashboard_link=current_user.is_authenticated,
        resource_links=resource_links,
    )


@main_bp.route("/contact")
def contact():
    return render_template("contact.html")


@main_bp.route("/api-guide")
def api_guide():
    api_sections = [
        {
            "title": "Authentication & security",
            "bullets": [
                "Use OAuth 2.1 client credentials to request access tokens from `/oauth/token` with scopes like `workspaces.read` and `payroll.read`.",
                "Rotate secrets quarterly via `/oauth/rotate` — the previous secret remains valid for 24 hours to avoid downtime.",
                "Verify webhook signatures with the `X-TrackYourSheets-Signature` header (HMAC-SHA256) before processing events.",
                "Respect per-organisation rate limits of 1,000 requests/minute and use the `Idempotency-Key` header for retries.",
            ],
        },
        {
            "title": "Core REST endpoints",
            "bullets": [
                "`GET /v1/workspaces` and `POST /v1/workspaces` for creating and managing agent pods.",
                "`GET /v1/payroll/runs` plus `POST /v1/payroll/runs/{id}/approve` for end-to-end payroll automation.",
                "`GET /v1/hr/employees` and `POST /v1/hr/documents` to sync directory data and push policy updates.",
                "`POST /v1/reports/export` to generate asynchronous CSV/PDF bundles for analytics and audits.",
            ],
        },
        {
            "title": "GraphQL highlights",
            "bullets": [
                "Query `organisation`, `workspaces`, `payrollRuns`, and `employees` with Relay-style pagination.",
                "Use mutations such as `createWorkspace`, `upsertProducer`, and `acknowledgeHRDocument` for transactional workflows.",
                "Send the `x-trackyoursheets-organisation` header when integrating multiple tenants from a single service account.",
                "Filter nodes by status, role, or updated timestamps to minimise payload size.",
            ],
        },
        {
            "title": "Webhook subscriptions",
            "bullets": [
                "Subscribe via `POST /v1/webhooks` and respond with `200 OK` within five seconds to avoid retries.",
                "Listen for `payroll.run.approved`, `hr.complaint.created`, `import.batch.completed`, and `report.export.ready` events.",
                "Store webhook IDs and secrets securely — they are required when disabling or rotating endpoints.",
                "Replay missed deliveries using the dashboard resend tool if your integration was temporarily offline.",
            ],
        },
    ]

    hosting_instructions = [
        "Build a static version of the API docs (e.g. MkDocs) and deploy it alongside the marketing site.",
        "Create a CNAME record pointing `api.trackyoursheets.com` at your docs CDN or reverse proxy.",
        "Issue TLS certificates for the subdomain and add uptime monitoring so expirations are caught early.",
        "Redirect legacy doc URLs to `/api-guide` so existing bookmarks continue working.",
    ]

    sample_flow = [
        "Request an access token every 45 minutes with the client credentials grant.",
        "Poll `GET /v1/payroll/runs?status=ready` to find new payouts and fetch line items for accounting.",
        "POST acknowledgements back to TrackYourSheets once payments are reconciled in your ERP.",
        "Subscribe to `payroll.run.approved` webhooks to trigger off-cycle exports instantly.",
    ]

    base_url = request.host_url.rstrip("/")

    return render_template(
        "api_guide.html",
        api_sections=api_sections,
        hosting_instructions=hosting_instructions,
        sample_flow=sample_flow,
        base_url=base_url,
    )


@main_bp.route("/dashboard")
@login_required
def dashboard():
    org_id = current_user.org_id
    workspace_ids = get_accessible_workspace_ids(current_user)
    workspaces = get_accessible_workspaces(current_user)

    requested_workspace_id = request.args.get("workspace_id", type=int)
    stored_workspace_id = session.get("active_workspace_id")
    active_workspace = None
    if requested_workspace_id and user_can_access_workspace(current_user, requested_workspace_id):
        active_workspace = next(
            (ws for ws in workspaces if ws.id == requested_workspace_id),
            None,
        )
        if active_workspace:
            session["active_workspace_id"] = active_workspace.id
    elif stored_workspace_id and user_can_access_workspace(current_user, stored_workspace_id):
        active_workspace = next(
            (ws for ws in workspaces if ws.id == stored_workspace_id),
            None,
        )
    elif workspaces:
        active_workspace = workspaces[0]
        session["active_workspace_id"] = active_workspace.id
    else:
        session.pop("active_workspace_id", None)

    import_query = ImportBatch.query.filter_by(org_id=org_id)
    if workspace_ids:
        import_query = import_query.filter(ImportBatch.workspace_id.in_(workspace_ids))
        imports = import_query.order_by(ImportBatch.created_at.desc()).limit(5).all()
    else:
        imports = []

    txn_query = CommissionTransaction.query.filter_by(org_id=org_id)
    if workspace_ids:
        txn_query = txn_query.filter(
            or_(
                CommissionTransaction.workspace_id.in_(workspace_ids),
                CommissionTransaction.batch.has(ImportBatch.workspace_id.in_(workspace_ids)),
            )
        )
        txns_total = txn_query.count()
    else:
        txns_total = 0
    audit_query = AuditLog.query.filter_by(org_id=org_id)
    audit_total = audit_query.count()
    recent_audit_events = (
        audit_query.order_by(AuditLog.ts.desc()).limit(5).all()
    )
    actor_ids = {
        event.actor_user_id
        for event in recent_audit_events
        if event.actor_user_id is not None
    }
    actor_lookup: dict[int, User] = {}
    if actor_ids:
        actor_lookup = {
            user.id: user
            for user in User.query.filter(User.id.in_(actor_ids)).all()
        }
    audit_entries = [
        _serialize_audit_event(event, actor_lookup)
        for event in recent_audit_events
    ]
    personal_note = None
    shared_note = None
    chat_messages = []
    chat_payload = []
    premium_totals = _calculate_premium_totals(
        org_id,
        list(workspace_ids) if workspace_ids else None,
    )
    if active_workspace:
        personal_note = (
            WorkspaceNote.query.filter_by(
                org_id=current_user.org_id,
                workspace_id=active_workspace.id,
                owner_id=current_user.id,
                scope="personal",
            )
            .order_by(WorkspaceNote.updated_at.desc())
            .first()
        )
        shared_note = (
            WorkspaceNote.query.filter_by(
                org_id=current_user.org_id,
                workspace_id=active_workspace.id,
                scope="shared",
            )
            .order_by(WorkspaceNote.updated_at.desc())
            .first()
        )
        chat_query = (
            WorkspaceChatMessage.query.filter_by(
                org_id=current_user.org_id,
                workspace_id=active_workspace.id,
            )
            .order_by(WorkspaceChatMessage.created_at.desc())
            .limit(50)
            .all()
        )
        chat_messages = list(reversed(chat_query))
        for message in chat_messages:
            message.rendered_content = _render_chat_message_html(message)
        chat_payload = [_serialize_chat_message(message) for message in chat_messages]

    return render_template(
        "dashboard.html",
        imports=imports,
        txns_total=txns_total,
        audit_entries=audit_entries,
        audit_total=audit_total,
        workspaces=workspaces,
        active_workspace=active_workspace,
        personal_note=personal_note,
        shared_note=shared_note,
        personal_note_meta=_note_meta(personal_note),
        shared_note_meta=_note_meta(shared_note),
        chat_messages=chat_messages,
        chat_messages_payload=chat_payload,
        premium_totals=premium_totals,
        premium_currency=getattr(current_user, "compensation_currency", None)
        or "USD",
    )


@main_bp.route("/workspaces/switch", methods=["POST"])
@login_required
def switch_workspace():
    workspace_id = request.form.get("workspace_id", type=int)
    next_url = request.form.get("next") or request.referrer or url_for("main.dashboard")
    if workspace_id and user_can_access_workspace(current_user, workspace_id):
        session["active_workspace_id"] = workspace_id
    else:
        flash("You do not have access to that workspace.", "danger")
    return redirect(next_url)


@main_bp.route("/workspaces/join", methods=["POST"])
@login_required
def join_workspace():
    workspace_id = request.form.get("workspace_id", type=int)
    next_url = request.form.get("next") or url_for("main.settings")
    if not workspace_id:
        flash("Select a workspace to join.", "danger")
        return redirect(next_url)
    workspace = Workspace.query.filter_by(id=workspace_id, org_id=current_user.org_id).first()
    if not workspace:
        flash("Workspace not found.", "danger")
        return redirect(next_url)
    current_user.record_workspace_membership(workspace, role=current_user.role)
    db.session.commit()
    session["active_workspace_id"] = workspace.id
    flash(f"Joined {workspace.name}.", "success")
    return redirect(next_url)


@main_bp.route("/workspaces/<int:workspace_id>/leave", methods=["POST"])
@login_required
def leave_workspace(workspace_id: int):
    next_url = request.form.get("next") or url_for("main.settings")
    membership = next(
        (
            m
            for m in getattr(current_user, "workspace_memberships", []) or []
            if m.workspace_id == workspace_id
        ),
        None,
    )
    if not membership:
        flash("You are not assigned to that workspace.", "warning")
        return redirect(next_url)
    if (
        current_user.role == "agent"
        and getattr(current_user, "managed_workspace", None)
        and current_user.managed_workspace.id == workspace_id
    ):
        flash("Agents must remain assigned to their managed workspace.", "danger")
        return redirect(next_url)
    if (
        current_user.role == "producer"
        and getattr(current_user, "producer", None)
        and current_user.producer.workspace_id == workspace_id
    ):
        flash("You cannot leave your primary producer workspace.", "danger")
        return redirect(next_url)
    db.session.delete(membership)
    db.session.commit()
    if session.get("active_workspace_id") == workspace_id:
        session.pop("active_workspace_id", None)
    flash("Workspace access removed.", "info")
    return redirect(next_url)


@main_bp.route("/audit")
@login_required
def audit_trail():
    if current_user.role not in {"owner", "admin", "agent"}:
        flash("You do not have access to the audit trail.", "danger")
        return redirect(url_for("main.dashboard"))

    org_id = current_user.org_id
    search_term = (request.args.get("q") or "").strip()
    actor_filter = request.args.get("actor", type=int)

    base_query = AuditLog.query.filter_by(org_id=org_id)
    if search_term:
        like_term = f"%{search_term}%"
        base_query = base_query.filter(
            or_(AuditLog.action.ilike(like_term), AuditLog.entity.ilike(like_term))
        )
    if actor_filter:
        base_query = base_query.filter(AuditLog.actor_user_id == actor_filter)

    total_matches = base_query.count()
    ordered_query = base_query.order_by(AuditLog.ts.desc())
    audit_records = ordered_query.limit(200).all()

    actor_ids = {
        record.actor_user_id
        for record in audit_records
        if record.actor_user_id is not None
    }
    actor_lookup: dict[int, User] = {}
    if actor_ids:
        actor_lookup = {
            user.id: user
            for user in User.query.filter(User.id.in_(actor_ids)).all()
        }

    entries = [
        _serialize_audit_event(record, actor_lookup)
        for record in audit_records
    ]

    actors = (
        User.query.filter_by(org_id=org_id)
        .order_by(User.email.asc())
        .all()
    )

    return render_template(
        "audit.html",
        entries=entries,
        actors=actors,
        search=search_term,
        actor_filter=actor_filter,
        total_matches=total_matches,
        result_limit=200,
    )


@main_bp.route("/onboarding")
@login_required
def onboarding():
    return render_template("onboarding.html")


@main_bp.route("/guide")
@login_required
def guide():
    sections = get_role_guides()
    tour_steps = []
    for step in get_interactive_tour():
        step_copy = {key: value for key, value in step.items() if key not in {"cta_endpoint", "cta_kwargs"}}
        endpoint = step.get("cta_endpoint")
        kwargs = step.get("cta_kwargs", {})
        if endpoint:
            step_copy["cta_url"] = url_for(endpoint, **kwargs)
        tour_steps.append(step_copy)
    back_to = request.args.get("back_to")
    for section in sections:
        for step in section.get("steps", []):
            print("DEBUG STEP:", step)
            print("DEBUG TYPE OF step['items']:", type(step.get("items")))
    return render_template("guide.html", sections=sections, tour_steps=tour_steps, back_to=back_to)


@main_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    org = Organization.query.get_or_404(current_user.org_id)
    subscription = (
        Subscription.query.filter_by(org_id=org.id)
        .order_by(Subscription.created_at.desc())
        .first()
    )
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.tier.asc()).all()
    plan_cards = build_plan_details(plans)
    plan_details_map = {detail["id"]: detail for detail in plan_cards}
    current_plan_detail = plan_details_map.get(org.plan_id)
    plan_limits = current_plan_detail.get("limits") if current_plan_detail else None
    can_manage_plan = current_user.role in {"owner", "admin", "agent"}
    stripe_gateway = current_app.extensions.get("stripe_gateway")
    stripe_enabled = bool(stripe_gateway and getattr(stripe_gateway, "is_configured", False) and stripe_gateway.is_configured)

    if stripe_gateway and not getattr(stripe_gateway, "is_configured", False):
        stripe_enabled = False

    if request.method == "POST":
        intent = request.form.get("intent")
        if intent == "profile":
            new_email_raw = (request.form.get("email") or "").strip()
            display_name = (request.form.get("display_name") or "").strip()
            new_password = request.form.get("new_password") or ""
            confirm_password = request.form.get("confirm_password") or ""
            errors = False
            pending_password_hash: str | None = None

            if not new_email_raw:
                flash("Email is required.", "danger")
                errors = True
            else:
                normalized_email = new_email_raw.lower()
                current_email_normalized = (current_user.email or "").lower()
                if normalized_email != current_email_normalized:
                    conflict = (
                        User.query.filter(func.lower(User.email) == normalized_email)
                        .filter(User.id != current_user.id)
                        .first()
                    )
                    if conflict:
                        flash("That email is already in use.", "danger")
                        errors = True
                if not errors:
                    current_user.email = new_email_raw

            if display_name and getattr(current_user, "producer", None):
                current_user.producer.display_name = display_name

            if new_password:
                if len(new_password) < 8:
                    flash("Passwords must be at least 8 characters.", "danger")
                    errors = True
                elif new_password != confirm_password:
                    flash("Passwords do not match.", "danger")
                    errors = True
                else:
                    pending_password_hash = generate_password_hash(new_password)

            if errors:
                db.session.rollback()
            elif pending_password_hash:
                code = current_user.generate_two_factor_code()
                db.session.commit()
                send_two_factor_code_email(
                    current_user.email,
                    code,
                    intent="password_change",
                )
                session["password_change"] = {
                    "user_id": current_user.id,
                    "password_hash": pending_password_hash,
                }
                flash(
                    "Enter the verification code we emailed you to confirm your new password.",
                    "info",
                )
                return redirect(url_for("auth.password_change_verify"))
            else:
                db.session.commit()
                flash("Profile updated successfully.", "success")
            return redirect(url_for("main.settings"))

        if intent == "plan":
            if not can_manage_plan:
                flash("You do not have permission to change the plan.", "danger")
                return redirect(url_for("main.settings"))

            plan_id_raw = request.form.get("plan_id")
            try:
                selected_plan_id = int(plan_id_raw)
            except (TypeError, ValueError):
                flash("Select a valid plan.", "danger")
                return redirect(url_for("main.settings"))

            plan = SubscriptionPlan.query.filter_by(id=selected_plan_id).first()
            if not plan:
                flash("Selected plan could not be found.", "danger")
                return redirect(url_for("main.settings"))

            if org.plan_id == plan.id:
                flash("You're already on this plan.", "info")
                return redirect(url_for("main.settings"))

            if not stripe_enabled or not stripe_gateway:
                flash(
                    "Stripe billing is not configured. Email contact@trackyoursheets.com to change plans.",
                    "danger",
                )
                return redirect(url_for("main.settings"))

            active_users = (
                User.query.filter_by(org_id=org.id, status="active").count() or 1
            )

            success_url = url_for("main.checkout_complete", _external=True)
            success_url = f"{success_url}?session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = url_for("main.settings", _external=True)

            try:
                checkout_url = stripe_gateway.create_checkout_session(
                    organization=org,
                    plan=plan,
                    quantity=active_users,
                    success_url=success_url,
                    cancel_url=cancel_url,
                    client_reference_id=str(org.id),
                    metadata={
                        "flow": "plan_change",
                        "initiated_by": current_user.email,
                    },
                    subscription_metadata={
                        "plan_id": str(plan.id),
                        "flow": "plan_change",
                        "initiated_by": current_user.email,
                    },
                )
            except Exception:
                current_app.logger.exception(
                    "Stripe checkout creation failed for plan change"
                )
                flash(
                    "We couldn't start Stripe checkout. Please try again or email contact@trackyoursheets.com.",
                    "danger",
                )
                return redirect(url_for("main.settings"))

            flash("Redirecting to Stripe to confirm your subscription update.", "info")
            return redirect(checkout_url)


        if intent == "redeem":
            if not can_manage_plan:
                flash("You do not have permission to redeem coupons.", "danger")
                return redirect(url_for("main.settings"))

            code = (request.form.get("coupon_code") or "").strip()
            if not code:
                flash("Enter a coupon code to redeem.", "danger")
                return redirect(url_for("main.settings"))

            coupon = (
                Coupon.query.filter(func.lower(Coupon.internal_code) == code.lower())
                .first()
            )
            if not coupon:
                flash("Coupon code not recognized.", "danger")
                return redirect(url_for("main.settings"))

            now = datetime.utcnow()
            if coupon.expires_at and coupon.expires_at < now:
                flash("This coupon has expired.", "danger")
                return redirect(url_for("main.settings"))

            if coupon.max_redemptions is not None and coupon.max_redemptions <= 0:
                flash("This coupon has already been fully redeemed.", "danger")
                return redirect(url_for("main.settings"))

            applied_plan = None
            if coupon.applies_to_plan:
                applied_plan = (
                    SubscriptionPlan.query.filter(
                        func.lower(SubscriptionPlan.name)
                        == coupon.applies_to_plan.lower()
                    )
                    .first()
                )
                if applied_plan:
                    org.plan_id = applied_plan.id
                    if subscription:
                        subscription.plan = applied_plan.name
                elif coupon.applies_to_plan:
                    flash(
                        "Coupon references a plan that is no longer available.",
                        "warning",
                    )

            extension_days = coupon.trial_extension_days or 0
            if extension_days:
                trial_base = org.trial_ends_at if org.trial_ends_at and org.trial_ends_at > now else now
                new_trial_end = trial_base + timedelta(days=extension_days)
                org.trial_ends_at = new_trial_end
                if subscription:
                    subscription.status = "trialing"
                    subscription.trial_end = new_trial_end
                else:
                    subscription = Subscription(
                        organization=org,
                        plan=(
                            applied_plan.name
                            if applied_plan
                            else (org.plan.name if org.plan else "Trial")
                        ),
                        status="trialing",
                        trial_end=new_trial_end,
                    )
                    db.session.add(subscription)

            if coupon.max_redemptions is not None:
                coupon.max_redemptions -= 1

            db.session.commit()
            flash(
                f"Coupon {code.upper()} applied successfully.",
                "success",
            )
            recipients = _billing_contacts(org)
            if current_user.email and current_user.wants_notification("plan_updates"):
                recipients.append(current_user.email)
            recipients = _dedupe_emails(recipients)
            if recipients:
                message_lines = [
                    f"Organisation: {org.name}",
                    f"Updated by: {current_user.email}",
                    f"Coupon code: {code.upper()}",
                ]
                if coupon.trial_extension_days:
                    message_lines.append(
                        f"Trial extended by {coupon.trial_extension_days} day(s)"
                    )
                if applied_plan:
                    message_lines.append(f"Applied plan: {applied_plan.name}")
                send_notification_email(
                    recipients=recipients,
                    subject=f"Coupon {code.upper()} applied",
                    body="\n".join(message_lines),
                    metadata={"org_id": org.id, "coupon": code.upper()},
                )
            return redirect(url_for("main.settings"))

        if intent == "notifications":
            selected = request.form.getlist("notifications")
            two_factor_enabled = bool(request.form.get("two_factor_enabled"))
            current_user.set_notification_preferences(selected)
            current_user.two_factor_enabled = two_factor_enabled
            if not two_factor_enabled:
                current_user.clear_two_factor_challenge()
            db.session.commit()
            flash("Notification preferences updated.", "success")
            return redirect(url_for("main.settings"))

    usage_snapshot = {
        "users": User.query.filter_by(org_id=org.id).filter(User.status == "active").count(),
        "workspaces": Workspace.query.filter_by(org_id=org.id).count(),
        "producers": Producer.query.filter_by(org_id=org.id).count(),
        "carriers": Carrier.query.filter_by(org_id=org.id).count(),
    }
    included_seats = org.plan.included_users if org.plan else None
    if included_seats is None and org.plan and org.plan.max_users:
        included_seats = org.plan.max_users
    extra_seat_price = org.plan.extra_user_price if org.plan else None
    seats_remaining = None
    if included_seats is not None:
        seats_remaining = max(included_seats - usage_snapshot["users"], 0)
    accessible_workspaces = get_accessible_workspaces(current_user)
    joined_workspace_ids = {ws.id for ws in accessible_workspaces}
    all_workspaces = (
        Workspace.query.filter_by(org_id=org.id)
        .order_by(Workspace.name.asc())
        .all()
    )
    joinable_workspaces = [
        ws for ws in all_workspaces if ws.id not in joined_workspace_ids
    ]

    stripe_publishable_key = None
    if stripe_gateway and getattr(stripe_gateway, "publishable_key", None):
        stripe_publishable_key = stripe_gateway.publishable_key
    elif current_app.config.get("STRIPE_PUBLISHABLE_KEY"):
        stripe_publishable_key = current_app.config.get("STRIPE_PUBLISHABLE_KEY")

    stripe_mode = getattr(stripe_gateway, "mode", None) if stripe_enabled else None

    return render_template(
        "settings.html",
        plans=plans,
        organization=org,
        subscription=subscription,
        can_manage_plan=can_manage_plan,
        usage_snapshot=usage_snapshot,
        seat_limit=included_seats,
        seats_remaining=seats_remaining,
        plan_details_map=plan_details_map,
        current_plan_detail=current_plan_detail,
        plan_limits=plan_limits,
        stripe_enabled=stripe_enabled,
        stripe_mode=stripe_mode,
        stripe_publishable_key=stripe_publishable_key,
        notification_options=DEFAULT_NOTIFICATION_PREFERENCES,
        user_notifications=current_user.notification_preferences
        or DEFAULT_NOTIFICATION_PREFERENCES,
        two_factor_enabled=current_user.two_factor_enabled,
        accessible_workspaces=accessible_workspaces,
        joinable_workspaces=joinable_workspaces,
        extra_seat_price=extra_seat_price,
    )


@main_bp.route("/messages", methods=["GET", "POST"])
@login_required
def messages_home():
    org = Organization.query.get_or_404(current_user.org_id)
    teammates = (
        User.query.filter_by(org_id=org.id)
        .filter(User.id != current_user.id)
        .order_by(User.first_name.asc(), User.last_name.asc())
        .all()
    )

    if request.method == "POST":
        participant_ids = {
            current_user.id,
            *{
                int(value)
                for value in request.form.getlist("participants")
                if value.isdigit()
            },
        }
        participant_users = (
            User.query.filter(User.id.in_(participant_ids))
            .filter_by(org_id=org.id)
            .all()
        )
        if len(participant_users) != len(participant_ids):
            flash("Select teammates from your organisation.", "danger")
            return redirect(url_for("main.messages_home"))

        is_group = len(participant_users) > 2
        name = (request.form.get("name") or "").strip()
        if not name:
            if is_group:
                name = ", ".join(
                    sorted(
                        {user.full_name or user.email for user in participant_users}
                    )
                )
            else:
                other = next(user for user in participant_users if user.id != current_user.id)
                name = other.full_name or other.email

        initial_message = (request.form.get("message") or "").strip()

        thread = MessageThread(
            org_id=org.id,
            name=name,
            is_group=is_group,
            created_by_id=current_user.id,
            last_message_at=datetime.utcnow() if initial_message else None,
        )
        db.session.add(thread)
        db.session.flush()

        for user in participant_users:
            participant = MessageParticipant(
                org_id=org.id,
                thread_id=thread.id,
                user_id=user.id,
                role="owner" if user.id == current_user.id else "member",
            )
            db.session.add(participant)

        if initial_message:
            message = ConversationMessage(
                org_id=org.id,
                thread_id=thread.id,
                author_id=current_user.id,
                content=initial_message,
            )
            db.session.add(message)

        db.session.commit()
        flash("Conversation created.", "success")
        return redirect(url_for("main.view_message_thread", thread_id=thread.id))

    participant_thread_ids = (
        MessageParticipant.query.with_entities(MessageParticipant.thread_id)
        .filter_by(org_id=org.id, user_id=current_user.id)
        .subquery()
    )
    threads = (
        MessageThread.query.filter_by(org_id=org.id)
        .filter(MessageThread.id.in_(participant_thread_ids))
        .options(
            joinedload(MessageThread.participants).joinedload(MessageParticipant.user),
            joinedload(MessageThread.messages).joinedload(ConversationMessage.author),
        )
        .order_by(MessageThread.last_message_at.desc().nullslast(), MessageThread.created_at.desc())
        .all()
    )

    for thread in threads:
        participant_names = [
            _display_user_name(participant.user)
            for participant in thread.participants
            if participant.user_id != current_user.id and participant.user
        ]
        thread.display_participants = participant_names or ["Just you"]
        thread_preview = None
        if thread.messages:
            latest = max(thread.messages, key=lambda msg: msg.created_at or datetime.min)
            thread_preview = {
                "author": _display_user_name(latest.author),
                "timestamp": latest.created_at,
                "body": latest.content[:120] + ("…" if len(latest.content or "") > 120 else ""),
            }
        thread.preview = thread_preview

    return render_template(
        "messages/index.html",
        threads=threads,
        teammates=teammates,
    )


@main_bp.route("/messages/<int:thread_id>", methods=["GET", "POST"])
@login_required
def view_message_thread(thread_id: int):
    thread = (
        MessageThread.query.filter_by(id=thread_id, org_id=current_user.org_id)
        .options(
            joinedload(MessageThread.participants).joinedload(MessageParticipant.user),
            joinedload(MessageThread.messages).joinedload(ConversationMessage.author),
        )
        .first_or_404()
    )
    participant_ids = {participant.user_id for participant in thread.participants}
    if current_user.id not in participant_ids:
        abort(403)

    if request.method == "POST":
        content = (request.form.get("content") or "").strip()
        if not content:
            flash("Message cannot be empty.", "danger")
            return redirect(url_for("main.view_message_thread", thread_id=thread.id))
        message = ConversationMessage(
            org_id=current_user.org_id,
            thread_id=thread.id,
            author_id=current_user.id,
            content=content,
        )
        thread.last_message_at = datetime.utcnow()
        db.session.add(message)
        db.session.add(thread)
        db.session.commit()
        flash("Message sent.", "success")
        return redirect(url_for("main.view_message_thread", thread_id=thread.id))

    messages = sorted(thread.messages, key=lambda msg: msg.created_at or datetime.min)
    for message in messages:
        message.rendered_content = _render_chat_message_html(message)

    return render_template(
        "messages/thread.html",
        thread=thread,
        messages=messages,
        participants_label=", ".join(
            _display_user_name(participant.user)
            for participant in thread.participants
            if participant.user
        ),
    )


@main_bp.route("/billing/portal", methods=["POST"])
@login_required
def open_billing_portal():
    if current_user.role not in {"owner", "admin", "agent"}:
        abort(403)
    org = Organization.query.get_or_404(current_user.org_id)
    stripe_gateway = current_app.extensions.get("stripe_gateway")
    if not stripe_gateway or not getattr(stripe_gateway, "is_configured", False):
        flash("Stripe billing portal is not configured.", "warning")
        return redirect(url_for("main.settings"))
    try:
        portal_url = stripe_gateway.create_billing_portal_session(
            organization=org,
            return_url=url_for("main.settings", _external=True),
        )
    except Exception as exc:  # pragma: no cover - Stripe errors logged only
        current_app.logger.error("Stripe billing portal error", exc_info=exc)
        flash(
            "We couldn't open the Stripe billing portal. Please try again or email contact@trackyoursheets.com.",
            "danger",
        )
        return redirect(url_for("main.settings"))
    return redirect(portal_url)


@main_bp.route("/billing/checkout/complete")
@login_required
def checkout_complete():
    session_id = request.args.get("session_id")
    if not session_id:
        flash("Checkout session missing. Email contact@trackyoursheets.com if this persists.", "danger")
        return redirect(url_for("main.settings"))

    stripe_gateway = current_app.extensions.get("stripe_gateway")
    if not stripe_gateway or not getattr(stripe_gateway, "is_configured", False):
        flash("Stripe integration is not configured. Email contact@trackyoursheets.com for assistance.", "danger")
        return redirect(url_for("main.settings"))

    try:
        session = stripe_gateway.retrieve_checkout_session(session_id)
    except Exception:
        current_app.logger.exception("Failed to retrieve Stripe checkout session")
        flash("We couldn't verify the Stripe checkout session. Email contact@trackyoursheets.com for assistance.", "danger")
        return redirect(url_for("main.settings"))

    if getattr(session, "status", None) != "complete":
        flash("Checkout has not completed yet. Please finish payment in Stripe.", "warning")
        return redirect(url_for("main.settings"))

    org = Organization.query.get_or_404(current_user.org_id)

    session_customer = getattr(session, "customer", None)
    if org.stripe_customer_id and session_customer and org.stripe_customer_id != session_customer:
        flash("This checkout session does not belong to your organisation.", "danger")
        return redirect(url_for("main.settings"))
    if session_customer and not org.stripe_customer_id:
        org.stripe_customer_id = session_customer

    subscription_record = Subscription.query.filter_by(org_id=org.id).first()
    if not subscription_record:
        subscription_record = Subscription(org_id=org.id)
        db.session.add(subscription_record)

    stripe_subscription = getattr(session, "subscription", None)
    metadata = {}
    if stripe_subscription and getattr(stripe_subscription, "metadata", None):
        metadata = dict(stripe_subscription.metadata)
    elif getattr(session, "metadata", None):
        metadata = dict(session.metadata)

    plan_id = metadata.get("plan_id")
    plan_name = metadata.get("plan") or metadata.get("plan_name")

    resolved_plan = None
    if plan_id and str(plan_id).isdigit():
        resolved_plan = SubscriptionPlan.query.get(int(plan_id))
    if not resolved_plan and plan_name:
        resolved_plan = SubscriptionPlan.query.filter(func.lower(SubscriptionPlan.name) == plan_name.lower()).first()

    if resolved_plan:
        org.plan_id = resolved_plan.id
        plan_name = resolved_plan.name

    subscription_record.plan = plan_name or subscription_record.plan
    subscription_record.status = (
        getattr(stripe_subscription, "status", None)
        or getattr(session, "status", None)
        or subscription_record.status
        or "active"
    )
    subscription_record.stripe_sub_id = (
        getattr(stripe_subscription, "id", None) or subscription_record.stripe_sub_id
    )

    trial_end_ts = getattr(stripe_subscription, "trial_end", None)
    if trial_end_ts:
        subscription_record.trial_end = datetime.utcfromtimestamp(trial_end_ts)
        org.trial_ends_at = subscription_record.trial_end
    else:
        subscription_record.trial_end = None
        org.trial_ends_at = None

    db.session.commit()

    quantity = None
    line_items = getattr(session, "line_items", None)
    if line_items and getattr(line_items, "data", None):
        first_item = line_items.data[0]
        quantity = getattr(first_item, "quantity", None)

    recipients = _billing_contacts(org)
    if current_user.email and current_user.wants_notification("plan_updates"):
        recipients.append(current_user.email)
    recipients = _dedupe_emails(recipients)

    if recipients:
        message_lines = [
            f"Organisation: {org.name}",
            f"Updated by: {current_user.email}",
            f"Plan: {plan_name or subscription_record.plan or 'Unknown'}",
        ]
        if quantity:
            message_lines.append(f"Seats confirmed: {quantity}")

        send_notification_email(
            recipients=recipients,
            subject=f"Stripe checkout completed for {org.name}",
            body="\n".join(message_lines),
            metadata={"org_id": org.id, "session_id": session_id},
        )

    flash("Subscription update confirmed. Thanks for completing checkout!", "success")
    return redirect(url_for("main.settings"))


@main_bp.route("/notes/<scope>", methods=["POST"])
@login_required
def save_note(scope: str):
    if scope not in {"personal", "shared"}:
        abort(400)

    data = request.get_json() or {}
    workspace_id = data.get("workspace_id")
    content = data.get("content", "")

    try:
        workspace_id = int(workspace_id)
    except (TypeError, ValueError):
        abort(400)

    if not user_can_access_workspace(current_user, workspace_id):
        abort(403)

    workspace = Workspace.query.filter_by(
        id=workspace_id,
        org_id=current_user.org_id,
    ).first_or_404()

    if scope == "personal":
        note = WorkspaceNote.query.filter_by(
            org_id=current_user.org_id,
            workspace_id=workspace.id,
            owner_id=current_user.id,
            scope="personal",
        ).first()
        if not note:
            note = WorkspaceNote(
                org_id=current_user.org_id,
                workspace_id=workspace.id,
                office_id=workspace.office_id,
                owner_id=current_user.id,
                scope="personal",
                owner=current_user,
            )
            db.session.add(note)
    else:
        note = WorkspaceNote.query.filter_by(
            org_id=current_user.org_id,
            workspace_id=workspace.id,
            scope="shared",
        ).first()
        if not note:
            note = WorkspaceNote(
                org_id=current_user.org_id,
                workspace_id=workspace.id,
                office_id=workspace.office_id,
                scope="shared",
                owner_id=current_user.id,
                owner=current_user,
            )
            db.session.add(note)

    note.owner = current_user

    note.content = content
    db.session.commit()
    db.session.refresh(note)

    if scope == "shared":
        snippet = (content or "").strip()
        if len(snippet) > 140:
            snippet = snippet[:137].rstrip() + "..."
        summary = snippet or "Shared workspace notes were updated."
        recipients = _workspace_recipients(
            workspace,
            preference="workspace_updates",
            exclude_user_id=current_user.id,
        )
        if recipients:
            send_workspace_update_notification(
                recipients,
                workspace=workspace,
                actor=current_user,
                summary=summary,
            )

    return jsonify(
        {
            "status": "saved",
            "updated_at": note.updated_at.isoformat() if note.updated_at else None,
            "updated_at_display": _format_timestamp(note.updated_at),
            "editor": _display_user_name(note.owner),
        }
    )


@main_bp.route("/chat/<int:workspace_id>/messages", methods=["GET", "POST"])
@login_required
def workspace_chat(workspace_id: int):
    if not user_can_access_workspace(current_user, workspace_id):
        abort(403)

    workspace = Workspace.query.filter_by(
        id=workspace_id,
        org_id=current_user.org_id,
    ).first_or_404()

    if request.method == "POST":
        data = request.get_json() or {}
        content = (data.get("content") or "").strip()
        if not content:
            abort(400, description="Message content is required.")

        message = WorkspaceChatMessage(
            org_id=current_user.org_id,
            workspace_id=workspace_id,
            author_id=current_user.id,
            content=content,
        )
        db.session.add(message)
        db.session.commit()
        db.session.refresh(message)

        snippet = message.content.strip()
        if len(snippet) > 140:
            snippet = snippet[:137].rstrip() + "..."
        recipients = _workspace_recipients(
            workspace,
            preference="new_entries",
            exclude_user_id=current_user.id,
        )
        if recipients:
            send_workspace_chat_notification(
                recipients,
                workspace=workspace,
                actor=current_user,
                message=snippet,
            )
        return jsonify(_serialize_chat_message(message)), 201

    messages = (
        WorkspaceChatMessage.query.filter_by(
            org_id=current_user.org_id,
            workspace_id=workspace_id,
        )
        .order_by(WorkspaceChatMessage.created_at.asc())
        .limit(100)
        .all()
    )
    return jsonify([_serialize_chat_message(message) for message in messages])
