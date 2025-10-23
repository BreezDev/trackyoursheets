from flask import Blueprint, render_template
from flask_login import current_user, login_required

from .models import AuditLog, CommissionTransaction, ImportBatch


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def dashboard():
    org_id = current_user.org_id
    imports = (
        ImportBatch.query.filter_by(org_id=org_id)
        .order_by(ImportBatch.created_at.desc())
        .limit(5)
        .all()
    )
    txns_total = CommissionTransaction.query.filter_by(org_id=org_id).count()
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
