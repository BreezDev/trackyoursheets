# Nylas integration reference

TrackYourSheets sends transactional emails through the Nylas v3 Messages API. This guide outlines configuration, helper functions, and touch points in the app.

## Configuration

Environment variables (or Flask config overrides) set in `app/__init__.py` and consumed by `app/nylas_email.py`:

- `NYLAS_API_BASE_URL` (defaults to `https://api.nylas.com`).
- `NYLAS_API_KEY` – API token for the connected Nylas application.
- `NYLAS_GRANT_ID` – grant/connection identifier used for sending.
- `NYLAS_FROM_EMAIL` / `NYLAS_FROM_NAME` – sender identity.
- `NYLAS_REPLY_TO` – optional comma-separated reply-to addresses.
- `NYLAS_NOTIFICATION_EMAILS` – default BCC/notification recipients.
- `NYLAS_SIGNUP_ALERT_EMAILS` (falls back to `NYLAS_ALERT_RECIPIENTS`) – internal alerts for new signups.

All variables can live in `.env`; they are automatically loaded into Flask config at startup. Missing credentials cause send attempts to no-op gracefully while logging a message, making local development easier.

## Helper utilities

`app/nylas_email.py` centralises send logic:

- `_nylas_config()` pulls configuration values and normalises recipient lists.
- `_send_email(...)` builds the API payload, handles reply-to logic, attaches metadata, and POSTs to `/v3/grants/<grant_id>/messages/send` with a 10s timeout. Failures are logged with context.
- `send_notification_email(...)` fans out operational alerts (plan changes, coupons, etc.), automatically including default notification recipients when requested.
- `send_import_notification(...)` summarises import uploads.
- `send_workspace_invitation(...)` delivers workspace invites from the admin console.
- `send_signup_welcome(...)` and `send_signup_alert(...)` fire during signup completion—one to the customer, one to internal alert recipients.

Each helper accepts plain strings or `{ "email": ..., "name": ... }` dicts for recipients. Deduplication and whitespace trimming happen automatically.

## Application touch points

- **Signup:** After the Stripe checkout success handler (`auth.signup_complete`) updates the organisation, it triggers `send_signup_welcome` and `send_signup_alert`.
- **Settings & billing:** Plan confirmations and coupon redemptions use `send_notification_email` to reach billing contacts.
- **Imports:** Upload summaries call `send_import_notification`.
- **Workspace invitations:** Admin actions call `send_workspace_invitation` once the new user record is committed.

## Testing & troubleshooting

1. Verify environment variables are present (`NYLAS_API_KEY`, `NYLAS_GRANT_ID`, `NYLAS_FROM_EMAIL`).
2. Trigger a workflow (e.g., complete signup or redeem a coupon) and watch the Flask logs for `Nylas send failed` entries if something misfires.
3. Inspect the payload metadata in logs to correlate messages with organisations and actions.
4. When testing locally without credentials, expect helpers to return `False` and log that configuration is incomplete—this is intentional to keep dev ergonomics smooth.
