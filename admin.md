# TrackYourSheets admin playbook

The admin console centralises every organisation-level configuration task. This guide walks through day-to-day workflows, plan governance, and advanced configuration tips.

## Access & roles

- Owners, admins, and workspace agents can access `/admin`.
- Owners are created during signup. Promote additional admins or agents from the Team card.
- Agents manage a single workspace (and the producers within it). Producers, bookkeepers, and read-only auditors stay within their scoped dashboards.

## Organisation overview

The landing card summarises your plan, usage, and quick stats. Billing plan changes are performed via Stripe’s Customer Portal once Stripe integration is connected. Until then, updates can be made manually through the database.

## Workspace management

1. Use **New office** to register each physical or virtual office your agency operates.
2. Create a **New workspace** for every line of business or producer pod and optionally assign an agent user.
3. Agents see only the workspaces they manage; owners/admins can reassign agents at any time using the workspace list dropdown.

## Team management

1. Click **Invite** to open the teammate modal.
2. Provide an email and assign a role. When inviting agents or producers, pick the workspace they should manage or operate in. New users receive a temporary password (`ChangeMe123!`) and should update it on first login.
3. Remove a user via the list’s **Remove** button (you can’t delete your own account). Removing an agent releases their workspace so another agent can be assigned.

## Carrier catalogue

- Use **Add** to register each carrier your agency works with. Producers can also trigger automatic carrier creation by uploading CSVs with a `carrier` column.
- Select the download type: CSV (supported) or PDF (for future OCR workflow).
- Carriers appear in analytics and can be mapped to rulesets.

## Commission rulesets

1. Create a ruleset (e.g., “2024 Commercial Auto”).
2. Open the ruleset to add rules:
   - Choose the basis (gross commission %, premium %, or flat).
   - Specify line of business (optional), rate/flat amount, new vs. renewal, and priority.
   - Higher priority (lower number) rules evaluate first.
3. Clone rulesets by creating a new version and reusing the same configuration when you need effective dating.

## API keys & integrations

- Generate API keys for upcoming webhook and Zapier integrations. Keys are stored hashed; display pages should only show the label and scopes.
- Extend scopes in code (`admin.create_api_key`) as new APIs become available.
- Rotate keys periodically and revoke unused keys directly from the database until UI revocation is added.

## Import operations

Although managed on `/imports`, admins should periodically:

- Confirm each carrier has an accurate column mapping (auto-created carriers can be renamed from this panel).
- Monitor batch statuses (`uploaded`, `imported`, `finalized`).
- Review audit logs on the dashboard for any anomalies.
- Ensure producers are uploading to the correct workspace — imports are scoped by workspace for reporting and reconciliation.

## Email notifications

- Configure `NYLAS_API_KEY`, `NYLAS_GRANT_ID`, and `NYLAS_FROM_EMAIL` environment variables to enable Nylas-powered import summaries.
- When a producer uploads a CSV, the workspace agent receives an email summarising row counts per carrier.

## Security best practices

- Enforce strong `SECRET_KEY` and move to HTTPS behind PythonAnywhere.
- Configure regular backups using scheduled tasks plus off-site storage.
- When Stripe is enabled, ensure webhook signing secrets are stored as environment variables.
- Use the audit log table (`audit_log`) to trace changes for compliance.

## Roadmap for power admins

- Connect Stripe: map `Subscription` and `Coupon` tables to Stripe webhooks to automate plan entitlements.
- Add fuzzy matching services: leverage the stored policy/customer data to reduce manual reconciliation.
- Expand scheduled jobs: automate nightly reprocessing, raw file deletion, and trial expiry notifications.

TrackYourSheets is designed to grow with your agency—this admin panel keeps you in control of every lever.
