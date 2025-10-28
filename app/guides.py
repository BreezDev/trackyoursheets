"""Role-based walkthrough content for the TrackYourSheets knowledge centre."""

from __future__ import annotations

from typing import Dict, List


def get_role_guides() -> List[Dict[str, object]]:
    """Return interactive guide sections used across the application.

    Each section contains a slug used for filtering, an overview that
    summarises the role, a keyword list to support quick client-side search,
    and a list of playbook steps that can be rendered inside accordions.
    """

    return [
        {
            "title": "Agents",
            "slug": "agents",
            "overview": "Configure commissions, manage assignments, and coach every producer pipeline.",
            "keywords": [
                "agents",
                "commission",
                "workspace",
                "overrides",
                "imports",
            ],
            "steps": [
                {
                    "title": "Set producer payouts",
                    "items": [
                        "Assign producers to workspaces and confirm their default split from Admin → Team.",
                        "Open the Producer Leaderboard to view every sale and apply manual overrides inline when needed.",
                        "Batch-select transactions to set flat, percentage, or split-based commissions in seconds.",
                    ],
                },
                {
                    "title": "Keep imports flowing",
                    "items": [
                        "Upload carrier statements under Imports and map unmatched rows using the side-by-side helper.",
                        "Tag categories like Auto, Home, or Renewal so producers can slice their results instantly.",
                        "Review the import health panel on the dashboard for any batches that need attention.",
                    ],
                },
            ],
        },
        {
            "title": "Producers",
            "slug": "producers",
            "overview": "Stay on top of personal production and understand every payout adjustment.",
            "keywords": [
                "producers",
                "statements",
                "commission",
                "notes",
                "renewals",
            ],
            "steps": [
                {
                    "title": "Track performance",
                    "items": [
                        "Use the dashboard workspace switcher to drill into personal or team sales funnels.",
                        "Download your latest commission statement as CSV or PDF from Reports → Commission Sheets.",
                        "Filter analytics by category or product to uncover cross-sell opportunities instantly.",
                    ],
                },
                {
                    "title": "Collaborate with the team",
                    "items": [
                        "Leave timeline notes on each sale so agents understand context on renewals and rewrites.",
                        "Review override history from the activity drawer before escalating payout questions.",
                        "Complete onboarding checklists from the interactive guide to ensure nothing is missed.",
                    ],
                },
            ],
        },
        {
            "title": "Bookkeepers",
            "slug": "bookkeepers",
            "overview": "Reconcile payouts, audit adjustments, and sync monthly closeouts without spreadsheets.",
            "keywords": [
                "bookkeepers",
                "reconciliation",
                "payout",
                "statements",
            ],
            "steps": [
                {
                    "title": "Reconcile quickly",
                    "items": [
                        "Export producer commission sheets and production summaries directly to QuickBooks-ready CSVs.",
                        "Use the production summary PDF for leadership meetings with total premium and commission trends.",
                        "Filter analytics by carrier or line to ensure payouts match carrier statements every cycle.",
                    ],
                },
                {
                    "title": "Audit activity",
                    "items": [
                        "Watch the dashboard's commission activity feed for recent overrides and imports.",
                        "Open Reports → Activity detail to print a full audit trail for any questioned payout.",
                        "Pin recurring adjustments in shared workspace notes so the team sees them immediately.",
                    ],
                },
            ],
        },
        {
            "title": "Auditors",
            "slug": "auditors",
            "overview": "Validate every change with timestamped logs and exportable reports.",
            "keywords": [
                "auditors",
                "compliance",
                "activity",
                "logs",
            ],
            "steps": [
                {
                    "title": "Monitor overrides",
                    "items": [
                        "Filter transactions by status, carrier, or category to surface items pending approval.",
                        "Review override notes directly from the commission activity drawer for full context.",
                        "Generate audit PDFs that highlight who made each change and when it happened.",
                    ],
                },
                {
                    "title": "Export artefacts",
                    "items": [
                        "Leverage the production summary CSV when sampling payouts for spot checks.",
                        "Use statement PDFs as immutable artefacts for regulators or E&O reviews.",
                        "Download import history to validate original carrier files against TrackYourSheets totals.",
                    ],
                },
            ],
        },
        {
            "title": "Admins",
            "slug": "admins",
            "overview": "Control billing, roles, and global configuration across every workspace.",
            "keywords": [
                "admins",
                "billing",
                "subscription",
                "settings",
                "nylas",
            ],
            "steps": [
                {
                    "title": "Tune the organisation",
                    "items": [
                        "Update subscription plans, seat counts, and billing cadence from the admin console.",
                        "Provision new offices and assign workspaces so agents have the right level of access.",
                        "Trigger Nylas-powered onboarding emails directly from the team management view.",
                    ],
                },
                {
                    "title": "Stay informed",
                    "items": [
                        "Use the global analytics dashboard to compare production across offices in real time.",
                        "Download organisation-wide commission sheets for executive or carrier reviews.",
                        "Review the activity feed on the main dashboard to keep tabs on imports and overrides.",
                    ],
                },
            ],
        },
        {
            "title": "Read-only",
            "slug": "read-only",
            "overview": "Navigate confidently with curated views and locked-down permissions.",
            "keywords": [
                "read-only",
                "view",
                "dashboard",
                "analytics",
            ],
            "steps": [
                {
                    "title": "Explore safely",
                    "items": [
                        "Use the left navigation tour to discover dashboards, reports, and workspace timelines.",
                        "Hover over any metric tile to reveal inline tooltips explaining the calculation.",
                        "Access the interactive How-To guide anytime for a refresher on navigation and filters.",
                    ],
                }
            ],
        },
    ]

