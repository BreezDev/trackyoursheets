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
    api_key = os.environ.get("NYLAS_API_KEY")
    grant_id = os.environ.get("NYLAS_GRANT_ID")
    from_email = os.environ.get("NYLAS_FROM_EMAIL", uploader.email)

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
