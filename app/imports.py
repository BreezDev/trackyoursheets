import csv
import io
import os
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from . import db
from .models import (
    Carrier,
    CommissionTransaction,
    ImportBatch,
    ImportRow,
    Producer,
    CategoryTag,
    Workspace,
)
from .nylas_email import send_import_notification
from .workspaces import (
    find_workspace_for_upload,
    get_accessible_workspaces,
    get_accessible_workspace_ids,
    get_accessible_producers,
    user_can_access_workspace,
)


imports_bp = Blueprint("imports", __name__)



def _get_category_choices(org_id: int):
    tags = (
        CategoryTag.query.filter_by(org_id=org_id, kind="status")
        .order_by(CategoryTag.is_default.desc(), CategoryTag.name.asc())
        .all()
    )
    if tags:
        return [tag.name for tag in tags]
    return ["Auto", "Home", "Renters", "Life", "Raw", "Existing", "Renewal"]

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"csv"}


@imports_bp.route("/")
@login_required
def index():
    workspaces = get_accessible_workspaces(current_user)
    workspace_ids = get_accessible_workspace_ids(current_user)

    if workspace_ids:
        batch_query = ImportBatch.query.filter_by(org_id=current_user.org_id)
        batch_query = batch_query.filter(ImportBatch.workspace_id.in_(workspace_ids))
        batches = batch_query.order_by(ImportBatch.created_at.desc()).all()
    else:
        batches = []

    batch_summaries = {}
    preview_rows = {}
    if batches:
        batch_ids = [batch.id for batch in batches]
        stats = (
            db.session.query(
                CommissionTransaction.batch_id,
                func.coalesce(func.sum(CommissionTransaction.premium), 0),
                func.coalesce(func.sum(CommissionTransaction.amount), 0),
                func.count(CommissionTransaction.id),
            )
            .filter(CommissionTransaction.batch_id.in_(batch_ids))
            .group_by(CommissionTransaction.batch_id)
            .all()
        )
        for batch_id, premium_sum, amount_sum, txn_count in stats:
            batch_summaries[batch_id] = {
                "premium": float(premium_sum or 0),
                "commission": float(amount_sum or 0),
                "transactions": int(txn_count or 0),
            }
        for batch in batches:
            preview_rows[batch.id] = batch.rows[:5]

    require_workspace_choice = (
        current_user.role in {"owner", "admin"} and len(workspaces) > 1
    )

    return render_template(
        "imports/index.html",
        workspaces=workspaces,
        batches=batches,
        batch_summaries=batch_summaries,
        preview_rows=preview_rows,
        require_workspace_choice=require_workspace_choice,
    )


@imports_bp.route("/batch/<int:batch_id>")
@login_required
def detail(batch_id: int):
    batch = (
        ImportBatch.query.options(
            joinedload(ImportBatch.rows),
            joinedload(ImportBatch.workspace),
            joinedload(ImportBatch.carrier),
            joinedload(ImportBatch.commission_transactions)
            .joinedload(CommissionTransaction.producer)
            .joinedload(Producer.user),
        )
        .filter_by(id=batch_id, org_id=current_user.org_id)
        .first_or_404()
    )

    if not user_can_access_workspace(current_user, batch.workspace_id):
        flash("You do not have access to this workspace batch.", "danger")
        return redirect(url_for("imports.index"))

    totals = {
        "premium": sum(float(txn.premium or 0) for txn in batch.commission_transactions),
        "commission": sum(float(txn.amount or 0) for txn in batch.commission_transactions),
        "transactions": len(batch.commission_transactions),
    }

    per_producer = {}
    for txn in batch.commission_transactions:
        key = txn.producer.display_name if txn.producer else "Unassigned"
        per_producer.setdefault(
            key,
            {"premium": 0.0, "commission": 0.0, "count": 0},
        )
        per_producer[key]["premium"] += float(txn.premium or 0)
        per_producer[key]["commission"] += float(txn.amount or 0)
        per_producer[key]["count"] += 1

    return render_template(
        "imports/detail.html",
        batch=batch,
        totals=totals,
        producer_breakdown=per_producer,
        categories=_get_category_choices(current_user.org_id),
    )


