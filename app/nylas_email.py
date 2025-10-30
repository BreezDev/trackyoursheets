"""Nylas email helpers for TrackYourSheets."""
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import os
from typing import Iterable, Mapping, MutableMapping, Optional, Sequence, Union

import requests
from flask import current_app

EmailRecipient = Union[str, Mapping[str, str]]


def _split_emails(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part and part.strip()]


def _deduplicate(recipients: Sequence[Mapping[str, str]]) -> list[Mapping[str, str]]:
    seen: set[str] = set()
    deduped: list[Mapping[str, str]] = []
    for entry in recipients:
        email = (entry.get("email") or "").lower()
        if not email or email in seen:
            continue
        seen.add(email)
        deduped.append(entry)
    return deduped


def _normalize_recipients(recipients: Sequence[EmailRecipient]) -> list[MutableMapping[str, str]]:
    normalised: list[MutableMapping[str, str]] = []
    for recipient in recipients:
        if isinstance(recipient, str):
            email = recipient.strip()
            if email:
                normalised.append({"email": email})
        elif isinstance(recipient, Mapping):
            email = (recipient.get("email") or "").strip()
            if not email:
                continue
            entry: MutableMapping[str, str] = {"email": email}
            name = (recipient.get("name") or "").strip()
            if name:
                entry["name"] = name
            normalised.append(entry)
    return _deduplicate(normalised)


def _nylas_config() -> dict:
    app = current_app._get_current_object()
    return {
        "api_key": app.config.get("NYLAS_API_KEY") or os.environ.get("NYLAS_API_KEY"),
        "grant_id": app.config.get("NYLAS_GRANT_ID") or os.environ.get("NYLAS_GRANT_ID"),
        "base_url": app.config.get("NYLAS_API_BASE_URL")
        or os.environ.get("NYLAS_API_BASE_URL", "https://api.nylas.com"),
        "from_email": app.config.get("NYLAS_FROM_EMAIL") or os.environ.get("NYLAS_FROM_EMAIL"),
        "from_name": app.config.get("NYLAS_FROM_NAME")
        or os.environ.get("NYLAS_FROM_NAME", "TrackYourSheets"),
        "reply_to": _split_emails(
            app.config.get("NYLAS_REPLY_TO") or os.environ.get("NYLAS_REPLY_TO")
        ),
        "default_notifications": _split_emails(
            app.config.get("NYLAS_NOTIFICATION_EMAILS")
            or os.environ.get("NYLAS_NOTIFICATION_EMAILS")
        ),
        "signup_alerts": _split_emails(
            app.config.get("NYLAS_SIGNUP_ALERT_EMAILS")
            or os.environ.get("NYLAS_SIGNUP_ALERT_EMAILS")
            or app.config.get("NYLAS_ALERT_RECIPIENTS")
            or os.environ.get("NYLAS_ALERT_RECIPIENTS")
        ),
    }


def _send_email(
    *,
    recipients: Sequence[EmailRecipient],
    subject: str,
    body: str,
    sender_email: Optional[str] = None,
    sender_name: Optional[str] = None,
    reply_to: Optional[Sequence[EmailRecipient]] = None,
    send_at: Optional[int] = None,
    is_html: bool = False,
    metadata: Optional[Mapping[str, object]] = None,
) -> bool:
    if not recipients:
        return False

    config = _nylas_config()
    api_key = config.get("api_key")
    grant_id = config.get("grant_id")
    from_email = sender_email or config.get("from_email")
    if not api_key or not grant_id or not from_email:
        current_app.logger.info(
            "Skipping Nylas send; configuration incomplete.",
            extra={
                "has_api_key": bool(api_key),
                "has_grant": bool(grant_id),
                "has_from": bool(from_email),
            },
        )
        return False

    to_payload = _normalize_recipients(recipients)
    if not to_payload:
        return False

    payload: dict[str, object] = {
        "from": {
            "email": from_email,
            "name": sender_name or config.get("from_name") or "TrackYourSheets",
        },
        "to": to_payload,
        "subject": subject,
        "body": body,
        "is_plaintext": not is_html,
    }

    effective_reply_to: list[EmailRecipient] = []
    if reply_to:
        effective_reply_to.extend(reply_to)
    elif config.get("reply_to"):
        effective_reply_to.extend(config["reply_to"])
    if effective_reply_to:
        payload["reply_to"] = _normalize_recipients(effective_reply_to)

    if send_at:
        payload["send_at"] = int(send_at)
    if metadata:
        payload["metadata"] = dict(metadata)

    base_url = (config.get("base_url") or "https://api.nylas.com").rstrip("/")
    url = f"{base_url}/v3/grants/{grant_id}/messages/send"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code >= 400:
            current_app.logger.warning(
                "Nylas send failed",
                extra={"status": response.status_code, "body": response.text},
            )
            return False
    except Exception as exc:  # pragma: no cover - network failures logged only
        current_app.logger.warning("Nylas send error", exc_info=exc)
        return False
    return True


