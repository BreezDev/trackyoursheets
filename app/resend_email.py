"""Resend email helpers for TrackYourSheets."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import os
from typing import Iterable, Mapping, MutableMapping, Optional, Sequence, Union

import resend
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


def _resend_config() -> dict:
    app = current_app._get_current_object()
    return {
        "api_key": app.config.get("RESEND_API_KEY") or os.environ.get("RESEND_API_KEY"),
        "from_email": app.config.get("RESEND_FROM_EMAIL")
        or os.environ.get("RESEND_FROM_EMAIL"),
        "from_name": app.config.get("RESEND_FROM_NAME")
        or os.environ.get("RESEND_FROM_NAME", "TrackYourSheets"),
        "reply_to": _split_emails(
            app.config.get("RESEND_REPLY_TO") or os.environ.get("RESEND_REPLY_TO")
        ),
        "default_notifications": _split_emails(
            app.config.get("RESEND_NOTIFICATION_EMAILS")
            or os.environ.get("RESEND_NOTIFICATION_EMAILS")
        ),
        "signup_alerts": _split_emails(
            app.config.get("RESEND_SIGNUP_ALERT_EMAILS")
            or os.environ.get("RESEND_SIGNUP_ALERT_EMAILS")
            or app.config.get("RESEND_ALERT_RECIPIENTS")
            or os.environ.get("RESEND_ALERT_RECIPIENTS")
        ),
    }


def _build_sender(email: str, name: Optional[str]) -> str:
    if name:
        name = name.strip()
    if name:
        return f"{name} <{email}>"
    return email


def _as_html(body: str) -> str:
    lines = body.splitlines() or [body]
    safe_lines = [line.replace("<", "&lt;").replace(">", "&gt;") for line in lines]
    return "<p>" + "<br>".join(safe_lines) + "</p>"


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

    config = _resend_config()
    api_key = config.get("api_key")
    from_email = sender_email or config.get("from_email")
    if not api_key or not from_email:
        current_app.logger.info(
            "Skipping Resend send; configuration incomplete.",
            extra={
                "has_api_key": bool(api_key),
                "has_from": bool(from_email),
            },
        )
        return False

    to_payload = _normalize_recipients(recipients)
    if not to_payload:
        return False

    resend.api_key = api_key

    sender_identity = sender_name or config.get("from_name") or "TrackYourSheets"
    sender = _build_sender(from_email, sender_identity)

    params: dict[str, object] = {
        "from": sender,
        "to": [entry["email"] for entry in to_payload],
        "subject": subject,
    }

    if is_html:
        params["html"] = body
    else:
        params["text"] = body
        params["html"] = _as_html(body)

    effective_reply_to: list[EmailRecipient] = []
    if reply_to:
        effective_reply_to.extend(reply_to)
    elif config.get("reply_to"):
        effective_reply_to.extend(config["reply_to"])
    if effective_reply_to:
        reply_to_payload = _normalize_recipients(effective_reply_to)
        if reply_to_payload:
            params["reply_to"] = [entry["email"] for entry in reply_to_payload]

    if metadata:
        tags: list[dict[str, str]] = []
        for key, value in metadata.items():
            if value is None:
                continue
            tags.append({"name": str(key), "value": str(value)})
        if tags:
            params["tags"] = tags

    if send_at:
        params["scheduled_at"] = send_at

    try:
        resend.Emails.send(params)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - network failures logged only
        current_app.logger.warning("Resend send error", exc_info=exc)
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
    config = _resend_config()
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
    recipients: Sequence[EmailRecipient],
    workspace,
    uploader,
    period: str,
    summary: Iterable[Mapping[str, object]],
) -> None:
    """Send a summary email when a statement import is uploaded."""

    if not recipients:
        return

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

    reply_to: Optional[list[EmailRecipient]] = None
    if getattr(uploader, "email", None):
        reply_to = [getattr(uploader, "email", "")]

    _send_email(
        recipients=recipients,
        subject=subject,
        body="\n".join(lines),
        sender_name=f"{uploader_name} via TrackYourSheets" if uploader_name else None,
        reply_to=reply_to,
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

    reply_to: Optional[list[EmailRecipient]] = None
    if getattr(inviter, "email", None):
        reply_to = [getattr(inviter, "email", "")]

    _send_email(
        recipients=[recipient],
        subject=f"You're invited to {workspace.name} on TrackYourSheets",
        body=body,
        sender_name=(
            f"{inviter_display} via TrackYourSheets"
            if inviter_display
            else "TrackYourSheets"
        ),
        reply_to=reply_to,
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
    config = _resend_config()
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


def send_two_factor_code_email(email: str, code: str, *, intent: str) -> None:
    if not email:
        return
    subject = f"TrackYourSheets security code ({intent.title()})"
    body = "\n".join(
        [
            "We received a request to verify your identity.",
            "",
            f"Security code: {code}",
            "",
            "The code expires in 10 minutes. If you didn't request this, reset your password immediately.",
        ]
    )
    _send_email(
        recipients=[email],
        subject=subject,
        body=body,
        metadata={"purpose": f"2fa-{intent}"},
    )


def send_login_notification(email: str, *, ip_address: Optional[str] = None) -> None:
    if not email:
        return
    lines = [
        "You successfully signed in to TrackYourSheets.",
    ]
    if ip_address:
        lines.append(f"Sign-in from: {ip_address}")
    lines.extend(
        [
            "",
            "If this wasn't you, reset your password and contact support.",
        ]
    )
    _send_email(
        recipients=[email],
        subject="TrackYourSheets login confirmation",
        body="\n".join(lines),
        metadata={"purpose": "login-alert"},
    )


def send_workspace_update_notification(
    recipients: Sequence[EmailRecipient],
    *,
    workspace,
    actor,
    summary: str,
) -> None:
    if not recipients:
        return
    actor_name = (
        getattr(actor, "display_name_for_ui", None)
        or getattr(actor, "email", None)
        or "A teammate"
    )
    body = "\n".join(
        [
            f"{actor_name} updated the {workspace.name} workspace.",
            "",
            summary,
            "",
            "Visit your dashboard to review the latest changes.",
        ]
    )
    _send_email(
        recipients=recipients,
        subject=f"Workspace activity: {workspace.name}",
        body=body,
        metadata={
            "workspace_id": getattr(workspace, "id", None),
            "purpose": "workspace-update",
        },
    )


def send_workspace_chat_notification(
    recipients: Sequence[EmailRecipient],
    *,
    workspace,
    actor,
    message: str,
) -> None:
    if not recipients:
        return
    actor_name = (
        getattr(actor, "display_name_for_ui", None)
        or getattr(actor, "email", None)
        or "A teammate"
    )
    body = "\n".join(
        [
            f"{actor_name} posted a new message in {workspace.name}.",
            "",
            message,
            "",
            "Reply from TrackYourSheets to keep momentum going.",
        ]
    )
    _send_email(
        recipients=recipients,
        subject=f"New workspace message: {workspace.name}",
        body=body,
        metadata={
            "workspace_id": getattr(workspace, "id", None),
            "purpose": "workspace-chat",
        },
    )
