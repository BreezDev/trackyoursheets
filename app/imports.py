import csv
import io
import os
from datetime import datetime

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
from werkzeug.utils import secure_filename

from . import db
from .models import Carrier, ImportBatch, ImportRow
from .nylas_email import send_import_notification
from .workspaces import (
    find_workspace_for_upload,
    get_accessible_workspaces,
    get_accessible_workspace_ids,
)


imports_bp = Blueprint("imports", __name__)


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

    require_workspace_choice = (
        current_user.role in {"owner", "admin"} and len(workspaces) > 1
    )

    return render_template(
        "imports/index.html",
        workspaces=workspaces,
        batches=batches,
        require_workspace_choice=require_workspace_choice,
    )


@imports_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    period_month = request.form.get("period_month")
    workspace_id_raw = request.form.get("workspace_id")
    workspace_id = int(workspace_id_raw) if workspace_id_raw else None
    file = request.files.get("statement")

    workspace = find_workspace_for_upload(current_user, workspace_id)
    if not workspace:
        flash("Select a valid workspace for this upload.", "danger")
        return redirect(url_for("imports.index"))

    if not period_month or not file:
        flash("Statement period and file are required.", "danger")
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

    batches_created = []
    summary = []
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
            period_month=period_month,
            source_type="csv",
            status="uploaded",
            created_by=current_user.id,
            file_path=batch_path,
        )
        db.session.add(batch)
        db.session.flush()

        import_rows = [
            ImportRow(
                batch_id=batch.id,
                raw=row,
                normalized=_normalize_row(row, carrier_field),
            )
            for row in carrier_rows
        ]
        db.session.bulk_save_objects(import_rows)
        batch.status = "imported"
        batches_created.append(batch)
        summary.append({"carrier": carrier.name, "rows": len(import_rows)})

    db.session.commit()

    if workspace.agent and workspace.agent.email:
        send_import_notification(
            recipient=workspace.agent.email,
            workspace=workspace,
            uploader=current_user,
            period=period_month,
            summary=summary,
        )

    flash(
        "Import uploaded and routed by carrier." if batches_created else "No rows imported.",
        "success" if batches_created else "warning",
    )
    return redirect(url_for("imports.index"))


def _group_rows_by_carrier(rows, carrier_field):
    grouped = {}
    for row in rows:
        carrier_name = (row.get(carrier_field) or "Unspecified").strip()
        grouped.setdefault(carrier_name or "Unspecified", []).append(row)
    return grouped


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

    return {
        "carrier": row.get(carrier_field),
        "policy_number": _first(["policy_number", "Policy Number", "Policy #", "Policy"]),
        "customer": _first(["customer", "Customer Name", "Insured", "Client"]),
        "premium": premium,
        "commission": commission,
    }


def _slugify(value):
    slug = secure_filename(value.lower()).replace(".", "_")
    return slug or "carrier"
