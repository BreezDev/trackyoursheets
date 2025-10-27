from collections import defaultdict
from datetime import datetime

from flask import Blueprint, render_template
from flask_login import current_user, login_required
from sqlalchemy import or_

from .models import CommissionTransaction, ImportBatch, PayoutStatement
from .workspaces import get_accessible_workspace_ids


reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/")
@login_required
def overview():
    org_id = current_user.org_id
    workspace_ids = get_accessible_workspace_ids(current_user)
    carrier_totals = defaultdict(lambda: {"premium": 0.0, "commission": 0.0})
    txn_query = CommissionTransaction.query.filter_by(org_id=org_id)
    if workspace_ids:
        txn_query = txn_query.filter(
            or_(
                CommissionTransaction.workspace_id.in_(workspace_ids),
                CommissionTransaction.batch.has(ImportBatch.workspace_id.in_(workspace_ids)),
            )
        )
        transactions = txn_query.all()
    else:
        transactions = []

    for txn in transactions:
        carrier = txn.policy.carrier.name if txn.policy and txn.policy.carrier else "Unassigned"
        carrier_totals[carrier]["premium"] += float(txn.premium or 0)
        carrier_totals[carrier]["commission"] += float(txn.amount or 0)

    carrier_rows = [
        {
            "carrier": carrier,
            "premium": totals["premium"],
            "commission": totals["commission"],
        }
        for carrier, totals in carrier_totals.items()
    ]

    statement_query = PayoutStatement.query.filter_by(org_id=org_id)
    batch_query = ImportBatch.query.filter_by(org_id=org_id)
    if workspace_ids:
        statement_query = statement_query.filter(PayoutStatement.workspace_id.in_(workspace_ids))
        batch_query = batch_query.filter(ImportBatch.workspace_id.in_(workspace_ids))
        statements = (
            statement_query.order_by(PayoutStatement.finalized_at.desc().nullslast()).all()
        )
        batches = (
            batch_query.order_by(ImportBatch.period_month.desc()).limit(12).all()
        )
    else:
        statements = []
        batches = []

    return render_template(
        "reports/overview.html",
        carrier_totals=carrier_rows,
        statements=statements,
        batches=batches,
        generated_at=datetime.utcnow(),
    )
