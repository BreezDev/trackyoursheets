from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import current_user, login_required

from sqlalchemy import or_

from .models import AuditLog, CommissionTransaction, ImportBatch, Workspace, WorkspaceNote
from .workspaces import get_accessible_workspace_ids, get_accessible_workspaces, user_can_access_workspace
from . import db


main_bp = Blueprint("main", __name__)


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

    return render_template(
        "dashboard.html",
        imports=imports,
        txns_total=txns_total,
        audit_events=audit_events,
        workspaces=workspaces,
        active_workspace=active_workspace,
        personal_note=personal_note,
        shared_note=shared_note,
    )


@main_bp.route("/onboarding")
@login_required
def onboarding():
    return render_template("onboarding.html")


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
                owner_id=current_user.id,
                scope="shared",
            )
            db.session.add(note)

    note.content = content
    db.session.commit()

    return jsonify({"status": "saved", "updated_at": note.updated_at.isoformat()})
