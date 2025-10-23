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

from . import db
from .models import Carrier, ImportBatch, ImportRow


imports_bp = Blueprint("imports", __name__)


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"csv"}


@imports_bp.route("/")
@login_required
def index():
    carriers = Carrier.query.filter_by(org_id=current_user.org_id).all()
    batches = (
        ImportBatch.query.filter_by(org_id=current_user.org_id)
        .order_by(ImportBatch.created_at.desc())
        .all()
    )
    return render_template("imports/index.html", carriers=carriers, batches=batches)


@imports_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    carrier_id = request.form.get("carrier_id")
    period_month = request.form.get("period_month")
    source_type = "csv"
    file = request.files.get("statement")

    if not carrier_id or not period_month or not file:
        flash("Carrier, period, and file are required.", "danger")
        return redirect(url_for("imports.index"))

    if not _allowed_file(file.filename):
        flash("Only CSV files are supported in this version.", "warning")
        return redirect(url_for("imports.index"))

    carrier = Carrier.query.filter_by(id=carrier_id, org_id=current_user.org_id).first()
    if not carrier:
        flash("Carrier not found.", "danger")
        return redirect(url_for("imports.index"))

    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    file_path = os.path.join(upload_dir, filename)

    raw_bytes = file.read()
    file.stream.seek(0)
    file.save(file_path)

    batch = ImportBatch(
        org_id=current_user.org_id,
        carrier_id=carrier.id,
        period_month=period_month,
        source_type=source_type,
        status="uploaded",
        created_by=current_user.id,
        file_path=file_path,
    )
    db.session.add(batch)
    db.session.commit()

    reader = csv.DictReader(io.StringIO(raw_bytes.decode("utf-8")))
    rows = []
    for raw_row in reader:
        row = ImportRow(batch_id=batch.id, raw=raw_row, normalized={"premium": raw_row.get("Premium")})
        rows.append(row)
    db.session.bulk_save_objects(rows)
    batch.status = "imported"
    db.session.commit()

    flash("Import uploaded and queued for reconciliation.", "success")
    return redirect(url_for("imports.index"))