@imports_bp.route("/manual", methods=["GET", "POST"])
@login_required
def manual_entry():
    workspaces = get_accessible_workspaces(current_user)
    if not workspaces:
        flash("Assign yourself to a workspace before adding manual transactions.", "warning")
        return redirect(url_for("imports.index"))

    carriers = (
        Carrier.query.filter_by(org_id=current_user.org_id)
        .order_by(Carrier.name.asc())
        .all()
    )
    producers = get_accessible_producers(current_user)

    raw_category_choices = _get_category_choices(current_user.org_id)
    category_choices = {_safe_str(value) for value in raw_category_choices}

    if request.method == "POST":
        workspace_id = request.form.get("workspace_id")
        try:
            workspace_id = int(workspace_id) if workspace_id else None
        except ValueError:
            workspace_id = None

        if not workspace_id or not user_can_access_workspace(current_user, workspace_id):
            flash("Choose a workspace you can access.", "danger")
            return redirect(url_for("imports.manual_entry"))

        workspace = Workspace.query.filter_by(id=workspace_id, org_id=current_user.org_id).first()
        if not workspace:
            flash("Workspace not found.", "danger")
            return redirect(url_for("imports.manual_entry"))

        carrier_name = request.form.get("carrier_name") or "Manual"
        carrier = _resolve_carrier(carrier_name)

        producer_id = request.form.get("producer_id")
        producer = None
        if producer_id:
            try:
                producer_id_int = int(producer_id)
            except ValueError:
                producer_id_int = None
            if producer_id_int:
                producer = Producer.query.filter_by(
                    id=producer_id_int,
                    org_id=current_user.org_id,
                ).first()
            if producer and producer.workspace_id != workspace.id:
                flash("Selected producer does not belong to this workspace.", "danger")
                return redirect(url_for("imports.manual_entry"))

        txn_date_raw = request.form.get("txn_date")
        if txn_date_raw:
            try:
                txn_date = datetime.strptime(txn_date_raw, "%Y-%m-%d").date()
            except ValueError:
                txn_date = datetime.utcnow().date()
        else:
            txn_date = datetime.utcnow().date()

        premium = _decimal_or_none(request.form.get("premium"))
        commission = _decimal_or_none(request.form.get("commission"))
        split_pct = _decimal_or_none(request.form.get("split_pct"))
        if split_pct is None and producer and producer.default_split is not None:
            split_pct = _decimal_or_none(producer.default_split)

        amount = _calculate_amount(commission, split_pct, {}) if commission is not None else None
        if commission is None and premium is not None and split_pct is not None:
            amount = premium * (split_pct / Decimal("100"))

        category = request.form.get("category") or "raw"
        category_normalized = _safe_str(category)
        if category_normalized not in category_choices:
            category_value = category_normalized or "other"
        else:
            category_value = category_normalized

        txn = CommissionTransaction(
            org_id=current_user.org_id,
            workspace_id=workspace.id,
            producer_id=producer.id if producer else None,
            txn_date=txn_date,
            premium=premium,
            commission=commission,
            basis=request.form.get("basis") or "manual",
            split_pct=split_pct,
            amount=amount,
            category=category_value,
            carrier_name=carrier.name if carrier else carrier_name,
            product_type=request.form.get("product_type") or None,
            source="manual",
            status="recorded",
            created_by=current_user.id,
            notes=request.form.get("notes") or None,
        )
        db.session.add(txn)
        db.session.commit()

        flash("Manual commission recorded.", "success")
        return redirect(url_for("reports.overview"))

    categories = _get_category_choices(current_user.org_id)
    return render_template(
        "imports/manual.html",
        workspaces=workspaces,
        carriers=carriers,
        producers=producers,
        categories=raw_category_choices,
        current_date=datetime.utcnow().date().isoformat(),
    )
