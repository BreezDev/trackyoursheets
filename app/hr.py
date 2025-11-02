"""HR portal blueprint providing people operations tooling inside TrackYourSheets."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Sequence

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from .models import (
    DEFAULT_NOTIFICATION_PREFERENCES,
    Office,
    OfficeMembership,
    Organization,
    Producer,
    User,
    Workspace,
    WorkspaceMembership,
)


ACCESS_ROLES = {"owner", "admin", "agent", "bookkeeper"}

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
    return render_template(
        "hr/policies.html",
        org=org,
        policy_sections=POLICY_SECTIONS,
    )
