# Resend integration reference

TrackYourSheets sends transactional emails through the Resend API. This guide outlines configuration, helper utilities, and the key application touch points that now render branded HTML cards with consistent footers and Instagram callouts.

## Configuration

Environment variables (or Flask config overrides) set in `app/__init__.py` and consumed by `app/resend_email.py`:

- `RESEND_API_KEY` – API token for the Resend workspace.
- `RESEND_FROM_EMAIL` / `RESEND_FROM_NAME` – sender identity for outbound messages.
- `RESEND_REPLY_TO` – optional comma-separated reply-to addresses.
- `RESEND_NOTIFICATION_EMAILS` – default operational recipients appended to alerts.
- `RESEND_SIGNUP_ALERT_EMAILS` (falls back to `RESEND_ALERT_RECIPIENTS`) – internal alerts for new signups.

All variables can live in `.env`; they are automatically loaded into Flask config at startup. Missing credentials cause send attempts to no-op gracefully while logging a message, keeping local development friction-free.

## Helper utilities

`app/resend_email.py` centralises send logic:

- `_resend_config()` pulls configuration values, expands default notification lists, and keeps optional reply-to addresses handy.
- `_send_email(...)` builds the API payload, attaches metadata tags, and invokes `resend.Emails.send(...)` with a 10s timeout. Payloads always include a text fallback; HTML bodies can be passed directly or composed with the helper utilities below.
- `_email_card(...)`, `_paragraph(...)`, `_button(...)`, `_highlight_block(...)`, and `_unordered_list(...)` compose branded card layouts used across login, invite, import, and notification emails. Cards automatically append the `contact@trackyoursheets.com` and Instagram footer.
- `_plain_text_with_footer(...)` mirrors the footer copy for the plain-text part of each message.
- `verify_email_deliverability(email)` pings Resend’s deliverability endpoint and returns `True`, `False`, or `None` (unknown) so the UI can nudge users to fix bad addresses before retries.
- `send_notification_email(...)` fans out operational alerts (plan changes, coupons, etc.), automatically including default notification recipients when requested.
- `send_import_notification(...)` summarises import uploads with workspace/office context and optional reply-to targeting the uploader.
- `send_workspace_invitation(...)` now includes the generated temporary password, CTA button, and metadata linking back to the workspace for audit trails.
- `send_signup_welcome(...)` / `send_signup_alert(...)` cover signup completion while highlighting the new onboarding steps.
- `send_two_factor_code_email(...)`, `send_login_notification(...)`, `send_workspace_update_notification(...)`, and `send_workspace_chat_notification(...)` share the same card presentation for 2FA, login alerts, workspace membership changes, and chat activity.

Each helper accepts plain strings or `{ "email": ..., "name": ... }` mappings for recipients. Deduplication and whitespace trimming happen automatically.

## Application touch points

- **Signup:** After the Stripe checkout success handler (`auth.signup_complete`) updates the organisation, it triggers `send_signup_welcome`, internal alerts, and two-factor verification emails rendered with the new card layout.
- **Settings & billing:** Plan confirmations, coupon redemptions, and plan changes use `send_notification_email` to reach billing contacts who opted in.
- **Imports:** Upload summaries call `send_import_notification`, which includes a detailed carrier breakdown plus reply-to routing back to the uploader.
- **Workspace invitations:** Admin actions call `send_workspace_invitation` after creating the user. The email includes the generated temporary password, direct login link, and metadata to audit who invited whom.
- **Workspace activity:** Shared notes, chat messages, login alerts, and workspace membership updates utilise the dedicated helpers so every message stays visually consistent.
- **Email validation nudges:** Login and signup flows call `verify_email_deliverability` to advise users when an address looks undeliverable before retrying.

## Testing & troubleshooting

1. Verify `RESEND_API_KEY` and `RESEND_FROM_EMAIL` are present.
2. Trigger a workflow (e.g., complete signup or redeem a coupon) and watch the Flask logs for `Resend send error` entries if something misfires.
3. Inspect metadata tags in Resend or logs to correlate messages with organisations and actions.
4. When testing locally without credentials, expect helpers to return `False` and log that configuration is incomplete—this is intentional to keep dev ergonomics smooth.