@imports_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    workspace_id_raw = request.form.get("workspace_id")
    workspace_id = int(workspace_id_raw) if workspace_id_raw else None
    file = request.files.get("statement")

    workspace = find_workspace_for_upload(current_user, workspace_id)
    if not workspace:
        flash("Select a valid workspace for this upload.", "danger")
        return redirect(url_for("imports.index"))

    if not file:
        flash("Statement file is required.", "danger")
        return redirect(url_for("imports.index"))

    if not _allowed_file(file.filename):
        flash("Only CSV files are supported in this version.", "warning")
        return redirect(url_for("imports.index"))

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    original_name = secure_filename(file.filename)
    original_path = os.path.join(upload_dir, f"{timestamp}_{original_name}")

    raw_bytes = file.read()
    file.stream.seek(0)
    file.save(original_path)

    try:
        decoded = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = raw_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(decoded))
    fieldnames = reader.fieldnames or []
    carrier_field = next((h for h in fieldnames if h and h.strip().lower() == "carrier"), None)
    if not carrier_field:
        flash("The uploaded CSV must include a 'carrier' column.", "danger")
        return redirect(url_for("imports.index"))

    rows = [{k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()} for row in reader]
    if not rows:
        flash("The uploaded CSV did not contain any rows.", "warning")
        return redirect(url_for("imports.index"))

    accessible_producers = get_accessible_producers(current_user)
    batches_created = []
    summary = []
    derived_period = _derive_period_month(rows)
    for carrier_name, carrier_rows in _group_rows_by_carrier(rows, carrier_field).items():
        carrier = _resolve_carrier(carrier_name)
        batch_filename = f"{timestamp}_{_slugify(carrier_name)}.csv"
        batch_path = os.path.join(upload_dir, batch_filename)
        _write_rows(batch_path, fieldnames, carrier_rows)

        batch = ImportBatch(
            org_id=current_user.org_id,
            carrier_id=carrier.id,
            workspace_id=workspace.id,
            producer_id=current_user.producer.id if current_user.role == "producer" and current_user.producer else None,
            period_month=derived_period,
            source_type="csv",
            status="uploaded",
            created_by=current_user.id,
            file_path=batch_path,
        )
        db.session.add(batch)
        db.session.flush()

        import_rows = []
        for row_data in carrier_rows:
            normalized = _normalize_row(row_data, carrier_field)
            import_row = ImportRow(
                batch_id=batch.id,
                raw=row_data,
                normalized=normalized,
            )
            import_rows.append(import_row)
            db.session.add(import_row)

        db.session.flush()

        totals = {"premium": Decimal("0"), "commission": Decimal("0"), "count": 0}
        for import_row in import_rows:
            txn = _build_transaction(
                import_row,
                batch,
                workspace,
                carrier,
                accessible_producers,
            )
            if txn:
                db.session.add(txn)
                totals["premium"] += Decimal(txn.premium or 0)
                totals["commission"] += Decimal(txn.amount or 0)
                totals["count"] += 1

        batch.status = "imported"
        batches_created.append(batch)
        summary.append(
            {
                "carrier": carrier.name,
                "rows": len(import_rows),
                "transactions": totals["count"],
                "premium": float(totals["premium"]),
                "commission": float(totals["commission"]),
            }
        )

    db.session.commit()

    if workspace.agent and workspace.agent.email:
        send_import_notification(
            recipient=workspace.agent.email,
            workspace=workspace,
            uploader=current_user,
            period=derived_period,
            summary=summary,
        )

    flash(
        (
            f"Import uploaded for period {derived_period}."
            if batches_created
            else "No rows imported."
        ),
        "success" if batches_created else "warning",
    )
    return redirect(url_for("imports.index"))


