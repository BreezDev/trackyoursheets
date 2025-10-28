import csv
from collections import defaultdict
from datetime import datetime
from io import BytesIO, StringIO

from flask import Blueprint, abort, jsonify, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from .models import (
    CommissionTransaction,
    ImportBatch,
    PayoutStatement,
    Producer,
    Workspace,
    CategoryTag,
)
from .workspaces import get_accessible_workspace_ids


reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/")
@login_required
def overview():
    org_id = current_user.org_id
    workspace_ids = get_accessible_workspace_ids(current_user)
    carrier_totals = defaultdict(lambda: {"premium": 0.0, "commission": 0.0})
    producer_totals = defaultdict(lambda: {"premium": 0.0, "commission": 0.0})
    category_totals = defaultdict(lambda: {"premium": 0.0, "commission": 0.0})
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
        carrier = (
            txn.carrier_name
            or (txn.policy.carrier.name if txn.policy and txn.policy.carrier else "Unassigned")
        )
        producer_name = txn.producer.display_name if txn.producer else "Unassigned"
        category = txn.category or "raw"
        carrier_totals[carrier]["premium"] += float(txn.premium or 0)
        carrier_totals[carrier]["commission"] += float(txn.amount or 0)
        producer_totals[producer_name]["premium"] += float(txn.premium or 0)
        producer_totals[producer_name]["commission"] += float(txn.amount or 0)
        category_totals[category]["premium"] += float(txn.premium or 0)
        category_totals[category]["commission"] += float(txn.amount or 0)

    carrier_rows = [
        {
            "carrier": carrier,
            "premium": totals["premium"],
            "commission": totals["commission"],
        }
        for carrier, totals in carrier_totals.items()
    ]

    producer_rows = [
        {
            "producer": producer,
            "premium": totals["premium"],
            "commission": totals["commission"],
        }
        for producer, totals in producer_totals.items()
    ]

    category_rows = [
        {
            "category": category,
            "premium": totals["premium"],
            "commission": totals["commission"],
        }
        for category, totals in category_totals.items()
    ]

    recent_transactions = sorted(
        transactions,
        key=lambda txn: txn.txn_date or datetime.utcnow().date(),
        reverse=True,
    )[:25]

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
        producer_totals=producer_rows,
        category_totals=category_rows,
        recent_transactions=recent_transactions,
        statements=statements,
        batches=batches,
        generated_at=datetime.utcnow(),
    )


@reports_bp.route("/analytics")
@login_required
def analytics_dashboard():
    workspace_ids = get_accessible_workspace_ids(current_user)

    category_tags = _fetch_status_categories(current_user.org_id)

    producer_query = Producer.query.filter_by(org_id=current_user.org_id)
    if workspace_ids:
        producer_query = producer_query.filter(Producer.workspace_id.in_(workspace_ids))
    producers = producer_query.order_by(Producer.display_name.asc()).all()

    workspace_query = Workspace.query.filter_by(org_id=current_user.org_id)
    if workspace_ids:
        workspace_query = workspace_query.filter(Workspace.id.in_(workspace_ids))
    workspaces = workspace_query.order_by(Workspace.name.asc()).all()

    return render_template(
        "reports/analytics.html",
        categories=category_tags,
        producers=producers,
        workspaces=workspaces,
    )


@reports_bp.route("/analytics/data")
@login_required
def analytics_data():
    dataset = _build_analytics_dataset(request.args, include_rows=True)
    return jsonify(dataset)


@reports_bp.route("/analytics/export")
@login_required
def analytics_export():
    dataset = _build_analytics_dataset(request.args, include_rows=True)
    fmt = (request.args.get("format") or "csv").lower()
    filename = "analytics_report"

    if fmt == "pdf":
        pdf_bytes = _build_pdf_report("Analytics summary", dataset)
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{filename}.pdf",
        )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Date",
            "Producer",
            "Workspace",
            "Category",
            "Product",
            "Premium",
            "Commission",
            "Status",
        ]
    )
    for row in dataset.get("table", []):
        writer.writerow(
            [
                row.get("date"),
                row.get("producer"),
                row.get("workspace"),
                row.get("category"),
                row.get("product_type"),
                f"{row.get('premium', 0):.2f}",
                f"{row.get('commission', 0):.2f}",
                row.get("status"),
            ]
        )
    output.seek(0)
    return send_file(
        BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{filename}.csv",
    )


