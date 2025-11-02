"""Role-based walkthrough content for the TrackYourSheets knowledge centre."""

from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

from typing import Dict, List


def get_role_guides() -> List[Dict[str, object]]:
    """Return interactive guide sections used across the application.

    Each section contains a slug used for filtering, an overview that
    summarises the role, a keyword list to support quick client-side search,
    and a list of playbook steps that can be rendered inside accordions.
    """

    sections = [
        {
            "title": "Agents",
            "slug": "agents",
            "overview": "Configure commissions, coach producers, and keep every pipeline healthy.",
            "keywords": [
                "agents",
                "commission",
                "workspace",
                "overrides",
                "imports",
                "leaderboard",
            ],
            "steps": [
                {
                    "title": "Set producer payouts",
                    "items": [
                        "Assign producers to workspaces and confirm default splits from Admin → Team before the month starts.",
                        "Open the Producer Leaderboard to drill into each sale, override the commission manually, and leave context notes that auditors can reference later.",
                        "Batch-select transactions to apply flat bonuses, adjust split percentages, or mark items as clawed back when reconciling statements.",
                        "Generate comparison views that show how the current period stacks against the prior month so you can justify adjustments in one click.",
                        "Regenerate individual or bulk commission statements on demand so producers always see the latest payout math.",
                        "Pin important payouts to the workspace announcement area so producers understand timing and any policy-specific caveats.",
                        "Audit the activity log before approving a payout to confirm who touched each transaction and whether approvals are complete.",
                    ],
                },
                {
                    "title": "Keep imports flowing",
                    "items": [
                        "Upload carrier statements under Imports and map unmatched rows using the assisted column matcher.",
                        "Categorise production with default tags like Auto, Home, Renters, Life plus any custom status you create for renewals or rewrites.",
                        "Monitor the dashboard import widget for warnings about missing columns, duplicate policies, or batches that require review and assign each warning to a teammate from the activity drawer.",
                        "Use saved column mapping templates when onboarding a new carrier so you can reconcile the first file in minutes.",
                        "Run the import health report weekly to identify which workspaces are falling behind or generating the most variances.",
                        "Kick off the onboarding tour from the Guide whenever you train a new teammate on the import workflow and bookmark the Imports FAQ in the knowledge base.",
                    ],
                },
                {
                    "title": "Collaborate with leaders",
                    "items": [
                        "Review workspace chat threads to keep everyone aligned on retention pushes and marketing blitzes.",
                        "Use shared workspace notes to pin coaching reminders and renewals that need attention this week.",
                        "Subscribe to Nylas-powered alerts for statement approvals so nothing slips through the cracks.",
                        "Export production summaries to PDF before leadership meetings to highlight premium growth and close rates.",
                        "Share dashboard snapshots via email or Slack using the built-in share buttons so leadership can react instantly.",
                        "Document weekly action items in the Guide’s checklist so everyone can revisit what was promised and who owns the follow-up.",
                    ],
                },
            ],
        },
        {
            "title": "Producers",
            "slug": "producers",
            "overview": "Stay on top of personal production, renewals, and payout changes.",
            "keywords": [
                "producers",
                "statements",
                "commission",
                "notes",
                "renewals",
                "leaderboard",
            ],
            "steps": [
                {
                    "title": "Track performance",
                    "items": [
                        "Use the dashboard workspace switcher to review personal vs. team funnels and premium totals.",
                        "Download the latest commission statement as CSV or branded PDF from Reports → Commission Sheets.",
                        "Filter analytics by category, product, or carrier to uncover cross-sell opportunities instantly.",
                        "Pin personal targets to the dashboard so you can measure progress every morning.",
                        "Launch the interactive tour to revisit how renewals, rewrites, and cancellations flow through TrackYourSheets.",
                        "Set up email digests for daily production summaries so you never miss a sale while on the road.",
                    ],
                },
                {
                    "title": "Collaborate with the team",
                    "items": [
                        "Leave timeline notes on each sale so agents understand renewal context and service follow-ups.",
                        "Chat with your workspace in real time for quick updates, marketing pushes, or underwriting questions.",
                        "Review the activity drawer before escalating payout questions so you can see who changed a commission and why.",
                        "Use personal notes on the dashboard to track daily goals, warm leads, and reminders only you can see.",
                        "Star important conversations so you can return to them after client meetings.",
                        "Share files (rate sheets, underwriting approvals) via the workspace document hub for one-click retrieval later.",
                    ],
                },
                {
                    "title": "Own renewals",
                    "items": [
                        "Apply renewal categories when uploading supporting documents so analytics separate new vs. existing business.",
                        "Confirm renewal payouts with agents when commissions shift from percentage to flat amounts.",
                        "Generate renewal-only production summaries to share with service teams and keep retention targets visible.",
                        "Set reminders inside workspace chat for upcoming expirations that need outbound touches.",
                        "Track renewal save rates in analytics and flag accounts that need cross-sell bundles.",
                        "Log coverage gaps discovered during renewal conversations so marketing can launch targeted campaigns.",
                    ],
                },
            ],
        },
        {
            "title": "Bookkeepers",
            "slug": "bookkeepers",
            "overview": "Reconcile payouts, tie out premiums, and prepare month-end packages.",
            "keywords": [
                "bookkeepers",
                "reconciliation",
                "payout",
                "statements",
                "close",
            ],
            "steps": [
                {
                    "title": "Month-end close",
                    "items": [
                        "Export producer commission sheets to CSV for accounting systems or PDF for leadership packet reviews.",
                        "Download the Total Premium Sold summary to compare against carrier downloads and bank deposits.",
                        "Use analytics filters to confirm category totals (raw vs. renewal) align with GL entries.",
                        "Attach PDFs and CSVs directly into your accounting workflow to leave an audit trail for auditors and partners.",
                        "Capture notes in the monthly close checklist so auditors understand any manual reconciliation steps.",
                        "Schedule recurring exports so finance receives reports automatically without logging in.",
                    ],
                },
                {
                    "title": "Investigate variances",
                    "items": [
                        "Open activity detail pages for any override to see who approved it, the original amount, and the audit note.",
                        "Reference shared workspace notes for context around manual adjustments before escalating to leadership.",
                        "Tag chat messages with carriers or policy numbers so agents can respond with documentation quickly.",
                        "Archive balanced imports to keep the dashboard queue focused on batches that still need review.",
                        "Use variance reason codes to build a trend report and surface systemic issues to carriers.",
                        "Export exception lists to share with compliance or your external CPA before closing the books.",
                    ],
                },
                {
                    "title": "Collaborate with finance",
                    "items": [
                        "Share the subscription utilisation report with finance so they understand seat counts and plan costs.",
                        "Schedule PDF exports for leadership so executive teams have consistent visuals for recurring meetings.",
                        "Use the guide search to find billing configuration steps when adjusting plan tiers mid-cycle.",
                        "Leverage the audit-ready download pack when responding to external accountant requests.",
                        "Publish a shared close checklist with due dates and status updates for every stakeholder.",
                        "Store signed-off financial packets in the HR Documents section for cross-team visibility.",
                    ],
                },
            ],
        },
        {
            "title": "Auditors",
            "slug": "auditors",
            "overview": "Validate each commission change with timestamped logs and exports.",
            "keywords": [
                "auditors",
                "compliance",
                "activity",
                "logs",
                "controls",
            ],
            "steps": [
                {
                    "title": "Monitor overrides",
                    "items": [
                        "Filter commission activity by status, carrier, or workspace to find high-risk adjustments.",
                        "Open the detail drawer to see before-and-after values, override notes, and the responsible editor.",
                        "Subscribe to audit alerts so you are notified when large manual payouts are saved.",
                        "Export override logs to PDF for regulators or E&O reviews with a single click.",
                    ],
                },
                {
                    "title": "Preserve artefacts",
                    "items": [
                        "Generate immutable PDFs for statements, production summaries, and audit checklists.",
                        "Download import history alongside original carrier files to maintain a full audit trail.",
                        "Store shared workspace notes as supplementary evidence when exceptions are approved.",
                        "Use analytics exports to keep third-party auditors aligned on totals across offices.",
                    ],
                },
            ],
        },
        {
            "title": "Admins",
            "slug": "admins",
            "overview": "Control billing, teams, and configuration across every workspace.",
            "keywords": [
                "admins",
                "billing",
                "subscription",
                "settings",
                "resend",
                "offices",
            ],
            "steps": [
                {
                    "title": "Tune the organisation",
                    "items": [
                        "Create new offices, assign agents, and manage workspace rosters from Admin → Offices & Team.",
                        "Adjust subscription plans, seat counts, and billing cadence using the subscription console walkthrough documented in admin.md.",
                        "Configure default product categories so new imports inherit the right tagging with no manual cleanup.",
                        "Invite teammates with the correct role permissions and trigger Resend onboarding emails instantly.",
                        "Track HR-specialist seats separately so people operations can work without full admin rights.",
                        "Review workspace agent coverage and reassign inactive accounts in one bulk update.",
                    ],
                },
                {
                    "title": "Stay informed",
                    "items": [
                        "Review the master analytics dashboard for production comparisons across offices and workspaces.",
                        "Generate organisation-wide commission sheets (CSV & PDF) before revenue or carrier reviews.",
                        "Drill into activity logs to understand who edited notes, overrides, or chat history and when they acted.",
                        "Launch the interactive tour whenever you introduce new features so admins and agents stay aligned.",
                        "Subscribe to weekly digest emails summarising imports, overrides, and payroll approvals.",
                        "Embed the analytics iframe inside your BI tool for a blended revenue and retention view.",
                    ],
                },
                {
                    "title": "Manage compliance",
                    "items": [
                        "Lock down read-only users with navigation tips so executives can explore without editing data.",
                        "Audit workspace chat for sensitive information and archive conversations when policies renew.",
                        "Export billing utilisation data to CSV for finance reviews and budgeting.",
                        "Confirm upcoming renewals and completed Stripe checkouts from the subscription settings screen.",
                        "Review HR access logs monthly to ensure only authorised teammates use the dedicated HR role.",
                        "Document policy changes in the knowledge base and share links directly from the HR Documents tab.",
                    ],
                },
            ],
        },
        {
            "title": "Owners & Executives",
            "slug": "executives",
            "overview": "Gain a command-center view of growth, retention, and billing health.",
            "keywords": [
                "executive",
                "owner",
                "analytics",
                "billing",
                "overview",
            ],
            "steps": [
                {
                    "title": "Monitor growth",
                    "items": [
                        "Use the dashboard tiles to track commission activity and click through to recent overrides and imports.",
                        "Review premium trends by carrier and workspace from Reports → Analytics to spot momentum.",
                        "Save PDF snapshots for board decks or partner updates using the export buttons.",
                        "Bookmark the interactive guide so leadership can self-serve answers during audits or diligence.",
                        "Compare offices side-by-side using the analytics segmentation controls to pinpoint coaching opportunities.",
                        "Enable executive email digests so you receive highlights every Monday before leadership meetings.",
                    ],
                },
                {
                    "title": "Oversee billing",
                    "items": [
                        "Check subscription utilisation to ensure seat counts and workspaces match staffing plans.",
                        "Confirm recurring payment status, renewal dates, and invoice history from the admin billing console.",
                        "Trigger CSV exports for finance teams covering total premium, commission, and outstanding adjustments.",
                        "Share workspace chat expectations so teams document escalations and approvals transparently.",
                    ],
                },
            ],
        },
        {
            "title": "HR specialists",
            "slug": "hr",
            "overview": "Steward onboarding, employee records, and sensitive requests without needing full admin powers.",
            "keywords": [
                "hr",
                "people",
                "onboarding",
                "policies",
                "complaints",
            ],
            "steps": [
                {
                    "title": "Run the daily HR desk",
                    "items": [
                        "Start on HR → Overview to review headcount, onboarding progress, anniversaries, and urgent complaints.",
                        "Filter the directory by role or status to check in on new hires and confirm they activated two-factor.",
                        "Log conversations or follow-ups in the HR complaint drawer so the full context rides with the case.",
                        "Upload new policy PDFs and request acknowledgements with one click — TrackYourSheets timestamps every response.",
                        "Use the search bar to jump straight to an employee profile and update job titles or emergency contacts.",
                        "Share the HR digest email with leadership so everyone sees the same onboarding and retention metrics.",
                    ],
                },
                {
                    "title": "Maintain compliance",
                    "items": [
                        "Tag documents by category (policy, payroll, compliance, culture) and track acknowledgement counts from the dashboard.",
                        "Assign complaint owners and update status notes so nothing stalls during investigations.",
                        "Export the onboarding checklist to CSV before audits to prove who completed each step and when.",
                        "Coordinate with admins to adjust notification or two-factor requirements directly from the HR quick actions card.",
                        "Mark sensitive complaints as urgent to trigger instant alerts for admins and owners.",
                        "Archive resolved issues with a closing summary to preserve context for future reviews.",
                    ],
                },
                {
                    "title": "Partner with leadership",
                    "items": [
                        "Review role distribution charts alongside workforce plans to anticipate hiring needs.",
                        "Export payroll acknowledgements so finance can reconcile payouts against signed-off records.",
                        "Share the anniversaries and recognition calendar with marketing for internal communications.",
                        "Surface HR trends (turnover, complaint categories, onboarding velocity) in executive meetings using the built-in charts.",
                        "Link to `docs/hr.md` from the knowledge base so new HR teammates can follow the full playbook.",
                        "Record cross-functional action items in the Guide checklist to keep people, finance, and operations aligned.",
                    ],
                },
            ],
        },
        {
            "title": "Payroll & finance",
            "slug": "payroll",
            "overview": "Transform reconciled commissions into payouts while keeping HR and accounting in sync.",
            "keywords": [
                "payroll",
                "finance",
                "payouts",
                "stripe",
                "reconciliation",
            ],
            "steps": [
                {
                    "title": "Prepare payout runs",
                    "items": [
                        "Open Admin → Payroll to review draft runs, run statuses, and pending approvals.",
                        "Clone the latest run to reuse configuration, then set the statement window and internal naming conventions.",
                        "Review each producer entry for bonuses, clawbacks, and tax adjustments before approval.",
                        "Use filters to isolate a specific workspace, agent, or role so nothing gets missed.",
                        "Attach reviewer notes explaining manual adjustments — they surface instantly in the HR profile view.",
                        "Send Stripe payouts or export the register for ACH if Stripe isn’t connected yet.",
                    ],
                },
                {
                    "title": "Reconcile & communicate",
                    "items": [
                        "Download the payout register CSV for accounting and store it with your month-end workpapers.",
                        "Compare the variance report to the prior period to highlight large swings before final approval.",
                        "Toggle the Include inactive users filter when processing off-cycle adjustments or terminations.",
                        "Mark runs as acknowledged once HR confirms every employee question is resolved.",
                        "Sync run notes with the HR portal so people operations can see payment references without admin access.",
                        "Reference `docs/payroll.md` for the full checklist and troubleshooting guidance.",
                    ],
                },
                {
                    "title": "Collaborate across teams",
                    "items": [
                        "Use workspace chat to notify agents when payouts are approved or when documentation is missing.",
                        "Share payroll metrics with executives alongside revenue dashboards for a complete financial picture.",
                        "Schedule recurring exports to push payroll data into accounting or BI tools automatically.",
                        "Document exception handling procedures inside the knowledge base so replacements can follow the same steps.",
                        "Review the HR complaint queue for payroll-related issues and resolve them before closing the run.",
                        "Archive completed runs with a link to payment confirmations to maintain an audit trail.",
                    ],
                },
            ],
        },
        {
            "title": "Imports & Operations",
            "slug": "operations",
            "overview": "Standardise data hygiene and keep carrier feeds synchronised.",
            "keywords": [
                "operations",
                "imports",
                "data",
                "mapping",
                "categories",
            ],
            "steps": [
                {
                    "title": "Prepare files",
                    "items": [
                        "Download carrier CSVs or PDFs and drag them into Imports — we support batch uploads up to 25MB.",
                        "Map headers once; TrackYourSheets remembers matches and flags anomalies automatically.",
                        "Use category presets (Auto, Home, Renters, Life, Raw, Existing, Renewal) as a starting point, then add custom options per organisation.",
                        "Validate split rules before posting the batch so commissions land in the right producer accounts.",
                    ],
                },
                {
                    "title": "Resolve exceptions",
                    "items": [
                        "Leverage the discrepancy panel to correct missing producers or duplicate policy numbers.",
                        "Tag agents in workspace chat when you need clarification on a transaction before approving it.",
                        "Re-run the onboarding tour if you need a refresher on import troubleshooting steps.",
                        "Archive completed batches to keep the imports list focused on files that still require action.",
                    ],
                },
            ],
        },
        {
            "title": "Read-only observers",
            "slug": "read-only",
            "overview": "Navigate confidently with curated dashboards and locked-down permissions.",
            "keywords": [
                "read-only",
                "view",
                "dashboard",
                "analytics",
                "executive",
            ],
            "steps": [
                {
                    "title": "Explore safely",
                    "items": [
                        "Use the navigation tour to discover dashboards, reports, and workspace timelines without editing data.",
                        "Hover over any metric tile to reveal inline tooltips explaining each calculation.",
                        "Download PDF summaries for meetings without altering underlying transactions.",
                        "Search the guide for quick answers on subscription status, analytics definitions, or export formats.",
                    ],
                },
            ],
        },
        {
            "title": "Developers & Integrations",
            "slug": "integrations",
            "overview": "Extend TrackYourSheets with secure API and webhook workflows.",
            "keywords": [
                "api",
                "integrations",
                "webhooks",
                "automation",
            ],
            "steps": [
                {
                    "title": "Automate safely",
                    "items": [
                        "Generate API keys from Admin → Integrations and scope them to specific workspaces.",
                        "Use the production summary endpoint to sync totals into BI tools or data warehouses.",
                        "Listen for webhook notifications when imports finish so you can trigger downstream automations.",
                        "Review the audit log after each deployment to verify automated adjustments were applied correctly.",
                        "Follow the authentication flow and rate limits documented in `docs/api.md` to stay within quotas.",
                        "Stand up sandbox tests against `/v1/` and `/graphql` before promoting to production.",
                    ],
                },
                {
                    "title": "Collaborate with admins",
                    "items": [
                        "Document integration notes inside shared workspace notes for transparency with agents and finance.",
                        "Schedule regular guide tours with stakeholders whenever new automation rolls out.",
                        "Provide CSV/PDF export samples to partners so data contracts stay aligned.",
                        "Coordinate via workspace chat before running bulk updates in production environments.",
                        "Publish public docs at `/api-guide` or `api.trackyoursheets.com` so partners can self-serve support.",
                        "Record webhook endpoints, secrets, and contact escalation paths inside your runbook.",
                    ],
                },
            ],
        },
    ]
