from flask import Blueprint, render_template, request, jsonify, abort, url_for
from flask_login import current_user, login_required

from sqlalchemy import or_

from .models import (
    AuditLog,
    CommissionTransaction,
    ImportBatch,
    Workspace,
    WorkspaceNote,
    WorkspaceChatMessage,
)
from .guides import get_role_guides, get_interactive_tour
from .workspaces import get_accessible_workspace_ids, get_accessible_workspaces, user_can_access_workspace
from . import db


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

    # ✅ Safe conversion: works even if steps are missing or malformed
    for section in sections:
        fixed_steps = []
        for step in section.get("steps", []):
            try:
                # Convert [("title", "..."), ("items", [...])] → {"title": "...", "items": [...]}
                if isinstance(step, (list, tuple)):
                    step = dict(step)
                # Only include valid steps with 'title' and 'items'
                if isinstance(step, dict) and "title" in step and "items" in step:
                    fixed_steps.append(step)
            except Exception:
                continue
        section["steps"] = fixed_steps

    # Interactive tour setup stays the same
    tour_steps = []
    for step in get_interactive_tour():
        step_copy = {key: value for key, value in step.items() if key not in {"cta_endpoint", "cta_kwargs"}}
        endpoint = step.get("cta_endpoint")
        kwargs = step.get("cta_kwargs", {})
        if endpoint:
            step_copy["cta_url"] = url_for(endpoint, **kwargs)
        tour_steps.append(step_copy)

    return render_template("guide.html", sections=sections, tour_steps=tour_steps)




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
