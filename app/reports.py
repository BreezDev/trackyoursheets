import csv
from collections import defaultdict
from datetime import datetime
from io import BytesIO, StringIO

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from . import db
from .models import (
    CommissionTransaction,
    ImportBatch,
    PayoutStatement,
    Producer,
    Workspace,
    CategoryTag,
)
from .workspaces import get_accessible_producers, get_accessible_workspace_ids

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


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

    can_assign_producers = current_user.role in {"owner", "admin"}
    assignable_producers = (
        get_accessible_producers(current_user) if can_assign_producers else []
    )

    return render_template(
        "reports/overview.html",
        carrier_totals=carrier_rows,
        producer_totals=producer_rows,
        category_totals=category_rows,
        recent_transactions=recent_transactions,
        statements=statements,
        batches=batches,
        generated_at=datetime.utcnow(),
        assignable_producers=assignable_producers,
        can_assign_producers=can_assign_producers,
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

    dataset["columns"] = [
        {"key": "date", "label": "Date"},
        {"key": "producer", "label": "Producer"},
        {"key": "workspace", "label": "Workspace"},
        {"key": "category", "label": "Category"},
        {"key": "product_type", "label": "Product"},
        {"key": "premium", "label": "Premium", "format": "currency"},
        {"key": "commission", "label": "Commission", "format": "currency"},
        {"key": "status", "label": "Status"},
    ]

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

    table_rows = [_commission_row(txn) for txn in transactions]
    summary = {
        "commission": sum(float(txn.amount or 0) for txn in transactions),
        "premium": sum(float(txn.premium or 0) for txn in transactions),
        "count": len(transactions),
    }

    columns = [
        {"key": "date", "label": "Date"},
        {"key": "producer", "label": "Producer"},
        {"key": "workspace", "label": "Workspace"},
        {"key": "policy", "label": "Policy"},
        {"key": "category", "label": "Category"},
        {"key": "premium", "label": "Premium", "format": "currency"},
        {"key": "commission", "label": "Commission", "format": "currency"},
        {"key": "split", "label": "Split"},
        {"key": "status", "label": "Status"},
    ]

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

    dataset = {
        "table": table_rows,
        "summary": summary,
        "columns": columns,
    }

    if fmt == "pdf":
        pdf_bytes = _build_pdf_report(title, dataset)
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{filename}.pdf",
        )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([column["label"] for column in columns])
    for row in table_rows:
        writer.writerow(
            [
                _format_csv_value(row, column)
                for column in columns
            ]
        )
    output.seek(0)
    return send_file(
        BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{filename}.csv",
    )


