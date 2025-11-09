"""Resend email helpers for TrackYourSheets."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import os
import html
import threading
import time
from typing import Iterable, Mapping, MutableMapping, Optional, Sequence, Union

import requests

import resend
from flask import current_app

EmailRecipient = Union[str, Mapping[str, str]]

_SEND_THROTTLE_SECONDS = 10.0
_send_lock = threading.Lock()
_last_send_ts: float = 0.0


def _throttle_email_sends() -> None:
    """Ensure we respect downstream rate limits when sending emails."""

    global _last_send_ts
    with _send_lock:
        now = time.monotonic()
        wait_for = _SEND_THROTTLE_SECONDS - (now - _last_send_ts)
        if wait_for > 0:
            time.sleep(wait_for)
        _last_send_ts = time.monotonic()


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


def _escape(value: object) -> str:
    return html.escape(str(value) if value is not None else "", quote=True)


def _paragraph(text: str) -> str:
    return (
        f'<p style="margin:0 0 16px;line-height:1.6;color:#1e293b;font-size:16px;">{_escape(text)}</p>'
    )


def _highlight_block(content: str) -> str:
    return (
        "<div style=\"margin:28px 0;padding:24px;border-radius:14px;background:#eef2ff;text-align:center;\">"
        f"<span style=\"display:inline-block;font-size:30px;letter-spacing:8px;font-weight:600;color:#312e81;\">{_escape(content)}" "</span>"
        "</div>"
    )


def _button(label: str, url: str) -> str:
    return (
        "<div style=\"margin-top:24px;\">"
        f"<a href=\"{_escape(url)}\" style=\"display:inline-block;padding:14px 28px;border-radius:999px;background:#2563eb;color:#ffffff;font-weight:600;text-decoration:none;\">{_escape(label)}</a>"
        "</div>"
    )


def _unordered_list(items: Iterable[str]) -> str:
    list_items = "".join(
        f"<li style=\"margin-bottom:8px;\">{_escape(item)}" "</li>" for item in items
    )
    return (
        "<ul style=\"padding-left:20px;margin:0 0 16px;line-height:1.6;color:#1e293b;font-size:16px;\">"
        f"{list_items}" "</ul>"
    )


def _plain_text_with_footer(lines: Iterable[str]) -> str:
    output = list(lines)
    if output and output[-1] != "":
        output.append("")
    output.append("Need help? Email contact@trackyoursheets.com.")
    output.append("Follow @trackyoursheets on Instagram for automation tips.")
    return "\n".join(output)


def _email_card(title: str, body_parts: Iterable[str]) -> str:
    content = "".join(body_parts)
    return (
        "<div style=\"background:#f8fafc;padding:32px 0;\">"
        "<div style=\"max-width:560px;margin:0 auto;padding:0 24px;font-family:'Inter',Arial,sans-serif;color:#0f172a;\">"
        "<div style=\"background:#ffffff;border-radius:18px;padding:32px 32px 40px;box-shadow:0 22px 48px rgba(15,23,42,0.12);\">"
        f"<h1 style=\"font-size:24px;line-height:1.25;margin:0 0 18px;font-weight:600;color:#0f172a;\">{_escape(title)}</h1>"
        f"{content}"
        "</div>"
        "<div style=\"text-align:center;font-size:13px;color:#475569;margin-top:24px;line-height:1.6;\">"
        "<p style=\"margin:0;\">Questions? Email <a href=\"mailto:contact@trackyoursheets.com\" style=\"color:#2563eb;text-decoration:none;font-weight:500;\">contact@trackyoursheets.com</a>.</p>"
        "<p style=\"margin:8px 0 0;\">Follow <a href=\"https://www.instagram.com/trackyoursheets\" style=\"color:#2563eb;text-decoration:none;font-weight:500;\">@trackyoursheets</a> on Instagram for automation tips.</p>"
        "</div>"
        "</div>"
        "</div>"
    )


def verify_email_deliverability(address: str) -> Optional[bool]:
    if not address:
        return None
    config = _resend_config()
    api_key = config.get("api_key")
    if not api_key:
        return None
    try:
        response = requests.post(
            "https://api.resend.com/emails/verify",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"email": address},
            timeout=5,
        )
    except Exception:
        return None

    if response.status_code != 200:
        return None

    try:
        payload = response.json()
    except ValueError:
        return None

    status = (payload.get("status") or payload.get("deliverability") or "").lower()
    if status in {"deliverable", "valid", "true"}:
        return True
    if status in {"undeliverable", "invalid", "false"}:
        return False

    verdict = payload.get("result") or payload.get("is_deliverable")
    if verdict is None:
        return None
    if isinstance(verdict, bool):
        return verdict
    if isinstance(verdict, str):
        lowered = verdict.lower()
        if lowered in {"true", "deliverable", "valid"}:
            return True
        if lowered in {"false", "undeliverable", "invalid"}:
            return False
    return None


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
    text_body: Optional[str] = None,
    html_body: Optional[str] = None,
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

    if html_body:
        params["html"] = html_body
    elif is_html:
        params["html"] = body
    else:
        params["html"] = _as_html(body)

    if text_body is not None:
        params["text"] = text_body
    else:
        params["text"] = body

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

    _throttle_email_sends()

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
    ]
    summary_items = []
    for item in summary:
        carrier = item.get("carrier", "Unspecified")
        rows = item.get("rows", 0)
        summary_items.append(f"{carrier}: {rows} row(s)")

    uploader_name = (
        getattr(uploader, "display_name_for_ui", None)
        or getattr(uploader, "email", None)
        or ""
    )

    reply_to: Optional[list[EmailRecipient]] = None
    if getattr(uploader, "email", None):
        reply_to = [getattr(uploader, "email", "")]

    html_parts = [
        _paragraph("A new commission import is ready for review."),
        _paragraph(f"Workspace: {workspace.name}"),
    ]
    if office_name:
        html_parts.append(_paragraph(f"Office: {office_name}"))
    html_parts.append(
        _paragraph(
            f"Uploaded by {getattr(uploader, 'email', 'Unknown uploader')} for period {period}."
        )
    )
    if summary_items:
        html_parts.append(_paragraph("Carrier breakdown:"))
        html_parts.append(_unordered_list(summary_items))
    text_lines = [
        f"A new commission import is ready for review in {workspace.name}.",
        *([f"Office: {office_name}"] if office_name else []),
        f"Uploaded by: {getattr(uploader, 'email', 'Unknown uploader')}",
        f"Statement period: {period}",
    ]
    if summary_items:
        text_lines.append("")
        text_lines.append("Carrier breakdown:")
        text_lines.extend(f"- {item}" for item in summary_items)
    text_body = _plain_text_with_footer(text_lines)
    html_body = _email_card(subject, html_parts)

    _send_email(
        recipients=recipients,
        subject=subject,
        body=text_body,
        text_body=text_body,
        html_body=html_body,
        sender_name=f"{uploader_name} via TrackYourSheets" if uploader_name else None,
        reply_to=reply_to,
        metadata={
            "workspace_id": getattr(workspace, "id", None),
            "period": period,
        },
        is_html=True,
    )


def send_workspace_invitation(
    recipient: str,
    inviter,
    workspace=None,
    role: str | None = None,
    *,
    temporary_password: str,
    login_url: str,
) -> None:
    inviter_display = (
        getattr(inviter, "display_name_for_ui", None)
        or getattr(inviter, "email", None)
        or ""
    )
    inviter_name = inviter_display or "A teammate"
    workspace_name = getattr(workspace, "name", None)
    office_name = getattr(getattr(workspace, "office", None), "name", None)
    if workspace_name:
        subject = f"You're invited to {workspace_name} on TrackYourSheets"
        intro = f"{inviter_name} invited you to join the {workspace_name} workspace."
    else:
        subject = "You're invited to TrackYourSheets"
        intro = (
            f"{inviter_name} invited you to collaborate in TrackYourSheets. "
            "You'll be able to join offices and workspaces as soon as you sign in."
        )

    html_parts = [
        _paragraph(intro),
        _paragraph(f"Role: {role.title()}") if role else "",
    ]
    if office_name:
        html_parts.append(
            _paragraph(
                f"Primary office: {office_name}. You can join additional offices once you're signed in."
            )
        )
    html_parts.extend(
        [
            _paragraph(
                "Use the temporary password below to sign in and you'll be prompted to create your own."
            ),
            _highlight_block(temporary_password),
            _paragraph("Keep this password safe—it expires once you update it."),
            _button("Open TrackYourSheets", login_url),
        ]
    )
    html_parts = [part for part in html_parts if part]
    html_parts.append(
        _paragraph(
            "Need a refresher? Explore the in-app How-To guide for imports, payouts, workspace chat, payroll tracking, and office assignments."
        )
    )
    text_intro = (
        f"{inviter_name} invited you to join the {workspace_name} workspace on TrackYourSheets."
        if workspace_name
        else f"{inviter_name} invited you to TrackYourSheets. Join offices and workspaces after you sign in."
    )
    text_lines = [
        text_intro,
        f"Role: {role.title()}" if role else None,
        (f"Primary office: {office_name}" if office_name else None),
        "",  # spacer
        "Temporary password:",
        temporary_password,
        "",
        "Sign in with your email, then set a new password when prompted.",
        login_url,
    ]
    text_lines = [line for line in text_lines if line is not None]
    text_body = _plain_text_with_footer(text_lines)
    html_body = _email_card(subject, html_parts)

    reply_to: Optional[list[EmailRecipient]] = None
    if getattr(inviter, "email", None):
        reply_to = [getattr(inviter, "email", "")]

    _send_email(
        recipients=[recipient],
        subject=subject,
        body=text_body,
        text_body=text_body,
        html_body=html_body,
        is_html=True,
        sender_name=(
            f"{inviter_display} via TrackYourSheets"
            if inviter_display
            else "TrackYourSheets"
        ),
        reply_to=reply_to,
        metadata={
            "workspace_id": getattr(workspace, "id", None),
            "role": role,
            "office_id": getattr(getattr(workspace, "office", None), "id", None)
            if workspace
            else None,
        },
    )


def send_signup_welcome(user, organization) -> None:
    if not getattr(user, "email", None):
        return
    org_name = getattr(organization, "name", "TrackYourSheets")
    subject = "Welcome to TrackYourSheets"
    text_lines = [
        f"Hi {user.email},",
        "",
        "Thanks for activating your TrackYourSheets subscription!",
        f"Your organisation, {org_name}, is ready to automate producer payouts, streamline imports, and collaborate in workspaces.",
        "",
        "Get started by:",
        "- Adding your first workspace and agent",
        "- Uploading a carrier statement to see the pipeline in action",
        "- Inviting teammates from the admin console",
        "",
        "Reply to this email if you need a hand—our team is standing by.",
    ]
    text_body = _plain_text_with_footer(text_lines)
    html_parts = [
        _paragraph(f"Hi {user.email},"),
        _paragraph(
            f"Thanks for activating your TrackYourSheets subscription! {org_name} is ready to automate producer payouts, streamline imports, and collaborate in workspaces."
        ),
        _paragraph("Get started by:"),
        _unordered_list(
            [
                "Adding your first workspace and assigning an agent",
                "Uploading a carrier statement to watch the pipeline in action",
                "Inviting teammates from the admin console",
            ]
        ),
        _paragraph("Need a hand? Reply to this email and our team will jump in."),
    ]
    html_body = _email_card(subject, html_parts)
    _send_email(
        recipients=[user.email],
        subject=subject,
        body=text_body,
        text_body=text_body,
        html_body=html_body,
        is_html=True,
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
    text_body = _plain_text_with_footer(lines)
    html_parts = [
        _paragraph("New organisation signup"),
        _unordered_list(
            [
                f"Organisation: {org_name}",
                f"User: {getattr(user, 'email', 'Unknown user')}",
                *(
                    [f"Selected plan: {organization.plan.name}"]
                    if getattr(organization, "plan", None)
                    else []
                ),
            ]
        ),
    ]
    html_body = _email_card(title=f"New TrackYourSheets signup: {org_name}", body_parts=html_parts)

    _send_email(
        recipients=recipients,
        subject=f"New TrackYourSheets signup: {org_name}",
        body=text_body,
        text_body=text_body,
        html_body=html_body,
        is_html=True,
        metadata={"org_id": getattr(organization, "id", None)},
    )


def send_two_factor_code_email(email: str, code: str, *, intent: str) -> None:
    if not email:
        return
    subject = f"TrackYourSheets security code ({intent.title()})"
    text_lines = [
        "We received a request to verify your identity.",
        "",
        f"Security code: {code}",
        "",
        "The code expires in 10 minutes. If you didn't request this, reset your password immediately.",
    ]
    text_body = _plain_text_with_footer(text_lines)
    html_parts = [
        _paragraph("We received a request to verify your identity."),
        _highlight_block(code),
        _paragraph("This code expires in 10 minutes. If you didn't request it, reset your password immediately."),
    ]
    html_body = _email_card(subject, html_parts)
    _send_email(
        recipients=[email],
        subject=subject,
        body=text_body,
        text_body=text_body,
        html_body=html_body,
        is_html=True,
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
    text_body = _plain_text_with_footer(lines)
    html_parts = [
        _paragraph("You successfully signed in to TrackYourSheets."),
    ]
    if ip_address:
        html_parts.append(_paragraph(f"Sign-in from: {ip_address}"))
    html_parts.append(
        _paragraph("If this wasn't you, reset your password immediately and let us know.")
    )
    html_body = _email_card("TrackYourSheets login confirmation", html_parts)
    _send_email(
        recipients=[email],
        subject="TrackYourSheets login confirmation",
        body=text_body,
        text_body=text_body,
        html_body=html_body,
        is_html=True,
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
    summary_lines = [line.strip() for line in (summary or "").splitlines() if line.strip()]
    text_lines = [
        f"{actor_name} updated the {workspace.name} workspace.",
        "",
        *(summary_lines or [summary or ""]),
        "",
        "Visit your dashboard to review the latest changes.",
    ]
    text_body = _plain_text_with_footer(text_lines)
    html_parts = [
        _paragraph(f"{actor_name} updated the {workspace.name} workspace."),
    ]
    if summary_lines:
        for line in summary_lines:
            html_parts.append(_paragraph(line))
    else:
        html_parts.append(_paragraph(summary))
    html_parts.append(_paragraph("Visit your dashboard to review the latest changes."))
    html_body = _email_card(f"Workspace activity: {workspace.name}", html_parts)
    _send_email(
        recipients=recipients,
        subject=f"Workspace activity: {workspace.name}",
        body=text_body,
        text_body=text_body,
        html_body=html_body,
        is_html=True,
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
    message_lines = [line.strip() for line in (message or "").splitlines() if line.strip()]
    text_lines = [
        f"{actor_name} posted a new message in {workspace.name}.",
        "",
        *(message_lines or [message or ""]),
        "",
        "Reply from TrackYourSheets to keep momentum going.",
    ]
    text_body = _plain_text_with_footer(text_lines)
    html_parts = [
        _paragraph(f"{actor_name} posted a new message in {workspace.name}."),
    ]
    if message_lines:
        for line in message_lines:
            html_parts.append(_paragraph(line))
    else:
        html_parts.append(_paragraph(message))
    html_parts.append(_paragraph("Reply from TrackYourSheets to keep momentum going."))
    html_body = _email_card(f"New workspace message: {workspace.name}", html_parts)
    _send_email(
        recipients=recipients,
        subject=f"New workspace message: {workspace.name}",
        body=text_body,
        text_body=text_body,
        html_body=html_body,
        is_html=True,
        metadata={
            "workspace_id": getattr(workspace, "id", None),
            "purpose": "workspace-chat",
        },
    )