def send_notification_email(
    recipients: Sequence[EmailRecipient],
    subject: str,
    body: str,
    *,
    include_default_recipients: bool = True,
    metadata: Optional[Mapping[str, object]] = None,
) -> bool:
    config = _nylas_config()
    target_list: list[EmailRecipient] = list(recipients or [])
    if include_default_recipients:
        target_list.extend(config.get("default_notifications", []))
    if not target_list:
        return False
    return _send_email(
        recipients=target_list,
        subject=subject,
        body=body,
        metadata=metadata,
    )


def send_import_notification(
    recipient: str,
    workspace,
    uploader,
    period: str,
    summary: Iterable[Mapping[str, object]],
) -> None:
    """Send a summary email when a statement import is uploaded."""

    subject = f"New commission import for {workspace.name}"
    office_name = workspace.office.name if getattr(workspace, "office", None) else ""

    lines = [
        f"Workspace: {workspace.name}",
        *([f"Office: {office_name}"] if office_name else []),
        f"Uploaded by: {getattr(uploader, 'email', 'Unknown uploader')}",
        f"Statement period: {period}",
        "",
        "Carrier breakdown:",
    ]
    for item in summary:
        carrier = item.get("carrier", "Unspecified")
        rows = item.get("rows", 0)
        lines.append(f" • {carrier}: {rows} row(s)")

    uploader_name = (
        getattr(uploader, "display_name_for_ui", None)
        or getattr(uploader, "email", None)
        or ""
    )

    _send_email(
        recipients=[recipient],
        subject=subject,
        body="\n".join(lines),
        sender_name=f"{uploader_name} via TrackYourSheets" if uploader_name else None,
        reply_to=[getattr(uploader, "email", "")] if getattr(uploader, "email", None) else None,
        metadata={
            "workspace_id": getattr(workspace, "id", None),
            "period": period,
        },
    )


def send_workspace_invitation(
    recipient: str,
    inviter,
    workspace,
    role: str,
) -> None:
    inviter_display = (
        getattr(inviter, "display_name_for_ui", None)
        or getattr(inviter, "email", None)
        or ""
    )
    inviter_name = inviter_display or "A teammate"
    body = (
        "\n".join(
            [
                "Hi there,",
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

    _send_email(
        recipients=[recipient],
        subject=f"You're invited to {workspace.name} on TrackYourSheets",
        body=body,
        sender_name=(
            f"{inviter_display} via TrackYourSheets"
            if inviter_display
            else "TrackYourSheets"
        ),
        reply_to=[getattr(inviter, "email", "")] if getattr(inviter, "email", None) else None,
        metadata={
            "workspace_id": getattr(workspace, "id", None),
            "role": role,
        },
    )


def send_signup_welcome(user, organization) -> None:
    if not getattr(user, "email", None):
        return
    org_name = getattr(organization, "name", "TrackYourSheets")
    subject = "Welcome to TrackYourSheets"
    body = "\n".join(
        [
            f"Hi {user.email},",
            "",
            "Thanks for activating your TrackYourSheets subscription!",
            f"Your organisation, {org_name}, is ready to automate producer payouts, streamline imports, and collaborate in workspaces.",
            "",
            "Get started by:",
            " • Adding your first workspace and agent",
            " • Uploading a carrier statement to see the pipeline in action",
            " • Inviting teammates from the admin console",
            "",
            "Need help? Reply to this email and our team will jump in.",
            "",
            "Let's build with you,",
            "TrackYourSheets Support",
        ]
    )
    _send_email(
        recipients=[user.email],
        subject=subject,
        body=body,
    )


def send_signup_alert(user, organization) -> None:
    config = _nylas_config()
    recipients = config.get("signup_alerts", [])
    if not recipients:
        return
    org_name = getattr(organization, "name", "Unknown org")
    lines = [
        "New organisation signup",
        "",
        f"Organisation: {org_name}",
        f"User: {getattr(user, 'email', 'Unknown user')}",
    ]
    if getattr(organization, "plan", None):
        lines.append(f"Selected plan: {organization.plan.name}")
    _send_email(
        recipients=recipients,
        subject=f"New TrackYourSheets signup: {org_name}",
        body="\n".join(lines),
        metadata={"org_id": getattr(organization, "id", None)},
    )