@reports_bp.route("/commission-sheet")
@login_required
def commission_sheet():
    producer_id = request.args.get("producer_id", type=int)
    fmt = (request.args.get("format") or "csv").lower()

    workspace_ids = get_accessible_workspace_ids(current_user)

    producer = None
    if producer_id:
        producer = Producer.query.filter_by(
            id=producer_id, org_id=current_user.org_id
        ).first_or_404()
        if current_user.role == "agent" and workspace_ids and producer.workspace_id not in workspace_ids:
            abort(403)

    query = CommissionTransaction.query.filter_by(org_id=current_user.org_id)
    if workspace_ids:
        query = query.filter(
            or_(
                CommissionTransaction.workspace_id.in_(workspace_ids),
                CommissionTransaction.batch.has(ImportBatch.workspace_id.in_(workspace_ids)),
            )
        )
    if producer:
        query = query.filter(CommissionTransaction.producer_id == producer.id)

    transactions = query.order_by(CommissionTransaction.txn_date.asc()).all()

    org_name = (
        current_user.organization.name
        if getattr(current_user, "organization", None) and current_user.organization
        else f"Org {current_user.org_id}"
    )
    title = (
        f"Commission sheet — {producer.display_name}"
        if producer
        else f"Commission sheet — {org_name}"
    )
    filename = (
        f"commission_sheet_{producer.display_name.lower().replace(' ', '_')}"
        if producer
        else "commission_sheet_all"
    )

    if fmt == "pdf":
        pdf_bytes = _build_pdf_report(
            title,
            {
                "table": [
                    _commission_row(txn)
                    for txn in transactions
                ],
                "summary": {
                    "commission": sum(float(txn.amount or 0) for txn in transactions),
                    "premium": sum(float(txn.premium or 0) for txn in transactions),
                    "count": len(transactions),
                },
            },
        )
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{filename}.pdf",
        )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Date",
            "Producer",
            "Workspace",
            "Policy",
            "Category",
            "Premium",
            "Commission",
            "Split",
            "Status",
        ]
    )
    for txn in transactions:
        row = _commission_row(txn)
        writer.writerow(
            [
                row["date"],
                row["producer"],
                row["workspace"],
                row["policy"],
                row["category"],
                f"{row['premium']:.2f}",
                f"{row['commission']:.2f}",
                row["split"],
                row["status"],
            ]
        )
    output.seek(0)
    return send_file(
        BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{filename}.csv",
    )


@reports_bp.route("/activity/<int:txn_id>")
@login_required
def activity_detail(txn_id: int):
    txn = CommissionTransaction.query.filter_by(
        id=txn_id, org_id=current_user.org_id
    ).first_or_404()

    workspace_ids = get_accessible_workspace_ids(current_user)
    if current_user.role == "agent" and workspace_ids and txn.workspace_id not in workspace_ids:
        abort(403)

    return render_template("reports/activity_detail.html", transaction=txn)


def _build_analytics_dataset(params, include_rows=False):
    org_id = current_user.org_id
    workspace_ids = get_accessible_workspace_ids(current_user)

    query = CommissionTransaction.query.filter_by(org_id=org_id)
    if workspace_ids:
        query = query.filter(
            or_(
                CommissionTransaction.workspace_id.in_(workspace_ids),
                CommissionTransaction.batch.has(ImportBatch.workspace_id.in_(workspace_ids)),
            )
        )

    producer_id = params.get("producer_id")
    if producer_id:
        try:
            producer_id_int = int(producer_id)
        except (TypeError, ValueError):
            producer_id_int = None
        if producer_id_int:
            query = query.filter(CommissionTransaction.producer_id == producer_id_int)

    workspace_filter = params.get("workspace_id")
    if workspace_filter:
        try:
            workspace_int = int(workspace_filter)
        except (TypeError, ValueError):
            workspace_int = None
        if workspace_int:
            query = query.filter(CommissionTransaction.workspace_id == workspace_int)

    category_filter = params.get("category")
    if category_filter:
        query = query.filter(
            func.lower(CommissionTransaction.category) == category_filter.lower()
        )

    product_filter = params.get("product_type") or params.get("line")
    if product_filter:
        query = query.filter(
            func.lower(CommissionTransaction.product_type) == product_filter.lower()
        )

    status_filter = params.get("status")
    if status_filter:
        query = query.filter(
            func.lower(CommissionTransaction.status) == status_filter.lower()
        )

    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))
    if date_from:
        query = query.filter(CommissionTransaction.txn_date >= date_from)
    if date_to:
        query = query.filter(CommissionTransaction.txn_date <= date_to)

    group_by = params.get("group_by") or "month"

    transactions = query.order_by(CommissionTransaction.txn_date.asc()).all()

    totals = {"premium": 0.0, "commission": 0.0}
    grouped = defaultdict(lambda: {"premium": 0.0, "commission": 0.0})

    table_rows = []
    for txn in transactions:
        premium = float(txn.premium or 0)
        commission = float(txn.amount or 0)
        totals["premium"] += premium
        totals["commission"] += commission
        key = _analytics_group_key(txn, group_by)
        grouped[key]["premium"] += premium
        grouped[key]["commission"] += commission
        if include_rows:
            table_rows.append(_commission_row(txn))

    labels = sorted(grouped.keys())
    series = [
        {
            "label": "Commission",
            "data": [round(grouped[label]["commission"], 2) for label in labels],
        },
        {
            "label": "Premium",
            "data": [round(grouped[label]["premium"], 2) for label in labels],
        },
    ]

    result = {
        "labels": labels,
        "series": series,
        "summary": {
            "commission": round(totals["commission"], 2),
            "premium": round(totals["premium"], 2),
            "count": len(transactions),
        },
    }

    if include_rows:
        table_rows.sort(key=lambda row: row["date"], reverse=True)
        result["table"] = table_rows

    return result