def _group_rows_by_carrier(rows, carrier_field):
    grouped = {}
    for row in rows:
        carrier_name = (row.get(carrier_field) or "Unspecified").strip()
        grouped.setdefault(carrier_name or "Unspecified", []).append(row)
    return grouped


def _derive_period_month(rows):
    dates = []
    for row in rows:
        for key, value in row.items():
            if not key or value in (None, ""):
                continue
            key_lower = key.lower()
            if any(term in key_lower for term in ["period", "month", "date", "effective", "written"]):
                parsed = _parse_any_date(value)
                if parsed:
                    dates.append(parsed)
                    break
    if dates:
        target = min(dates)
    else:
        target = datetime.utcnow().date()
    return target.strftime("%Y-%m")


def _parse_any_date(value):
    if isinstance(value, (datetime, date)):
        return value.date() if isinstance(value, datetime) else value
    for fmt in [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y%m%d",
        "%b %d %Y",
        "%d %b %Y",
    ]:
        try:
            return datetime.strptime(str(value), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _resolve_carrier(carrier_name):
    carrier = (
        Carrier.query.filter(
            Carrier.org_id == current_user.org_id,
            func.lower(Carrier.name) == carrier_name.lower(),
        )
        .first()
    )
    if not carrier:
        carrier = Carrier(
            org_id=current_user.org_id,
            name=carrier_name,
            download_type="csv",
        )
        db.session.add(carrier)
        db.session.flush()
    return carrier


def _write_rows(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _normalize_row(row, carrier_field):
    def _first(keys):
        for key in keys:
            if key in row and row[key]:
                return row[key]
        return None

    def _parse_amount(value):
        if not value:
            return None
        cleaned = str(value).replace(",", "").replace("$", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    premium = _parse_amount(
        _first(["premium", "Premium", "Written Premium", "Total Premium"])
    )
    commission = _parse_amount(
        _first(["commission", "Commission", "Commission Amount", "Commission Total"])
    )

    known_keys = {
        carrier_field,
        "premium",
        "Premium",
        "Written Premium",
        "Total Premium",
        "commission",
        "Commission",
        "Commission Amount",
        "Commission Total",
        "policy_number",
        "Policy Number",
        "Policy #",
        "Policy",
        "customer",
        "Customer Name",
        "Insured",
        "Client",
    }

    additional = {
        key: value
        for key, value in row.items()
        if key not in known_keys and value not in (None, "")
    }

    return {
        "carrier": row.get(carrier_field),
        "policy_number": _first(["policy_number", "Policy Number", "Policy #", "Policy"]),
        "customer": _first(["customer", "Customer Name", "Insured", "Client"]),
        "premium": premium,
        "commission": commission,
        "additional_data": additional,
    }


def _slugify(value):
    slug = secure_filename(value.lower()).replace(".", "_")
    return slug or "carrier"


def _build_transaction(import_row, batch, workspace, carrier, accessible_producers):
    normalized = import_row.normalized or {}
    raw = import_row.raw or {}

    premium = _decimal_or_none(normalized.get("premium") or raw.get("premium"))
    commission = _decimal_or_none(normalized.get("commission") or raw.get("commission"))
    if commission is None:
        commission = _resolve_commission_amount(raw, premium)

    producer = _match_producer(raw, workspace, accessible_producers)
    split_pct = _resolve_split(raw, producer)
    amount = _calculate_amount(commission, split_pct, raw)

    txn_date = _parse_txn_date(raw) or datetime.utcnow().date()
    basis = _resolve_basis(raw, normalized)
    category = _resolve_category(raw, workspace.org_id if workspace else None)
    product_type = _resolve_product_type(raw, normalized)
    notes = _collect_notes(raw)

    if premium is None and commission is None and amount is None:
        return None

    return CommissionTransaction(
        org_id=batch.org_id,
        batch_id=batch.id,
        workspace_id=workspace.id,
        producer_id=producer.id if producer else None,
        txn_date=txn_date,
        premium=premium,
        commission=commission,
        basis=basis,
        split_pct=split_pct,
        amount=amount if amount is not None else commission,
        category=category,
        carrier_name=carrier.name if carrier else None,
        product_type=product_type,
        source="import",
        status="provisional",
        created_by=current_user.id,
        notes=notes,
    )


def _match_producer(row, workspace, accessible_producers):
    if not accessible_producers or not workspace:
        return None

    workspace_producers = [
        producer
        for producer in accessible_producers
        if producer.workspace_id == workspace.id
    ]
    if not workspace_producers:
        return None

    hints = []
    for key in [
        "producer",
        "producer_name",
        "producer full name",
        "agent",
        "agent_name",
        "writer",
        "producer_email",
        "agent_email",
    ]:
        value = row.get(key)
        if value:
            hints.append(value)

    normalized_hints = {_safe_str(value) for value in hints if value}
    for hint in normalized_hints:
        for producer in workspace_producers:
            if producer.display_name and _safe_str(producer.display_name) == hint:
                return producer
            if producer.user and producer.user.email:
                if _safe_str(producer.user.email) == hint:
                    return producer

    return workspace_producers[0] if len(workspace_producers) == 1 else None


def _resolve_split(row, producer):
    for key in [
        "split_pct",
        "split",
        "split %",
        "producer_split",
        "agent_split",
    ]:
        value = row.get(key)
        split = _decimal_or_none(value)
        if split is not None:
            return split

    if producer and producer.default_split is not None:
        return _decimal_or_none(producer.default_split)

    return None


def _resolve_commission_amount(row, premium):
    for key in [
        "commission",
        "commission_amount",
        "commission total",
        "agent_commission",
        "split_amount",
    ]:
        value = row.get(key)
        amount = _decimal_or_none(value)
        if amount is not None:
            return amount

    rate = _decimal_or_none(row.get("commission_rate") or row.get("rate"))
    if premium is not None and rate is not None:
        if rate > 1:
            rate = rate / Decimal("100")
        return (premium * rate)

    return None


def _calculate_amount(commission, split_pct, row):
    amount = _decimal_or_none(row.get("agent_amount") or row.get("producer_amount"))
    if amount is not None:
        return amount

    if commission is None:
        return None

    if split_pct is not None:
        return commission * (split_pct / Decimal("100"))

    return commission


def _resolve_basis(raw, normalized):
    return (
        raw.get("commission_basis")
        or raw.get("basis")
        or normalized.get("basis")
        or "import"
    )


def _resolve_category(raw, org_id=None):
    allowed = set()
    if org_id:
        allowed = {_safe_str(value) for value in _get_category_choices(org_id)}
    for key in [
        "category",
        "commission_type",
        "type",
        "revenue_type",
        "line_type",
    ]:
        value = raw.get(key)
        if value:
            normalized = _safe_str(value)
            if not allowed or normalized in allowed:
                return normalized
            return normalized
    return "raw"


def _resolve_product_type(raw, normalized):
    for key in [
        "lob",
        "line_of_business",
        "product_type",
        "coverage",
    ]:
        value = raw.get(key) or normalized.get(key)
        if value:
            return value
    return None


def _collect_notes(raw):
    parts = []
    for key in ["notes", "memo", "comments", "description", "status"]:
        value = raw.get(key)
        if value and value not in parts:
            parts.append(value)
    return "\n".join(parts) if parts else None


def _parse_txn_date(raw):
    for key in [
        "transaction_date",
        "date",
        "effective_date",
        "written_date",
        "paid_date",
    ]:
        value = raw.get(key)
        if not value:
            continue
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"]:
            try:
                return datetime.strptime(value, fmt).date()
            except (ValueError, TypeError):
                continue
    return None


def _decimal_or_none(value):
    if value in (None, "", " "):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _safe_str(value):
    if value is None:
        return ""
    return str(value).strip().lower()
