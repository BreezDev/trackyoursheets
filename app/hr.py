"""HR portal blueprint providing people operations tooling inside TrackYourSheets."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Sequence

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from . import db
from .models import (
    DEFAULT_NOTIFICATION_PREFERENCES,
    HRComplaint,
    HRDocument,
    HRDocumentAcknowledgement,
    Office,
    OfficeMembership,
    Organization,
    PayrollEntry,
    PayrollRun,
    Producer,
    User,
    Workspace,
    WorkspaceMembership,
)


ACCESS_ROLES = {"owner", "admin", "agent", "bookkeeper", "hr"}
PUBLIC_HR_ENDPOINTS = {
    "hr.submit_complaint",
    "hr.complaint_submitted",
    "hr.acknowledge_document",
}

DOCUMENT_CATEGORY_LABELS: dict[str, str] = {
    "policy": "Policies",
    "benefits": "Benefits",
    "compliance": "Compliance",
    "training": "Training",
    "payroll": "Payroll",
    "wellbeing": "Wellbeing",
    "other": "Other",
}

COMPLAINT_STATUS_CHOICES: tuple[str, ...] = (
    "open",
    "in_progress",
    "waiting",
    "resolved",
)

COMPLAINT_PRIORITY_CHOICES: tuple[str, ...] = (
    "low",
    "normal",
    "high",
    "urgent",
)

hr_bp = Blueprint("hr", __name__)


@dataclass(frozen=True)
class ResourceLink:
    """Static HR resource metadata for templating."""

    title: str
    description: str
    href: str
    icon: str = "file-earmark-text"


POLICY_SECTIONS: Sequence[dict[str, object]] = (
    {
        "title": "Employee handbook",
        "description": "Core policies covering conduct, payroll, time off, and compliance expectations.",
        "resources": [
            ResourceLink(
                title="TrackYourSheets handbook",
                description="Download the master handbook template — update it with your agency specifics before sharing.",
                href="https://example.com/hr/handbook.pdf",
                icon="journal-text",
            ),
            ResourceLink(
                title="Code of conduct checklist",
                description="Quick checklist to confirm new hires acknowledged behaviour, confidentiality, and data policies.",
                href="https://example.com/hr/conduct-checklist",
                icon="check2-square",
            ),
        ],
    },
    {
        "title": "Benefits & wellbeing",
        "description": "Summaries and enrolment guidance for medical, retirement, and wellness programmes.",
        "resources": [
            ResourceLink(
                title="Benefits overview deck",
                description="Slides that outline plan tiers, employer contributions, and enrolment deadlines for your teams.",
                href="https://example.com/hr/benefits",
                icon="heart",
            ),
            ResourceLink(
                title="PTO request template",
                description="Shareable template that routes PTO approvals through TrackYourSheets with automated notifications.",
                href="https://example.com/hr/pto-template",
                icon="calendar2-check",
            ),
        ],
    },
    {
        "title": "Compliance & training",
        "description": "Keep licenses current and ensure security, privacy, and harassment training stays on schedule.",
        "resources": [
            ResourceLink(
                title="Annual compliance tracker",
                description="Spreadsheet for tracking CE credits, license expirations, and required annual attestations.",
                href="https://example.com/hr/compliance-tracker",
                icon="shield-check",
            ),
            ResourceLink(
                title="Security awareness agenda",
                description="30-minute meeting agenda covering phishing drills, password hygiene, and device requirements.",
                href="https://example.com/hr/security-agenda",
                icon="shield-lock",
            ),
        ],
    },
)


ONBOARDING_TASKS: Sequence[dict[str, str]] = (
    {
        "slug": "account",
        "title": "Account activated",
        "description": "Invite accepted and status set to active.",
    },
    {
        "slug": "first_login",
        "title": "First login",
        "description": "New teammate has logged in at least once.",
    },
    {
        "slug": "two_factor",
        "title": "Two-factor verified",
        "description": "Two-factor authentication is turned on for secure access.",
    },
    {
        "slug": "workspace",
        "title": "Workspace assigned",
        "description": "Teammate is part of an active workspace.",
    },
    {
        "slug": "notifications",
        "title": "Notifications confirmed",
        "description": "Notification preferences reviewed and saved.",
    },
)


def _normalise(value: str | None) -> str:
    return (value or "").strip().lower()


def _next_anniversary(original: datetime | None) -> date | None:
    if not original:
        return None
    base = original.date()
    today = datetime.utcnow().date()
    try:
        anniversary = date(today.year, base.month, base.day)
    except ValueError:
        # Handle 29 February gracefully.
        anniversary = date(today.year, 3, 1)
    if anniversary < today:
        try:
            anniversary = date(today.year + 1, base.month, base.day)
        except ValueError:
            anniversary = date(today.year + 1, 3, 1)
    return anniversary


def _workspace_names(user: User) -> List[str]:
    names: list[str] = []
    for membership in getattr(user, "workspace_memberships", []) or []:
        if membership.workspace:
            if membership.workspace.office:
                names.append(f"{membership.workspace.office.name} · {membership.workspace.name}")
            else:
                names.append(membership.workspace.name)
    if user.producer and user.producer.workspace:
        workspace = user.producer.workspace
        if workspace.office:
            names.append(f"{workspace.office.name} · {workspace.name}")
        else:
            names.append(workspace.name)
    if user.managed_workspace:
        workspace = user.managed_workspace
        label = "Agent: "
        if workspace.office:
            names.append(f"{label}{workspace.office.name} · {workspace.name}")
        else:
            names.append(f"{label}{workspace.name}")
    return sorted({name for name in names})


def _office_names(user: User) -> List[str]:
    offices = [membership.office.name for membership in getattr(user, "office_memberships", []) if membership.office]
    if user.managed_workspace and user.managed_workspace.office:
        offices.append(user.managed_workspace.office.name)
    return sorted({name for name in offices})


def _document_category_key(value: str | None) -> str:
    candidate = (value or "").strip().lower().replace(" ", "_")
    if candidate in DOCUMENT_CATEGORY_LABELS:
        return candidate
    return "other"


def _document_category_label(key: str) -> str:
    return DOCUMENT_CATEGORY_LABELS.get(key, key.replace("_", " ").title())


def _onboarding_progress(user: User) -> List[dict[str, object]]:
    workspaces_joined = bool(getattr(user, "workspace_memberships", [])) or bool(
        user.producer and user.producer.workspace
    )
    has_notifications = bool(user.notification_preferences)
    if has_notifications:
        baseline = DEFAULT_NOTIFICATION_PREFERENCES
        has_notifications = user.notification_preferences != baseline
    steps = []
    for task in ONBOARDING_TASKS:
        slug = task["slug"]
        if slug == "account":
            complete = user.status == "active"
        elif slug == "first_login":
            complete = user.last_login is not None
        elif slug == "two_factor":
            complete = bool(user.two_factor_enabled)
        elif slug == "workspace":
            complete = workspaces_joined
        elif slug == "notifications":
            complete = has_notifications
        else:
            complete = False
        steps.append({"slug": slug, "title": task["title"], "description": task["description"], "complete": complete})
    return steps


def _load_users_for_org(org_id: int) -> List[User]:
    return (
        User.query.filter_by(org_id=org_id)
        .options(
            joinedload(User.producer).joinedload(Producer.workspace).joinedload(Workspace.office),
            joinedload(User.workspace_memberships).joinedload(WorkspaceMembership.workspace).joinedload(Workspace.office),
            joinedload(User.office_memberships).joinedload(OfficeMembership.office),
            joinedload(User.managed_workspace).joinedload(Workspace.office),
        )
        .order_by(User.created_at.desc())
        .all()
    )


@hr_bp.before_request
@login_required
def ensure_hr_access():
    endpoint = request.endpoint or ""
    if endpoint in PUBLIC_HR_ENDPOINTS:
        return None
    if current_user.role not in ACCESS_ROLES:
        flash("You do not have access to the HR portal.", "danger")
        return redirect(url_for("main.dashboard"))


@hr_bp.route("/")
def dashboard():
    org = Organization.query.get_or_404(current_user.org_id)
    employees = _load_users_for_org(org.id)
    total = len(employees)
    active_count = sum(1 for user in employees if user.status == "active")
    pending_count = total - active_count
    two_factor_enabled = sum(1 for user in employees if user.two_factor_enabled)
    adoption_pct = round((two_factor_enabled / total) * 100) if total else 0
    role_breakdown = Counter(user.role for user in employees)

    recent_window = datetime.utcnow() - timedelta(days=45)
    recent_hires = [user for user in employees if user.created_at and user.created_at >= recent_window]
    upcoming_anniversaries = []
    for employee in employees:
        anniversary = _next_anniversary(employee.created_at)
        if not anniversary:
            continue
        if anniversary <= datetime.utcnow().date() + timedelta(days=90):
            upcoming_anniversaries.append({
                "user": employee,
                "anniversary": anniversary,
            })
    upcoming_anniversaries.sort(key=lambda item: item["anniversary"])

    workspaces = (
        Workspace.query.filter_by(org_id=org.id)
        .options(joinedload(Workspace.office), joinedload(Workspace.agent))
        .order_by(Workspace.name.asc())
        .all()
    )
    workspace_summary = [
        {
            "name": workspace.name,
            "office": workspace.office.name if workspace.office else None,
            "agent": workspace.agent.email if workspace.agent else None,
            "members": len(workspace.memberships),
        }
        for workspace in workspaces
    ]

    documents = (
        HRDocument.query.filter_by(org_id=org.id)
        .options(joinedload(HRDocument.acknowledgements))
        .all()
    )
    document_totals: dict[str, int] = {}
    acknowledgement_total = 0
    for document in documents:
        key = _document_category_key(document.category)
        document_totals[key] = document_totals.get(key, 0) + 1
        acknowledgement_total += len(document.acknowledgements or [])

    complaints = (
        HRComplaint.query.filter_by(org_id=org.id)
        .options(joinedload(HRComplaint.reporter), joinedload(HRComplaint.assignee))
        .order_by(HRComplaint.created_at.desc())
        .all()
    )
    complaint_counts = Counter(complaint.status for complaint in complaints)
    open_complaints = [complaint for complaint in complaints if complaint.status != "resolved"]
    urgent_queue = [complaint for complaint in complaints if complaint.priority == "urgent" and complaint.status != "resolved"]

    recent_payroll_runs = (
        PayrollRun.query.filter_by(org_id=org.id)
        .order_by(PayrollRun.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "hr/dashboard.html",
        org=org,
        employees=employees,
        active_count=active_count,
        pending_count=pending_count,
        total_employees=total,
        two_factor_enabled=two_factor_enabled,
        adoption_pct=adoption_pct,
        role_breakdown=role_breakdown,
        recent_hires=recent_hires,
        upcoming_anniversaries=upcoming_anniversaries,
        workspace_summary=workspace_summary,
        document_totals=document_totals,
        acknowledgement_total=acknowledgement_total,
        document_category_label=_document_category_label,
        complaint_counts=complaint_counts,
        open_complaints=open_complaints,
        urgent_queue=urgent_queue,
        recent_payroll_runs=recent_payroll_runs,
    )


@hr_bp.route("/directory")
def directory():
    org = Organization.query.get_or_404(current_user.org_id)
    employees = _load_users_for_org(org.id)
    query = _normalise(request.args.get("q"))
    role_filter = _normalise(request.args.get("role"))
    status_filter = _normalise(request.args.get("status"))
    office_filter = request.args.get("office")

    def matches(user: User) -> bool:
        if query:
            search_pool = {
                _normalise(user.email),
                _normalise(user.display_name_for_ui),
            }
            search_pool.update(_normalise(name) for name in _office_names(user))
            search_pool.update(_normalise(name) for name in _workspace_names(user))
            if not any(query in value for value in search_pool if value):
                return False
        if role_filter and _normalise(user.role) != role_filter:
            return False
        if status_filter and _normalise(user.status) != status_filter:
            return False
        if office_filter:
            office_ids = {membership.office_id for membership in user.office_memberships}
            managed_office = (
                {user.managed_workspace.office_id}
                if user.managed_workspace and user.managed_workspace.office_id
                else set()
            )
            office_ids.update(managed_office)
            if int(office_filter) not in office_ids:
                return False
        return True

    filtered = [user for user in employees if matches(user)]

    offices = (
        Office.query.filter_by(org_id=org.id)
        .order_by(Office.name.asc())
        .all()
    )
    available_statuses = sorted({user.status for user in employees})
    available_roles = sorted({user.role for user in employees})

    return render_template(
        "hr/directory.html",
        org=org,
        employees=filtered,
        offices=offices,
        available_statuses=available_statuses,
        available_roles=available_roles,
        filters={
            "query": request.args.get("q", ""),
            "role": request.args.get("role", ""),
            "status": request.args.get("status", ""),
            "office": office_filter or "",
        },
        office_names=_office_names,
        workspace_names=_workspace_names,
    )


@hr_bp.route("/onboarding")
def onboarding():
    org = Organization.query.get_or_404(current_user.org_id)
    employees = _load_users_for_org(org.id)
    focus_window = datetime.utcnow() - timedelta(days=90)
    onboarding_pool = [
        user for user in employees if (user.created_at and user.created_at >= focus_window) or user.status != "active"
    ]

    roster = []
    task_totals = Counter({task["slug"]: 0 for task in ONBOARDING_TASKS})
    for user in onboarding_pool:
        steps = _onboarding_progress(user)
        completed = sum(1 for step in steps if step["complete"])
        for step in steps:
            if step["complete"]:
                task_totals[step["slug"]] += 1
        roster.append(
            {
                "user": user,
                "steps": steps,
                "completed": completed,
                "total": len(steps),
                "progress_pct": round((completed / len(steps)) * 100) if steps else 0,
            }
        )

    roster.sort(key=lambda item: (item["completed"], item["user"].created_at or datetime.utcnow()))

    return render_template(
        "hr/onboarding.html",
        org=org,
        roster=roster,
        task_totals=task_totals,
        task_catalog=ONBOARDING_TASKS,
    )


@hr_bp.route("/policies")
def policies():
    org = Organization.query.get_or_404(current_user.org_id)
    documents = (
        HRDocument.query.filter_by(org_id=org.id)
        .options(joinedload(HRDocument.acknowledgements))
        .order_by(HRDocument.category.asc(), HRDocument.title.asc())
        .all()
    )
    documents_by_category: dict[str, list[HRDocument]] = {}
    for document in documents:
        key = _document_category_key(document.category)
        documents_by_category.setdefault(key, []).append(document)
    return render_template(
        "hr/policies.html",
        org=org,
        policy_sections=POLICY_SECTIONS,
        documents_by_category=documents_by_category,
        document_category_label=_document_category_label,
    )


@hr_bp.route("/documents")
def documents():
    org = Organization.query.get_or_404(current_user.org_id)
    documents = (
        HRDocument.query.filter_by(org_id=org.id)
        .options(
            joinedload(HRDocument.acknowledgements).joinedload(HRDocumentAcknowledgement.user)
        )
        .order_by(HRDocument.category.asc(), HRDocument.title.asc())
        .all()
    )
    employees = _load_users_for_org(org.id)
    active_employees = [user for user in employees if user.status == "active"]
    active_total = len(active_employees)
    document_rows = []
    for document in documents:
        ack_count = len(document.acknowledgements or [])
        ack_pct = round((ack_count / active_total) * 100) if active_total and document.requires_acknowledgement else None
        document_rows.append(
            {
                "document": document,
                "category_label": _document_category_label(document.category),
                "ack_count": ack_count,
                "ack_pct": ack_pct,
            }
        )
    return render_template(
        "hr/documents.html",
        org=org,
        documents=document_rows,
        active_tab="documents",
        active_total=active_total,
        category_options=DOCUMENT_CATEGORY_LABELS,
    )


@hr_bp.route("/documents/new", methods=["GET", "POST"])
def create_document():
    org = Organization.query.get_or_404(current_user.org_id)
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Document title is required.", "danger")
        else:
            category = _document_category_key(request.form.get("category"))
            requires_ack = bool(request.form.get("requires_ack"))
            document = HRDocument(
                org_id=org.id,
                title=title,
                category=category,
                version=(request.form.get("version") or None),
                summary=(request.form.get("summary") or None),
                link_url=(request.form.get("link_url") or None),
                content=(request.form.get("content") or None),
                requires_acknowledgement=requires_ack,
                created_by_id=current_user.id,
            )
            if request.form.get("publish_now"):
                document.published_at = datetime.utcnow()
            db.session.add(document)
            db.session.commit()
            flash("Document added to your HR library.", "success")
            return redirect(url_for("hr.documents"))
    return render_template(
        "hr/document_form.html",
        org=org,
        document=None,
        category_options=DOCUMENT_CATEGORY_LABELS,
        active_tab="documents",
    )


@hr_bp.route("/documents/<int:doc_id>", methods=["GET", "POST"])
def edit_document(doc_id: int):
    org = Organization.query.get_or_404(current_user.org_id)
    document = HRDocument.query.filter_by(id=doc_id, org_id=org.id).first_or_404()
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Document title is required.", "danger")
        else:
            document.title = title
            document.category = _document_category_key(request.form.get("category"))
            document.version = request.form.get("version") or None
            document.summary = request.form.get("summary") or None
            document.link_url = request.form.get("link_url") or None
            document.content = request.form.get("content") or None
            document.requires_acknowledgement = bool(request.form.get("requires_ack"))
            if request.form.get("publish_now") and not document.published_at:
                document.published_at = datetime.utcnow()
            db.session.add(document)
            db.session.commit()
            flash("Document updated.", "success")
            return redirect(url_for("hr.documents"))
    acknowledgements = (
        HRDocumentAcknowledgement.query.filter_by(org_id=org.id, document_id=document.id)
        .options(joinedload(HRDocumentAcknowledgement.user))
        .order_by(HRDocumentAcknowledgement.acknowledged_at.desc())
        .all()
    )
    return render_template(
        "hr/document_form.html",
        org=org,
        document=document,
        acknowledgements=acknowledgements,
        category_options=DOCUMENT_CATEGORY_LABELS,
        active_tab="documents",
    )


@hr_bp.route("/documents/<int:doc_id>/acknowledge", methods=["POST"])
@login_required
def acknowledge_document(doc_id: int):
    org = Organization.query.get_or_404(current_user.org_id)
    document = HRDocument.query.filter_by(id=doc_id, org_id=org.id).first_or_404()
    acknowledgement = HRDocumentAcknowledgement.query.filter_by(
        org_id=org.id,
        document_id=document.id,
        user_id=current_user.id,
    ).first()
    if acknowledgement:
        flash("You've already acknowledged this document.", "info")
    else:
        acknowledgement = HRDocumentAcknowledgement(
            org_id=org.id,
            document_id=document.id,
            user_id=current_user.id,
            acknowledged_at=datetime.utcnow(),
        )
        db.session.add(acknowledgement)
        db.session.commit()
        flash("Thanks! Your acknowledgement has been recorded.", "success")
    next_url = request.form.get("next") or url_for("hr.policies")
    return redirect(next_url)


@hr_bp.route("/complaints")
def complaints():
    org = Organization.query.get_or_404(current_user.org_id)
    complaints = (
        HRComplaint.query.filter_by(org_id=org.id)
        .options(joinedload(HRComplaint.reporter), joinedload(HRComplaint.assignee))
        .order_by(HRComplaint.created_at.desc())
        .all()
    )
    status_breakdown = Counter(complaint.status for complaint in complaints)
    priority_breakdown = Counter(complaint.priority for complaint in complaints)
    return render_template(
        "hr/complaints.html",
        org=org,
        complaints=complaints,
        status_breakdown=status_breakdown,
        priority_breakdown=priority_breakdown,
        status_choices=COMPLAINT_STATUS_CHOICES,
        priority_choices=COMPLAINT_PRIORITY_CHOICES,
        active_tab="complaints",
    )


@hr_bp.route("/complaints/<int:complaint_id>", methods=["GET", "POST"])
def complaint_detail(complaint_id: int):
    org = Organization.query.get_or_404(current_user.org_id)
    complaint = HRComplaint.query.filter_by(id=complaint_id, org_id=org.id).first_or_404()
    if request.method == "POST":
        complaint.status = request.form.get("status") or complaint.status
        complaint.priority = request.form.get("priority") or complaint.priority
        assignee_id = request.form.get("assignee_id")
        complaint.assigned_to_id = int(assignee_id) if assignee_id else None
        complaint.resolution_notes = request.form.get("resolution_notes") or None
        if complaint.status == "resolved" and not complaint.resolved_at:
            complaint.resolved_at = datetime.utcnow()
        elif complaint.status != "resolved":
            complaint.resolved_at = None
        db.session.add(complaint)
        db.session.commit()
        flash("Complaint updated.", "success")
        return redirect(url_for("hr.complaint_detail", complaint_id=complaint.id))
    team_members = _load_users_for_org(org.id)
    return render_template(
        "hr/complaint_detail.html",
        org=org,
        complaint=complaint,
        team_members=team_members,
        status_choices=COMPLAINT_STATUS_CHOICES,
        priority_choices=COMPLAINT_PRIORITY_CHOICES,
        active_tab="complaints",
    )


@hr_bp.route("/complaints/new", methods=["GET", "POST"])
def submit_complaint():
    org = Organization.query.get_or_404(current_user.org_id)
    if request.method == "POST":
        subject = (request.form.get("subject") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not subject or not description:
            flash("Subject and detailed description are required.", "danger")
        else:
            complaint = HRComplaint(
                org_id=org.id,
                reporter_id=current_user.id,
                subject=subject,
                category=_document_category_key(request.form.get("category")),
                description=description,
                priority=(request.form.get("priority") or "normal"),
            )
            db.session.add(complaint)
            db.session.commit()
            flash("Your report has been sent to HR.", "success")
            return redirect(url_for("hr.complaint_submitted", complaint_id=complaint.id))
    return render_template(
        "hr/complaint_form.html",
        org=org,
        priority_choices=COMPLAINT_PRIORITY_CHOICES,
        category_options=DOCUMENT_CATEGORY_LABELS,
    )


@hr_bp.route("/complaints/<int:complaint_id>/submitted")
def complaint_submitted(complaint_id: int):
    org = Organization.query.get_or_404(current_user.org_id)
    complaint = HRComplaint.query.filter_by(id=complaint_id, org_id=org.id).first_or_404()
    if complaint.reporter_id != current_user.id and current_user.role not in ACCESS_ROLES:
        abort(404)
    return render_template(
        "hr/complaint_submitted.html",
        org=org,
        complaint=complaint,
    )


@hr_bp.route("/employees/<int:user_id>", methods=["GET", "POST"])
def manage_employee(user_id: int):
    org = Organization.query.get_or_404(current_user.org_id)
    user = User.query.filter_by(id=user_id, org_id=org.id).first_or_404()
    if request.method == "POST":
        user.first_name = request.form.get("first_name") or None
        user.last_name = request.form.get("last_name") or None
        user.preferred_name = request.form.get("preferred_name") or None
        user.job_title = request.form.get("job_title") or None
        user.phone_number = request.form.get("phone_number") or None
        user.role = request.form.get("role") or user.role
        user.status = request.form.get("status") or user.status
        user.must_change_password = bool(request.form.get("must_change_password"))
        emergency_name = request.form.get("emergency_name")
        emergency_phone = request.form.get("emergency_phone")
        emergency_relation = request.form.get("emergency_relation")
        if emergency_name or emergency_phone or emergency_relation:
            user.emergency_contact = {
                "name": emergency_name,
                "phone": emergency_phone,
                "relationship": emergency_relation,
            }
        else:
            user.emergency_contact = None
        if user.producer:
            producer_name = request.form.get("producer_display_name") or None
            if producer_name:
                user.producer.display_name = producer_name
        db.session.add(user)
        db.session.commit()
        flash("Employee profile updated.", "success")
        return redirect(url_for("hr.manage_employee", user_id=user.id))

    acknowledgements = (
        HRDocumentAcknowledgement.query.filter_by(org_id=org.id, user_id=user.id)
        .options(joinedload(HRDocumentAcknowledgement.document))
        .order_by(HRDocumentAcknowledgement.acknowledged_at.desc())
        .all()
    )
    reported_complaints = (
        HRComplaint.query.filter_by(org_id=org.id, reporter_id=user.id)
        .order_by(HRComplaint.created_at.desc())
        .all()
    )
    assigned_complaints = (
        HRComplaint.query.filter_by(org_id=org.id, assigned_to_id=user.id)
        .order_by(HRComplaint.created_at.desc())
        .all()
    )
    payroll_query = PayrollEntry.query.filter_by(org_id=org.id)
    if user.producer:
        payroll_query = payroll_query.filter(
            or_(PayrollEntry.user_id == user.id, PayrollEntry.producer_id == user.producer.id)
        )
    else:
        payroll_query = payroll_query.filter(PayrollEntry.user_id == user.id)
    payroll_history = (
        payroll_query.options(joinedload(PayrollEntry.payroll_run))
        .order_by(PayrollEntry.created_at.desc())
        .limit(25)
        .all()
    )

    return render_template(
        "hr/edit_user.html",
        org=org,
        user=user,
        acknowledgements=acknowledgements,
        reported_complaints=reported_complaints,
        assigned_complaints=assigned_complaints,
        payroll_history=payroll_history,
        active_tab="directory",
    )
