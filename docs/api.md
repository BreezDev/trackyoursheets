# TrackYourSheets API Guide

The TrackYourSheets API gives engineering teams programmatic access to organisations, workspaces, producers, policies, payroll runs, and HR records. The guide below summarises authentication, available endpoints, webhook events, and recommended deployment patterns so you can stand up an integration or a partner portal quickly.

## Getting started

1. **Provision API access** – Owners and admins can request API credentials from TrackYourSheets support. Once enabled, the Admin → Integrations panel displays a `client_id`, `client_secret`, and the organisation’s base URL.
2. **Choose REST or GraphQL** – Both interfaces expose the same data model. REST is versioned via `/v1/`, while GraphQL lives at `/graphql`. You can mix approaches in the same project.
3. **Allowlist the domain** – Serve the API docs from the main marketing site (e.g. `www.trackyoursheets.com/api-guide`) and optionally CNAME a subdomain such as `api.trackyoursheets.com` to your application load balancer. See the hosting instructions below for details.

## Authentication

- **OAuth 2.1 client credentials** – Request an access token from `POST /oauth/token` with your `client_id` and `client_secret`. Tokens expire every 60 minutes.
- **Scopes** – Assign scopes to limit access. Examples: `workspaces.read`, `producers.write`, `hr.read`, `payroll.read`, `reports.export`.
- **Rotating credentials** – Use the `POST /oauth/rotate` endpoint quarterly. The previous client secret stays valid for 24 hours, enabling zero downtime rotation.
- **Impersonation** – Admins can generate short-lived “act as producer” tokens via `POST /v1/impersonations` to support embedded portals.

Example token request:

```bash
curl -X POST "https://api.trackyoursheets.com/oauth/token" \
  -H "Content-Type: application/json" \
  -d '{
        "client_id": "ORG123",
        "client_secret": "xxxx",
        "grant_type": "client_credentials",
        "scope": "workspaces.read producers.read"
      }'
```

## REST endpoints (v1)

| Resource | Endpoint | Key operations |
| --- | --- | --- |
| Organisations | `GET /v1/organisations/current` | Fetch plan limits, seat counts, and feature toggles. |
| Workspaces | `GET /v1/workspaces`, `POST /v1/workspaces` | List by office, create new workspaces, and assign agents. |
| Producers | `GET /v1/producers`, `PATCH /v1/producers/{id}` | Retrieve roster, update display names, toggle portal access. |
| Commission transactions | `GET /v1/transactions`, `POST /v1/transactions/import` | Pull reconciled transactions or ingest external payouts. |
| Payroll | `GET /v1/payroll/runs`, `POST /v1/payroll/runs`, `POST /v1/payroll/runs/{id}/approve` | Manage payroll from your finance system. |
| HR | `GET /v1/hr/employees`, `POST /v1/hr/documents`, `POST /v1/hr/complaints/{id}/assign` | Sync directory data, upload policies, or route HR tickets. |
| Reports | `POST /v1/reports/export` | Generate CSV/PDF bundles for analytics, audits, or leadership decks. |

Every endpoint supports pagination (`page`, `page_size`) and filtering by `workspace_id`, `office_id`, `role`, `status`, `updated_after`, and `created_after`. Include `Prefer: return=minimal` to reduce payload size when you only need identifiers.

## GraphQL schema highlights

```graphql
type Query {
  organisation: Organisation!
  workspaces(filter: WorkspaceFilter, pagination: Pagination): WorkspaceConnection!
  payrollRuns(status: [PayrollRunStatus!]): PayrollRunConnection!
  employees(filter: EmployeeFilter, pagination: Pagination): EmployeeConnection!
}

type Mutation {
  createWorkspace(input: WorkspaceInput!): Workspace!
  upsertProducer(input: ProducerInput!): Producer!
  createPayrollRun(input: PayrollRunInput!): PayrollRun!
  acknowledgeHRDocument(input: HRDocumentAckInput!): HRDocumentAcknowledgement!
}
```

