"""Nylas email helpers for TrackYourSheets."""
from __future__ import annotations

import os
from typing import Iterable, Mapping

import requests
from flask import current_app


def send_import_notification(
    recipient: str,
    workspace,
    uploader,
    period: str,
    summary: Iterable[Mapping[str, object]],
) -> None:
    """Send a summary email when a statement import is uploaded."""
    api_key = os.environ.get("nyk_v0_eR1G99LoiMU4mhsZAv6Koo8ehZK6gQGNKUjTnIjevR5gSeq0htoZtrf5Mn4cI2Nl")
    grant_id = os.environ.get("54ddffa7-3b11-4982-a9a0-75a544c97e80")
    from_email = os.environ.get("itstheplugg@gmail.com", uploader.email)

    if not api_key or not grant_id or not recipient:
        current_app.logger.info(
            "Skipping Nylas notification; configuration incomplete.",
            extra={"recipient": recipient, "grant_id": bool(grant_id)},
        )
        return

    subject = f"New commission import for {workspace.name}"
    office_name = workspace.office.name if getattr(workspace, "office", None) else ""

    lines = [
        f"Workspace: {workspace.name}",
        *( [f"Office: {office_name}"] if office_name else [] ),
        f"Uploaded by: {uploader.email}",
        f"Statement period: {period}",
        "",
        "Carrier breakdown:",
    ]
    for item in summary:
        carrier = item.get("carrier", "Unspecified")
        rows = item.get("rows", 0)
        lines.append(f" • {carrier}: {rows} row(s)")

    body_text = "\n".join(lines)

    payload = {
        "from": {"email": from_email, "name": uploader.email},
        "to": [{"email": recipient}],
        "subject": subject,
        "body": body_text,
    }

    url = f"https://api.nylas.com/v3/grants/{grant_id}/messages/send"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code >= 400:
            current_app.logger.warning(
                "Nylas notification failed",
                extra={"status": response.status_code, "body": response.text},
            )
    except Exception as exc:  # pragma: no cover - network failures logged only
        current_app.logger.warning("Nylas notification error", exc_info=exc)


def send_workspace_invitation(
    recipient: str,
    inviter,
    workspace,
    role: str,
) -> None:
    api_key = os.environ.get("nyk_v0_eR1G99LoiMU4mhsZAv6Koo8ehZK6gQGNKUjTnIjevR5gSeq0htoZtrf5Mn4cI2Nl")
    grant_id = os.environ.get("54ddffa7-3b11-4982-a9a0-75a544c97e80")
    from_email = os.environ.get("itstheplugg@gmail.com", inviter.email if inviter else None)

    if not api_key or not grant_id or not recipient:
        current_app.logger.info(
            "Skipping invitation email; configuration incomplete.",
            extra={"recipient": recipient, "grant_id": bool(grant_id)},
        )
        return

    subject = f"You're invited to {workspace.name} on TrackYourSheets"
    inviter_name = inviter.email if inviter else "A teammate"
    body = (
        "\n".join(
            [
                f"Hi there,",
                "",
                f"{inviter_name} invited you to join the {workspace.name} workspace on TrackYourSheets.",
                f"Role: {role.title()}",
                "",
                "Sign in with your email to get started and review the in-app How-To guide for a quick tour.",
                "",
                "See you inside!",
                "TrackYourSheets Team",
            ]
        )
    )

    payload = {
        "from": {"email": from_email or inviter.email, "name": inviter_name},
        "to": [{"email": recipient}],
        "subject": subject,
        "body": body,
    }

    url = f"https://api.nylas.com/v3/grants/{grant_id}/messages/send"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code >= 400:
            current_app.logger.warning(
                "Workspace invitation email failed",
                extra={"status": response.status_code, "body": response.text},
            )
    except Exception as exc:  # pragma: no cover
        current_app.logger.warning("Workspace invitation email error", exc_info=exc)
