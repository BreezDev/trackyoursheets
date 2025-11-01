# Resend integration reference

TrackYourSheets sends transactional emails through the Resend API. This guide outlines configuration, helper functions, and touc
h points in the app.

## Configuration

Environment variables (or Flask config overrides) set in `app/__init__.py` and consumed by `app/resend_email.py`:

- `RESEND_API_KEY` – API token for the Resend workspace.
- `RESEND_FROM_EMAIL` / `RESEND_FROM_NAME` – sender identity for outbound messages.
- `RESEND_REPLY_TO` – optional comma-separated reply-to addresses.
- `RESEND_NOTIFICATION_EMAILS` – default operational recipients appended to alerts.
- `RESEND_SIGNUP_ALERT_EMAILS` (falls back to `RESEND_ALERT_RECIPIENTS`) – internal alerts for new signups.

All variables can live in `.env`; they are automatically loaded into Flask config at startup. Missing credentials cause send atte
mpts to no-op gracefully while logging a message, keeping local development friction-free.

## Helper utilities

`app/resend_email.py` centralises send logic:

- `_resend_config()` pulls configuration values and normalises recipient lists.
- `_send_email(...)` builds the API payload, applies reply-to rules, attaches metadata tags, and calls `resend.Emails.send(...)` wi
th a 10s timeout. Failures are logged with context.
- `send_notification_email(...)` fans out operational alerts (plan changes, coupons, etc.), automatically including default notif
ication recipients when requested.
- `send_import_notification(...)` summarises import uploads and includes uploader context.
- `send_workspace_invitation(...)` delivers workspace invites from the admin console.
- `send_signup_welcome(...)` and `send_signup_alert(...)` fire during signup completion—one to the customer, one to internal alert
recipients.
- `send_two_factor_code_email(...)`, `send_login_notification(...)`, and workspace helpers cover the expanded security and activity notifications.

Each helper accepts plain strings or `{ "email": ..., "name": ... }` dicts for recipients. Deduplication and whitespace trimming h
appen automatically.

## Application touch points

- **Signup:** After the Stripe checkout success handler (`auth.signup_complete`) updates the organisation, it triggers welcome/al
ert emails and initiates two-factor verification.
- **Settings & billing:** Plan confirmations and coupon redemptions use `send_notification_email` to reach billing contacts who op
ted in.
- **Imports:** Upload summaries call `send_import_notification`, respecting user notification preferences.
- **Workspace invitations:** Admin actions call `send_workspace_invitation` once the new user record is committed.
- **Workspace activity:** Shared notes, chat messages, and logins utilise the dedicated helpers for richer notifications.

## Testing & troubleshooting

1. Verify `RESEND_API_KEY` and `RESEND_FROM_EMAIL` are present.
2. Trigger a workflow (e.g., complete signup or redeem a coupon) and watch the Flask logs for `Resend send error` entries if some
thing misfires.
3. Inspect metadata tags in Resend or logs to correlate messages with organisations and actions.
4. When testing locally without credentials, expect helpers to return `False` and log that configuration is incomplete—this is in
tentional to keep dev ergonomics smooth.