GraphQL requests follow Relay-style pagination. Use the `x-trackyoursheets-organisation` header when querying multiple tenants from a central integration.

## Webhooks

Subscribe to webhook topics at `POST /v1/webhooks` with a public HTTPS endpoint.

- `payroll.run.approved` – Fires when a payroll run changes from `draft` to `ready` or `paid`.
- `hr.complaint.created` – Fires when an employee files a new HR ticket.
- `import.batch.completed` – Fires when an import finishes mapping and reconciliation.
- `report.export.ready` – Fires when an asynchronous report bundle is available for download.

Send a `200 OK` within five seconds. TrackYourSheets retries three times with exponential backoff. Validate signatures using the `X-TrackYourSheets-Signature` header (HMAC-SHA256).

## Rate limits

- **Authenticated requests** – 1,000 requests per minute per organisation.
- **Webhook deliveries** – 50 concurrent deliveries with automatic backoff.
- **Burst handling** – Exceeding limits returns `429 Too Many Requests` with the `Retry-After` header set in seconds.

Use idempotency keys (`Idempotency-Key` header) for POST/PUT requests to safely retry operations.

## Error handling

Errors return JSON following RFC 7807:

```json
{
  "type": "https://docs.trackyoursheets.com/errors/validation",
  "title": "Validation failed",
  "status": 422,
  "detail": "workspace_id is required",
  "instance": "urn:trackyoursheets:request:abc123",
  "errors": {
    "workspace_id": ["This field is required"]
  }
}
```

## Security checklist

- Pin your integration to TLS 1.2+ and validate TrackYourSheets certificates.
- Store secrets in a hardware security module (HSM) or a managed secrets vault.
- Rotate client credentials quarterly and after any staff change.
- Log every API call with request IDs. The `X-TrackYourSheets-Request-Id` header maps to audit logs in the web app.
- Use separate OAuth clients for staging vs. production environments.

## Hosting the public API docs

1. **Create a static build** – Convert this Markdown file into HTML using your preferred generator (MkDocs, Docusaurus, Sphinx) and commit it to your marketing site.
2. **Add a marketing link** – Update `app/templates/landing.html` to highlight the API and point to `/api-guide`.
3. **Set up `api.trackyoursheets.com`** – Create a CNAME record for `api` pointing to your marketing site CDN (e.g. `api → www`). If you host docs separately, point to the docs origin instead.
4. **Issue TLS certificates** – Use your certificate manager (Let’s Encrypt, AWS ACM, Cloudflare) to cover `api.trackyoursheets.com`.
5. **Redirect legacy paths** – If you previously hosted docs elsewhere, configure HTTP 301 redirects to `/api-guide` so existing bookmarks continue working.
6. **Monitor uptime** – Add the docs endpoint to your synthetic monitoring to catch certificate expirations or CDN issues early.

## Sample integration flow

1. Your middleware retrieves an access token every 45 minutes.
2. On schedule, call `GET /v1/payroll/runs?status=ready` to find approved runs.
3. For each run, request detailed entries via `GET /v1/payroll/runs/{id}` and push them into your accounting platform.
4. After successful export, call `POST /v1/payroll/runs/{id}/acknowledge` with `{ "notes": "Synced to NetSuite" }` so HR sees the sync status.
5. Listen for `payroll.run.approved` webhooks to trigger off-cycle jobs immediately.

## Support & change management

- Version bump announcements ship via email and the in-app changelog 30 days before deprecation.
- Subscribe to the `api-status` RSS feed hosted alongside the docs for outage alerts.
- Contact `support@trackyoursheets.com` with your organisation ID and recent request IDs for expedited troubleshooting.

By following these guidelines, you can expose a reliable partner portal, automate payroll reconciliation, or embed producer analytics anywhere your business needs them.
