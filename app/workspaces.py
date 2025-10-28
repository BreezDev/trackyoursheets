"""Workspace access helpers."""
from __future__ import annotations

from typing import List, Optional

from flask_login import UserMixin

from .models import Producer, Workspace


def get_accessible_workspaces(user: UserMixin) -> List[Workspace]:
    """Return the workspaces a user can manage or view."""
    if not getattr(user, "is_authenticated", False):
        return []

    base_query = Workspace.query.filter_by(org_id=user.org_id)

    if user.role in {"owner", "admin"}:
        return base_query.order_by(Workspace.name.asc()).all()

    if user.role == "agent":
        workspace = base_query.filter_by(agent_id=user.id).first()
        return [workspace] if workspace else []

    if user.role == "producer" and user.producer:
        return [user.producer.workspace] if user.producer.workspace else []

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

    if user.role == "agent":
        return accessible[0] if accessible else None

    if user.role == "producer":
        return accessible[0] if accessible else None

    return None


def get_accessible_producers(user: UserMixin) -> List[Producer]:
    """Return producers the user can view or manage."""
    if not getattr(user, "is_authenticated", False):
        return []

    query = Producer.query.filter_by(org_id=user.org_id)

    if user.role in {"owner", "admin"}:
        return query.order_by(Producer.display_name.asc()).all()

    if user.role == "agent":
        return (
            query.filter_by(agent_id=user.id)
            .order_by(Producer.display_name.asc())
            .all()
        )

    if user.role == "producer" and user.producer:
        return [user.producer]

    return []


def user_can_access_workspace(user: UserMixin, workspace_id: int) -> bool:
    return any(ws.id == workspace_id for ws in get_accessible_workspaces(user))
