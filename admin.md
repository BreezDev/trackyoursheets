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

## Subscription rule updates

All plan entitlements live in the `subscription_plans` table (`app/models.py`). To adjust pricing, seat limits, or billing cadence without touching Stripe:

1. Open a Flask shell: `flask shell`.
2. Load the target plan, e.g. `plan = SubscriptionPlan.query.filter_by(name="Scale").first()`.
3. Update any attribute – `plan.price_per_user = Decimal("199.00")`, `plan.max_users = 25`, `plan.max_carriers = 25`, `plan.max_rows_per_month = 150000`, etc.
4. Persist the change with `db.session.commit()`.

Length of plan / trial settings are controlled per-organisation:

1. `org = Organization.query.get(<org_id>)`
2. Adjust `org.trial_ends_at` or set `org.trial_ends_at = datetime.utcnow() + timedelta(days=15)` to grant the standard 15-day trial.
3. For paying tenants, update or create a `Subscription` record: `sub = Subscription.query.filter_by(org_id=org.id).first()` then set `sub.plan`, `sub.status`, `sub.trial_end`, `sub.next_bill_at`, etc.
4. `db.session.commit()` once the organisation-level adjustments are ready.

Seat limits (team member amount) are enforced by the plan’s `max_users`. Price changes rely on the same `price_per_user` column; if you need tiered or flat billing, store the amount on the plan and use it during invoice generation.

When Stripe integration is active, webhook handlers should authorise these changes automatically. Until then, the admin console plus the steps above keep billing aligned with your contract.

## Workspace email notifications via Nylas

`app/nylas_email.py` exposes helpers around the Nylas v3 send endpoint. Wire them into admin workflows as follows:

1. Ensure `NYLAS_API_KEY`, `NYLAS_GRANT_ID`, and `NYLAS_FROM_EMAIL` environment variables are set.
2. For import summaries, call `send_import_notification(recipient, workspace, uploader, period, summary_rows)`.
3. For workspace invitations, call `send_workspace_invitation(recipient, inviter, workspace, role)` immediately after committing the new user record.

Both helpers log failures to the Flask app logger so you can troubleshoot without breaking the request cycle. They also no-op gracefully when credentials are missing (useful in local dev environments).

## Master admin bootstrap account

The application now provisions a fallback master admin automatically during startup. Customise it with environment variables:

- `MASTER_ADMIN_EMAIL` (default: `insurance@audimi.co.site`)
- `MASTER_ADMIN_PASSWORD` (default: `Tofu`)
- `MASTER_ADMIN_ORG_NAME` (default: `Master Admin`)

On first run the seeder will:

1. Create the organisation defined by `MASTER_ADMIN_ORG_NAME` (or reuse an existing one).
2. Attach the lowest-tier plan if the org has none so limits stay permissive.
3. Create an owner-level user with the configured email/password.

If you prefer to manage the bootstrap user manually, unset `MASTER_ADMIN_EMAIL` or `MASTER_ADMIN_PASSWORD` before launching the app.

## Import operations

Although managed on `/imports`, admins should periodically:

- Confirm each carrier has an accurate column mapping (auto-created carriers can be renamed from this panel).
- Monitor batch statuses (`uploaded`, `imported`, `finalized`).
- Review audit logs on the dashboard for any anomalies.
- Ensure producers are uploading to the correct workspace — imports are scoped by workspace for reporting and reconciliation.
- Spot-check manual sales created from the **Manual sale** screen; each entry immediately feeds reports and can be audited under the batch detail if attached or via the analytics ledger.

## Email notifications

- Configure `NYLAS_API_KEY`, `NYLAS_GRANT_ID`, and `NYLAS_FROM_EMAIL` environment variables to enable Nylas-powered import summaries.
- When a producer uploads a CSV, the workspace agent receives an email summarising row counts per carrier.

## Security best practices

- Enforce strong `SECRET_KEY` and move to HTTPS behind PythonAnywhere.
- Configure regular backups using scheduled tasks plus off-site storage.
- When Stripe is enabled, ensure webhook signing secrets are stored as environment variables.
- Use the audit log table (`audit_log`) to trace changes for compliance.
- Encourage workspace leads to maintain shared notes via the dashboard board — the content lives in `workspace_notes` and is visible to all workspace members.

## Roadmap for power admins

- Connect Stripe: map `Subscription` and `Coupon` tables to Stripe webhooks to automate plan entitlements.
- Add fuzzy matching services: leverage the stored policy/customer data to reduce manual reconciliation.
- Expand scheduled jobs: automate nightly reprocessing, raw file deletion, and trial expiry notifications.

TrackYourSheets is designed to grow with your agency—this admin panel keeps you in control of every lever.
