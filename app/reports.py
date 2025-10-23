from collections import defaultdict
from datetime import datetime

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from .models import CommissionTransaction, ImportBatch, PayoutStatement


reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/")
@login_required
def overview():
    org_id = current_user.org_id
    carrier_totals = defaultdict(lambda: {"premium": 0.0, "commission": 0.0})
    for txn in CommissionTransaction.query.filter_by(org_id=org_id).all():
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

    statements = (
        PayoutStatement.query.filter_by(org_id=org_id)
        .order_by(PayoutStatement.finalized_at.desc().nullslast())
        .all()
    )
    batches = (
        ImportBatch.query.filter_by(org_id=org_id)
        .order_by(ImportBatch.period_month.desc())
        .limit(12)
        .all()
    )

    return render_template(
        "reports/overview.html",
        carrier_totals=carrier_rows,
        statements=statements,
        batches=batches,
        generated_at=datetime.utcnow(),
    )
