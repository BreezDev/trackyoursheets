"""Role-based walkthrough content for the TrackYourSheets knowledge centre."""

from __future__ import annotations

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
                        "Regenerate individual or bulk commission statements on demand so producers always see the latest payout math.",
                    ],
                },
                {
                    "title": "Keep imports flowing",
                    "items": [
                        "Upload carrier statements under Imports and map unmatched rows using the assisted column matcher.",
                        "Categorise production with default tags like Auto, Home, Renters, Life plus any custom status you create for renewals or rewrites.",
                        "Monitor the dashboard import widget for warnings about missing columns, duplicate policies, or batches that require review.",
                        "Kick off the onboarding tour from the Guide whenever you train a new teammate on the import workflow.",
                    ],
                },
                {
                    "title": "Collaborate with leaders",
                    "items": [
                        "Review workspace chat threads to keep everyone aligned on retention pushes and marketing blitzes.",
                        "Use shared workspace notes to pin coaching reminders and renewals that need attention this week.",
                        "Subscribe to Nylas-powered alerts for statement approvals so nothing slips through the cracks.",
                        "Export production summaries to PDF before leadership meetings to highlight premium growth and close rates.",
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
                        "Launch the interactive tour to revisit how renewals, rewrites, and cancellations flow through TrackYourSheets.",
                    ],
                },
                {
                    "title": "Collaborate with the team",
                    "items": [
                        "Leave timeline notes on each sale so agents understand renewal context and service follow-ups.",
                        "Chat with your workspace in real time for quick updates, marketing pushes, or underwriting questions.",
                        "Review the activity drawer before escalating payout questions so you can see who changed a commission and why.",
                        "Use personal notes on the dashboard to track daily goals, warm leads, and reminders only you can see.",
                    ],
                },
                {
                    "title": "Own renewals",
                    "items": [
                        "Apply renewal categories when uploading supporting documents so analytics separate new vs. existing business.",
                        "Confirm renewal payouts with agents when commissions shift from percentage to flat amounts.",
                        "Generate renewal-only production summaries to share with service teams and keep retention targets visible.",
                        "Set reminders inside workspace chat for upcoming expirations that need outbound touches.",
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
                    ],
                },
                {
                    "title": "Investigate variances",
                    "items": [
                        "Open activity detail pages for any override to see who approved it, the original amount, and the audit note.",
                        "Reference shared workspace notes for context around manual adjustments before escalating to leadership.",
                        "Tag chat messages with carriers or policy numbers so agents can respond with documentation quickly.",
                        "Archive balanced imports to keep the dashboard queue focused on batches that still need review.",
                    ],
                },
                {
                    "title": "Collaborate with finance",
                    "items": [
                        "Share the subscription utilisation report with finance so they understand seat counts and plan costs.",
                        "Schedule PDF exports for leadership so executive teams have consistent visuals for recurring meetings.",
                        "Use the guide search to find billing configuration steps when adjusting plan tiers mid-cycle.",
                        "Leverage the audit-ready download pack when responding to external accountant requests.",
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
                "nylas",
                "offices",
            ],
            "steps": [
                {
                    "title": "Tune the organisation",
                    "items": [
                        "Create new offices, assign agents, and manage workspace rosters from Admin → Offices & Team.",
                        "Adjust subscription plans, seat counts, and billing cadence using the subscription console walkthrough documented in admin.md.",
                        "Configure default product categories so new imports inherit the right tagging with no manual cleanup.",
                        "Invite teammates with the correct role permissions and trigger Nylas onboarding emails instantly.",
                    ],
                },
                {
                    "title": "Stay informed",
                    "items": [
                        "Review the master analytics dashboard for production comparisons across offices and workspaces.",
                        "Generate organisation-wide commission sheets (CSV & PDF) before revenue or carrier reviews.",
                        "Drill into activity logs to understand who edited notes, overrides, or chat history and when they acted.",
                        "Launch the interactive tour whenever you introduce new features so admins and agents stay aligned.",
                    ],
                },
                {
                    "title": "Manage compliance",
                    "items": [
                        "Lock down read-only users with navigation tips so executives can explore without editing data.",
                        "Audit workspace chat for sensitive information and archive conversations when policies renew.",
                        "Export billing utilisation data to CSV for finance reviews and budgeting.",
                        "Confirm free-trial expirations and recurring payments from the subscription settings screen.",
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
                    ],
                },
                {
                    "title": "Collaborate with admins",
                    "items": [
                        "Document integration notes inside shared workspace notes for transparency with agents and finance.",
                        "Schedule regular guide tours with stakeholders whenever new automation rolls out.",
                        "Provide CSV/PDF export samples to partners so data contracts stay aligned.",
                        "Coordinate via workspace chat before running bulk updates in production environments.",
                    ],
                },
            ],
        },
    ]

    for section in sections:
        fixed_steps = []
        for step in section.get("steps", []):
            if isinstance(step, (list, tuple)):
                step = dict(step)
            fixed_steps.append(step)
        section["steps"] = fixed_steps

    return sections


def get_interactive_tour() -> List[Dict[str, object]]:
    return [
        {
            "title": "Welcome to TrackYourSheets",
            "description": "Start on the dashboard to monitor recent commission activity, imports, and audit alerts at a glance.",
            "cta_label": "Open dashboard",
            "cta_endpoint": "main.dashboard",
        },
        {
            "title": "Review producer performance",
            "description": "Visit Reports → Commission Sheets to download CSV or branded PDF payouts for any producer or the entire organisation.",
            "cta_label": "Go to commission sheets",
            "cta_endpoint": "reports.commission_sheet",
        },
        {
            "title": "Analyse total premium sold",
            "description": "Use Reports → Analytics to filter premium and commission by workspace, product, or custom category tags.",
            "cta_label": "Open analytics",
            "cta_endpoint": "reports.analytics_dashboard",
        },
        {
            "title": "Manage team and billing",
            "description": "Head to the Admin console to adjust seats, update subscription plans, and invite teammates with the right roles.",
            "cta_label": "Visit admin",
            "cta_endpoint": "admin.index",
        },
        {
            "title": "Import carrier statements",
            "description": "Upload new batches under Imports and follow the assisted mapping flow to reconcile production quickly.",
            "cta_label": "Launch imports",
            "cta_endpoint": "imports.index",
        },
        {
            "title": "Collaborate in workspaces",
            "description": "Use workspace notes and chat directly from the dashboard to coordinate renewals, approvals, and escalations.",
            "cta_label": "View workspace tools",
            "cta_endpoint": "main.dashboard",
        },
        {
            "title": "Finish with the knowledge base",
            "description": "Search the role-based guide anytime for policy references, setup steps, and onboarding checklists.",
            "cta_label": "Browse guide",
            "cta_endpoint": "main.guide",
        },
    ]

