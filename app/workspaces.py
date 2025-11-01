"""Workspace access helpers."""
from __future__ import annotations

from typing import List, Optional

from flask_login import UserMixin

from .models import Producer, Workspace


def _membership_workspace_ids(user: UserMixin) -> set[int]:
    memberships = getattr(user, "workspace_memberships", []) or []
    return {
        membership.workspace_id
        for membership in memberships
        if getattr(membership, "workspace_id", None)
    }


def get_accessible_workspaces(user: UserMixin) -> List[Workspace]:
    """Return the workspaces a user can manage or view."""
    if not getattr(user, "is_authenticated", False):
        return []

    base_query = Workspace.query.filter_by(org_id=user.org_id)

    if user.role in {"owner", "admin"}:
        return base_query.order_by(Workspace.name.asc()).all()

    if user.role == "agent":
        managed = base_query.filter_by(agent_id=user.id).all()
        membership_ids = _membership_workspace_ids(user)
        if membership_ids:
            additional = (
                base_query.filter(Workspace.id.in_(membership_ids))
                .order_by(Workspace.name.asc())
                .all()
            )
        else:
            additional = []
        combined = {ws.id: ws for ws in managed + additional if ws}
        return list(combined.values())

    if user.role == "producer" and user.producer:
        workspaces = []
        if user.producer.workspace:
            workspaces.append(user.producer.workspace)
        membership_ids = _membership_workspace_ids(user)
        if membership_ids:
            additional = (
                base_query.filter(Workspace.id.in_(membership_ids))
                .order_by(Workspace.name.asc())
                .all()
            )
            for workspace in additional:
                if workspace and workspace not in workspaces:
                    workspaces.append(workspace)
        return workspaces

    membership_ids = _membership_workspace_ids(user)
    if membership_ids:
        return (
            base_query.filter(Workspace.id.in_(membership_ids))
            .order_by(Workspace.name.asc())
            .all()
        )

    return []


def get_accessible_workspace_ids(user: UserMixin) -> List[int]:
    return [ws.id for ws in get_accessible_workspaces(user) if ws]


def find_workspace_for_upload(user: UserMixin, workspace_id: Optional[int]) -> Optional[Workspace]:
    """Resolve the workspace that should receive an upload for the given user."""
    accessible = get_accessible_workspaces(user)

    if user.role in {"owner", "admin"}:
        if workspace_id is None:
            return accessible[0] if len(accessible) == 1 else None
        return next((ws for ws in accessible if ws.id == workspace_id), None)

    if user.role in {"agent", "producer"}:
        if workspace_id and any(ws.id == workspace_id for ws in accessible):
            return next((ws for ws in accessible if ws.id == workspace_id), None)
        return accessible[0] if accessible else None

    if workspace_id and any(ws.id == workspace_id for ws in accessible):
        return next((ws for ws in accessible if ws.id == workspace_id), None)
    if len(accessible) == 1:
        return accessible[0]

    return None


def get_accessible_producers(user: UserMixin) -> List[Producer]:
    """Return producers the user can view or manage."""
    if not getattr(user, "is_authenticated", False):
        return []

    query = Producer.query.filter_by(org_id=user.org_id)

    if user.role in {"owner", "admin"}:
        return query.order_by(Producer.display_name.asc()).all()

    if user.role == "agent":
        workspace_ids = get_accessible_workspace_ids(user)
        if workspace_ids:
            query = query.filter(Producer.workspace_id.in_(workspace_ids))
        else:
            query = query.filter_by(agent_id=user.id)
        return query.order_by(Producer.display_name.asc()).all()

    if user.role == "producer" and user.producer:
        return [user.producer]

    workspace_ids = get_accessible_workspace_ids(user)
    if workspace_ids:
        return (
            query.filter(Producer.workspace_id.in_(workspace_ids))
            .order_by(Producer.display_name.asc())
            .all()
        )

    return []


def user_can_access_workspace(user: UserMixin, workspace_id: int) -> bool:
    return any(ws.id == workspace_id for ws in get_accessible_workspaces(user))