def _analytics_group_key(txn, group_by):
    if group_by == "category":
        return txn.category or "Uncategorized"
    if group_by == "producer":
        return txn.producer.display_name if txn.producer else "Unassigned"
    if group_by == "workspace":
        if txn.workspace:
            return txn.workspace.name
        if txn.batch and txn.batch.workspace:
            return txn.batch.workspace.name
        return "Unassigned"
    if group_by == "product":
        return txn.product_type or "Other"
    if group_by == "status":
        return txn.status or "Unknown"
    date_value = txn.txn_date or datetime.utcnow().date()
    if group_by == "day":
        return date_value.strftime("%Y-%m-%d")
    return date_value.strftime("%Y-%m")


def _parse_date(raw):
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            value = datetime.strptime(raw, fmt).date()
            if fmt == "%Y-%m":
                return value.replace(day=1)
            return value
        except ValueError:
            continue
    return None


def _build_pdf_report(title, dataset):
    summary = dataset.get("summary", {})
    table = dataset.get("table", [])

    lines = [title, ""]
    lines.append(f"Total commission: ${summary.get('commission', 0):.2f}")
    lines.append(f"Total premium: ${summary.get('premium', 0):.2f}")
    lines.append(f"Transactions: {summary.get('count', 0)}")
    lines.append("")

    for row in table[:40]:
        lines.append(
            f"{row.get('date')} · {row.get('producer')} · ${row.get('commission', 0):.2f}"
        )

    return _text_to_pdf_bytes(lines)


def _text_to_pdf_bytes(lines):
    if isinstance(lines, str):
        text_lines = lines.splitlines()
    else:
        text_lines = list(lines)
    if not text_lines:
        text_lines = [""]

    content_parts = ["BT /F1 12 Tf 72 720 Td"]
    for index, line in enumerate(text_lines):
        safe_line = (
            (line or "")
            .replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        if index == 0:
            content_parts.append(f"({safe_line}) Tj")
        else:
            content_parts.append(f"0 -16 Td ({safe_line}) Tj")
    content_parts.append("ET")
    content_stream = "\n".join(content_parts)
    content_bytes = content_stream.encode("latin-1")

    parts = []
    offsets = []
    total = 0

    def append_bytes(value):
        nonlocal total
        if isinstance(value, str):
            data = value.encode("latin-1")
        else:
            data = value
        parts.append(data)
        total += len(data)

    def append_obj(value):
        offsets.append(total)
        append_bytes(value)

    append_bytes("%PDF-1.4\n")
    append_obj("1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    append_obj("2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    append_obj(
        "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    append_obj(
        f"4 0 obj<< /Length {len(content_bytes)} >>stream\n{content_stream}\nendstream\nendobj\n"
    )
    append_obj("5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    xref_offset = total
    append_bytes("xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets:
        append_bytes(f"{offset:010d} 00000 n \n")
    append_bytes(f"trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF")

    return b"".join(parts)


def _commission_row(txn):
    workspace_name = "—"
    if txn.workspace:
        workspace_name = txn.workspace.name
    elif txn.batch and txn.batch.workspace:
        workspace_name = txn.batch.workspace.name

    split_value = txn.manual_split_pct or txn.split_pct

    policy_number = "—"
    if txn.policy and txn.policy.policy_number:
        policy_number = txn.policy.policy_number

    row = {
        "id": txn.id,
        "date": txn.txn_date.strftime("%Y-%m-%d") if txn.txn_date else "",
        "producer": txn.producer.display_name if txn.producer else "Unassigned",
        "workspace": workspace_name,
        "policy": policy_number,
        "category": txn.category or "Uncategorized",
        "product_type": txn.product_type or "—",
        "premium": float(txn.premium or 0),
        "commission": float(txn.amount or 0),
        "split": f"{float(split_value):.2f}%" if split_value is not None else "—",
        "status": txn.status or "—",
        "link": url_for("reports.activity_detail", txn_id=txn.id),
    }
    return row


def _fetch_status_categories(org_id: int):
    tags = (
        CategoryTag.query.filter_by(org_id=org_id, kind="status")
        .order_by(CategoryTag.name.asc())
        .all()
    )
    if tags:
        return [tag.name for tag in tags]
    return ["Raw", "Existing", "Renewal"]