@reports_bp.route("/production-summary")
@login_required
def production_summary():
    fmt = (request.args.get("format") or "csv").lower()
    producer_id = request.args.get("producer_id", type=int)

    workspace_ids = get_accessible_workspace_ids(current_user)

    producer = None
    if producer_id:
        producer = Producer.query.filter_by(
            id=producer_id,
            org_id=current_user.org_id,
        ).first_or_404()
        if (
            current_user.role == "agent"
            and workspace_ids
            and producer.workspace_id not in workspace_ids
        ):
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

    aggregates = {}
    for txn in transactions:
        key = txn.producer_id or 0
        if key not in aggregates:
            producer_name = txn.producer.display_name if txn.producer else "Unassigned"
            workspace_name = "Unassigned"
            if txn.producer and txn.producer.workspace:
                workspace_name = txn.producer.workspace.name
            elif txn.workspace:
                workspace_name = txn.workspace.name
            elif txn.batch and txn.batch.workspace:
                workspace_name = txn.batch.workspace.name
            aggregates[key] = {
                "producer": producer_name,
                "workspace": workspace_name,
                "premium": 0.0,
                "commission": 0.0,
                "sales": 0,
            }
        aggregates[key]["premium"] += float(txn.premium or 0)
        aggregates[key]["commission"] += float(txn.amount or 0)
        aggregates[key]["sales"] += 1

    table_rows = [
        {
            "producer": data["producer"],
            "workspace": data["workspace"],
            "premium": round(data["premium"], 2),
            "commission": round(data["commission"], 2),
            "sales": data["sales"],
        }
        for data in aggregates.values()
    ]

    table_rows.sort(key=lambda row: row["premium"], reverse=True)

    summary = {
        "commission": sum(row["commission"] for row in table_rows),
        "premium": sum(row["premium"] for row in table_rows),
        "count": sum(row["sales"] for row in table_rows),
    }

    columns = [
        {"key": "producer", "label": "Producer"},
        {"key": "workspace", "label": "Workspace"},
        {"key": "premium", "label": "Total premium", "format": "currency"},
        {"key": "commission", "label": "Total commission", "format": "currency"},
        {"key": "sales", "label": "Sales"},
    ]

    org_name = (
        current_user.organization.name
        if getattr(current_user, "organization", None) and current_user.organization
        else f"Org {current_user.org_id}"
    )

    title = (
        f"Production summary — {producer.display_name}"
        if producer
        else f"Production summary — {org_name}"
    )
    filename = (
        f"production_summary_{producer.display_name.lower().replace(' ', '_')}"
        if producer
        else "production_summary_all"
    )

    dataset = {
        "table": table_rows,
        "summary": summary,
        "columns": columns,
    }

    if fmt == "pdf":
        pdf_bytes = _build_pdf_report(title, dataset)
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{filename}.pdf",
        )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([column["label"] for column in columns])
    for row in table_rows:
        writer.writerow(
            [
                _format_csv_value(row, column)
                for column in columns
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


@reports_bp.route("/activity/<int:txn_id>/assign", methods=["POST"])
@login_required
def assign_transaction_producer(txn_id: int):
    if current_user.role not in {"owner", "admin"}:
        abort(403)
    txn = CommissionTransaction.query.filter_by(
        id=txn_id, org_id=current_user.org_id
    ).first_or_404()
    producer_id = request.form.get("producer_id", type=int)
    next_url = request.form.get("next") or request.referrer or url_for("reports.overview")
    if not producer_id:
        flash("Select a producer to assign.", "danger")
        return redirect(next_url)
    producer = Producer.query.filter_by(
        id=producer_id, org_id=current_user.org_id
    ).first()
    if not producer:
        flash("Producer not found.", "danger")
        return redirect(next_url)
    txn.producer_id = producer.id
    if not txn.workspace_id and producer.workspace_id:
        txn.workspace_id = producer.workspace_id
    db.session.add(txn)
    db.session.commit()
    flash("Producer assigned to transaction.", "success")
    return redirect(next_url)


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
    columns = dataset.get("columns", [])

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=title,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    brand_blue = colors.HexColor("#2A4BFF")
    header_style = ParagraphStyle(
        "ReportHeader",
        parent=styles["Heading1"],
        fontSize=22,
        leading=28,
        textColor=brand_blue,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
    )

    story = [
        Paragraph("TrackYourSheets", header_style),
        Paragraph(title, subtitle_style),
        Spacer(1, 0.2 * inch),
    ]

    generated_at = datetime.utcnow().strftime("%b %d, %Y %I:%M %p UTC")
    summary_rows = [
        ["Generated", generated_at],
        ["Total commission", f"${summary.get('commission', 0):,.2f}"],
        ["Total premium", f"${summary.get('premium', 0):,.2f}"],
        ["Transactions", f"{summary.get('count', 0):,}"],
    ]
    summary_table = Table(
        [["Metric", "Value"], *summary_rows],
        hAlign="LEFT",
        colWidths=[2.3 * inch, 4.0 * inch],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), brand_blue),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.3 * inch))

    if columns and table:
        header_row = [column["label"] for column in columns]
        max_rows = 200
        data_rows = []
        for row in table[:max_rows]:
            rendered_cells = []
            for column in columns:
                value = row.get(column["key"])
                if column.get("format") == "currency" and value is not None:
                    try:
                        rendered_cells.append(f"${float(value):,.2f}")
                    except (TypeError, ValueError):
                        rendered_cells.append("$0.00")
                else:
                    rendered_cells.append(str(value) if value not in {None, ""} else "—")
            data_rows.append(rendered_cells)
        tabular_data = [header_row, *data_rows]
        pdf_table = Table(tabular_data, repeatRows=1)
        pdf_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), brand_blue),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(pdf_table)
        if len(table) > max_rows:
            story.append(Spacer(1, 0.1 * inch))
            story.append(
                Paragraph(
                    f"Showing first {max_rows} rows of {len(table)}. Export CSV for the full data set.",
                    styles["Italic"],
                )
            )
    else:
        body_style = styles["BodyText"]
        if table:
            for row in table:
                story.append(Paragraph(str(row), body_style))
                story.append(Spacer(1, 0.1 * inch))
        else:
            story.append(Paragraph("No transactions available for this report.", body_style))

    document.build(story)
    return buffer.getvalue()


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


def _format_csv_value(row, column):
    value = row.get(column["key"])
    if value is None:
        return ""
    if column.get("format") == "currency":
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "0.00"
    return value


def _fetch_status_categories(org_id: int):
    tags = (
        CategoryTag.query.filter_by(org_id=org_id, kind="status")
        .order_by(CategoryTag.name.asc())
        .all()
    )
    if tags:
        return [tag.name for tag in tags]
    return ["Raw", "Existing", "Renewal"]