# ✅ FIX: sanitize every step and repair any corrupted "items" keys
    for section in sections:
        clean_steps = []
        for step in section.get("steps", []):
            # Make sure each step is a dict
            if isinstance(step, (list, tuple)):
                step = dict(step)

            # If step.items accidentally became a method, fix it
            items_value = step.get("items")
            if callable(items_value):
                # convert it safely to a list of keys or reset it to empty
                try:
                    items_value = list(items_value())
                    # this would make it [('title', '...'), ('items', [...])] → we don’t want that
                    # so just skip and replace with empty list if that happens
                    if len(items_value) and isinstance(items_value[0], tuple):
                        items_value = []
                except Exception:
                    items_value = []
            elif not isinstance(items_value, list):
                items_value = []

            step["items"] = items_value
            clean_steps.append(step)

        section["steps"] = clean_steps

    return sections


def get_interactive_tour() -> List[Dict[str, object]]:
    return [
        {
            "title": "Welcome to TrackYourSheets",
            "description": "Start on the dashboard to monitor recent commission activity, imports, audit alerts, and workspace announcements in one place.",
            "cta_label": "Open dashboard",
            "cta_endpoint": "main.dashboard",
        },
        {
            "title": "Review producer performance",
            "description": "Visit Reports → Commission Sheets to download CSV or branded PDF payouts, compare periods, and email results to producers in seconds.",
            "cta_label": "Go to commission sheets",
            "cta_endpoint": "reports.commission_sheet",
        },
        {
            "title": "Analyse premium & retention",
            "description": "Use Reports → Analytics to slice premium, commission, and renewal rates by workspace, product, or custom tags — perfect for leadership decks.",
            "cta_label": "Open analytics",
            "cta_endpoint": "reports.analytics_dashboard",
        },
        {
            "title": "Manage team, seats, and billing",
            "description": "Head to the Admin console to invite agents, assign HR specialists, adjust seat counts, and trigger Stripe plan changes with audit logging.",
            "cta_label": "Visit admin",
            "cta_endpoint": "admin.index",
        },
        {
            "title": "Import carrier statements",
            "description": "Upload new batches under Imports, reuse saved column mappings, and resolve variances using the guided checklist.",
            "cta_label": "Launch imports",
            "cta_endpoint": "imports.index",
        },
        {
            "title": "Run HR operations",
            "description": "Open the HR portal to manage onboarding, policy acknowledgements, complaint queues, and role distribution in real time.",
            "cta_label": "View HR dashboard",
            "cta_endpoint": "hr.dashboard",
        },
        {
            "title": "Process payroll",
            "description": "Jump to Admin → Payroll to assemble runs, review payouts, attach notes, and sync acknowledgements back to HR.",
            "cta_label": "Open payroll",
            "cta_endpoint": "admin.payroll_dashboard",
        },
        {
            "title": "Collaborate in workspaces",
            "description": "Use workspace notes, chat, and document sharing directly from the dashboard to coordinate renewals, approvals, and escalations.",
            "cta_label": "View workspace tools",
            "cta_endpoint": "main.dashboard",
        },
        {
            "title": "Explore the API",
            "description": "Review the API guide for authentication, REST/GraphQL endpoints, and webhook topics so you can automate TrackYourSheets safely.",
            "cta_label": "Read API guide",
            "cta_endpoint": "main.api_guide",
        },
        {
            "title": "Finish with the knowledge base",
            "description": "Search the role-based guide anytime for policy references, setup steps, onboarding checklists, and recorded tours.",
            "cta_label": "Browse guide",
            "cta_endpoint": "main.guide",
        },
    ]

