from datetime import datetime, timedelta

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
)
from flask_login import current_user, login_required

from sqlalchemy import func, or_

from .models import (
    AuditLog,
    CommissionTransaction,
    ImportBatch,
    Workspace,
    WorkspaceNote,
    WorkspaceChatMessage,
    Organization,
    SubscriptionPlan,
    Subscription,
    Coupon,
    User,
    Producer,
)
from .guides import get_role_guides, get_interactive_tour
from .workspaces import get_accessible_workspace_ids, get_accessible_workspaces, user_can_access_workspace
from . import db
from .nylas_email import send_notification_email


main_bp = Blueprint("main", __name__)


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


def _billing_contacts(organization) -> list[str]:
    if not organization or not getattr(organization, "users", None):
        return []
    emails = []
    for user in organization.users:
        if user.role in {"owner", "admin"} and getattr(user, "email", None):
            emails.append(user.email)
    return emails


def _serialize_chat_message(message: WorkspaceChatMessage) -> dict:
    return {
        "id": message.id,
        "content": message.content,
        "author": _display_user_name(message.author),
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "created_at_display": _format_timestamp(message.created_at),
    }


@main_bp.route("/")
@login_required
def dashboard():
    org_id = current_user.org_id
    workspace_ids = get_accessible_workspace_ids(current_user)
    workspaces = get_accessible_workspaces(current_user)

    requested_workspace_id = request.args.get("workspace_id", type=int)
    active_workspace = None
    if requested_workspace_id and user_can_access_workspace(current_user, requested_workspace_id):
        active_workspace = next(
            (ws for ws in workspaces if ws.id == requested_workspace_id),
            None,
        )
    elif workspaces:
        active_workspace = workspaces[0]

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
    audit_events = (
        AuditLog.query.filter_by(org_id=org_id)
        .order_by(AuditLog.ts.desc())
        .limit(5)
        .all()
    )
    personal_note = None
    shared_note = None
    chat_messages = []
    chat_payload = []
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
        chat_payload = [_serialize_chat_message(message) for message in chat_messages]

    return render_template(
        "dashboard.html",
        imports=imports,
        txns_total=txns_total,
        audit_events=audit_events,
        workspaces=workspaces,
        active_workspace=active_workspace,
        personal_note=personal_note,
        shared_note=shared_note,
        personal_note_meta=_note_meta(personal_note),
        shared_note_meta=_note_meta(shared_note),
        chat_messages=chat_messages,
        chat_messages_payload=chat_payload,
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
                    current_user.set_password(new_password)

            if errors:
                db.session.rollback()
            else:
                db.session.commit()
                flash("Profile updated successfully.", "success")
            return redirect(url_for("main.settings"))

        if intent == "plan":
            if not can_manage_plan:
                flash("You do not have permission to change plans.", "danger")
                return redirect(url_for("main.settings"))

            plan_id_raw = request.form.get("plan_id")
            try:
                selected_plan_id = int(plan_id_raw)
            except (TypeError, ValueError):
                flash("Select a plan to continue.", "danger")
                return redirect(url_for("main.settings"))

            plan = SubscriptionPlan.query.filter_by(id=selected_plan_id).first()
            if not plan:
                flash("Selected plan could not be found.", "danger")
                return redirect(url_for("main.settings"))

            if request.form.get("checkout_with_stripe"):
                if not stripe_enabled:
                    flash("Stripe checkout is not configured for this environment.", "warning")
                    return redirect(url_for("main.settings"))
                seat_count = max(User.query.filter_by(org_id=org.id).count(), 1)
                success_url = url_for("main.settings", _external=True)
                cancel_url = success_url
                try:
                    checkout_url = stripe_gateway.create_checkout_session(
                        organization=org,
                        plan=plan,
                        quantity=seat_count,
                        success_url=success_url,
                        cancel_url=cancel_url,
                    )
                except Exception as exc:  # pragma: no cover - Stripe errors logged only
                    current_app.logger.error("Stripe checkout session failed", exc_info=exc)
                    flash(
                        "We couldn't start the Stripe checkout session. Please try again or contact support.",
                        "danger",
                    )
                    return redirect(url_for("main.settings"))
                return redirect(checkout_url)

            org.plan_id = plan.id
            if subscription:
                subscription.plan = plan.name
                if subscription.status not in {"active", "trialing"}:
                    subscription.status = "active"
            else:
                subscription = Subscription(
                    organization=org,
                    plan=plan.name,
                    status="active",
                )
                db.session.add(subscription)

            db.session.commit()
            flash(f"Plan updated to {plan.name}.", "success")
            recipients = _billing_contacts(org) or [current_user.email]
            message_lines = [
                f"Organisation: {org.name}",
                f"Updated by: {current_user.email}",
                f"New plan: {plan.name}",
            ]
            send_notification_email(
                recipients=recipients,
                subject=f"Plan updated to {plan.name}",
                body="\n".join(message_lines),
                metadata={"org_id": org.id, "plan_id": plan.id},
            )
            return redirect(url_for("main.settings"))

        if intent == "trial":
            if not can_manage_plan:
                flash("You do not have permission to manage the trial.", "danger")
                return redirect(url_for("main.settings"))

            action = request.form.get("action", "set")
            if action == "end":
                org.trial_ends_at = datetime.utcnow()
                if subscription:
                    subscription.status = "active"
                    subscription.trial_end = None
                db.session.commit()
                flash("Trial ended. Billing continues on the selected plan.", "info")
                recipients = _billing_contacts(org) or [current_user.email]
                send_notification_email(
                    recipients=recipients,
                    subject=f"Trial ended for {org.name}",
                    body="\n".join(
                        [
                            f"Organisation: {org.name}",
                            f"Updated by: {current_user.email}",
                            "Trial status: Ended",
                        ]
                    ),
                    metadata={"org_id": org.id, "action": "trial_end"},
                )
                return redirect(url_for("main.settings"))

            trial_days = request.form.get("trial_days")
            try:
                trial_days_value = int(trial_days)
            except (TypeError, ValueError):
                flash("Enter the number of days to grant for the trial.", "danger")
                return redirect(url_for("main.settings"))

            if trial_days_value < 1:
                flash("Trial days must be at least 1.", "danger")
                return redirect(url_for("main.settings"))

            new_trial_end = datetime.utcnow() + timedelta(days=trial_days_value)
            org.trial_ends_at = new_trial_end
            if subscription:
                subscription.status = "trialing"
                subscription.trial_end = new_trial_end
            else:
                subscription = Subscription(
                    organization=org,
                    plan=org.plan.name if org.plan else "Trial",
                    status="trialing",
                    trial_end=new_trial_end,
                )
                db.session.add(subscription)

            db.session.commit()
            flash(
                f"Trial extended through {new_trial_end.strftime('%b %d, %Y')}.",
                "success",
            )
            recipients = _billing_contacts(org) or [current_user.email]
            send_notification_email(
                recipients=recipients,
                subject=f"Trial updated for {org.name}",
                body="\n".join(
                    [
                        f"Organisation: {org.name}",
                        f"Updated by: {current_user.email}",
                        f"New trial end: {new_trial_end.strftime('%b %d, %Y')}",
                    ]
                ),
                metadata={"org_id": org.id, "action": "trial_extend"},
            )
            return redirect(url_for("main.settings"))

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
            recipients = _billing_contacts(org) or [current_user.email]
            message_lines = [
                f"Organisation: {org.name}",
                f"Updated by: {current_user.email}",
                f"Coupon code: {code.upper()}",
            ]
            if coupon.trial_extension_days:
                message_lines.append(f"Trial extended by {coupon.trial_extension_days} day(s)")
            if applied_plan:
                message_lines.append(f"Applied plan: {applied_plan.name}")
            send_notification_email(
                recipients=recipients,
                subject=f"Coupon {code.upper()} applied",
                body="\n".join(message_lines),
                metadata={"org_id": org.id, "coupon": code.upper()},
            )
            return redirect(url_for("main.settings"))

    trial_days_remaining = None
    if org.trial_ends_at:
        delta = org.trial_ends_at - datetime.utcnow()
        trial_days_remaining = max(delta.days + (1 if delta.seconds > 0 else 0), 0)

    usage_snapshot = {
        "users": User.query.filter_by(org_id=org.id).count(),
        "workspaces": Workspace.query.filter_by(org_id=org.id).count(),
        "producers": Producer.query.filter_by(org_id=org.id).count(),
    }

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
        trial_days_remaining=trial_days_remaining,
        can_manage_plan=can_manage_plan,
        usage_snapshot=usage_snapshot,
        stripe_enabled=stripe_enabled,
        stripe_mode=stripe_mode,
        stripe_publishable_key=stripe_publishable_key,
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
            "We couldn't open the Stripe billing portal. Please try again or contact support.",
            "danger",
        )
        return redirect(url_for("main.settings"))
    return redirect(portal_url)


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
