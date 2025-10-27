from flask import Blueprint, render_template
from flask_login import current_user, login_required

from sqlalchemy import or_

from .models import AuditLog, CommissionTransaction, ImportBatch
from .workspaces import get_accessible_workspace_ids


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def dashboard():
    org_id = current_user.org_id
    workspace_ids = get_accessible_workspace_ids(current_user)

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
    return render_template(
        "dashboard.html",
        imports=imports,
        txns_total=txns_total,
        audit_events=audit_events,
    )


@main_bp.route("/onboarding")
@login_required
def onboarding():
    return render_template("onboarding.html")
