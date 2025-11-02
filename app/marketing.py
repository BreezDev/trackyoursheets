from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from flask import current_app

from .models import SubscriptionPlan


def _format_currency(amount: Decimal | float | int | None) -> str:
    if amount is None:
        return "$0"
    value = float(amount)
    if value.is_integer():
        return f"${int(value):,}"
    return f"${value:,.2f}"


def _format_cap(label: str, value: int) -> str:
    if value is None:
        return label
    if value >= 999:
        return f"{label}: Unlimited"
    return f"{label}: up to {value:,}"


def _plan_tagline(plan: SubscriptionPlan) -> str:
    name = (plan.name or "").lower()
    if "starter" in name:
        return "Essential visibility for lean, fast-moving teams"
    if "growth" in name:
        return "Analytics and automations for scaling agencies"
    if "scale" in name:
        return "Enterprise controls for complex revenue operations"
    if "pro" in name:
        return "Professional insights for expanding teams"
    return "Flexible commission intelligence tailored to your agency"


def _plan_access_level(plan: SubscriptionPlan) -> str:
    mapping = {
        1: "Core access",
        2: "Advanced access",
        3: "Enterprise access",
    }
    return mapping.get(plan.tier, "Flexible access")


def _plan_feature_points(plan: SubscriptionPlan) -> list[str]:
    features: list[str] = []
    included = plan.included_users or plan.max_users
    if included:
        seat_phrase = f"Includes {included:,} user{'s' if included != 1 else ''}"
        if plan.extra_user_price:
            seat_phrase += f" · ${float(plan.extra_user_price):.2f}/mo per extra seat"
        features.append(seat_phrase)
    else:
        features.append("Flexible team seats")
    features.append(_format_cap("Team seats", plan.max_users))
    features.append("Unlimited carrier connections & data sync")
    features.append(_format_cap("Rows reconciled / month", plan.max_rows_per_month))
    features.append("Real-time dashboard & anomaly detection")
    if plan.includes_quickbooks:
        features.append("QuickBooks Online revenue sync")
    else:
        features.append("CSV export & reconciliation tools")
    if plan.includes_producer_portal:
        features.append("Producer performance portals")
    else:
        features.append("Internal workspace for managers")
    if plan.includes_api:
        features.append("GraphQL + REST API access")
    else:
        features.append("Automated email & Slack digests")
    features.append("Bank-level security & audit logging")
    return features


def build_plan_details(
    plans: Iterable[SubscriptionPlan],
    *,
    stripe_gateway=None,
) -> list[dict]:
    if stripe_gateway is None:
        try:
            stripe_gateway = current_app.extensions.get("stripe_gateway")
        except RuntimeError:  # pragma: no cover - accessing outside app context
            stripe_gateway = None

    plan_details: list[dict] = []
    for index, plan in enumerate(plans):
        price_label = _format_currency(plan.price_per_user)
        billing_interval = "month"
        price_amount: Optional[float] = float(plan.price_per_user or 0)
        price_source = "database"
        if stripe_gateway and getattr(stripe_gateway, "is_configured", False):
            pricing_snapshot = stripe_gateway.plan_pricing(plan)
            if pricing_snapshot and pricing_snapshot.get("label"):
                price_label = pricing_snapshot["label"]
                billing_interval = pricing_snapshot.get("interval") or billing_interval
                amount_decimal = pricing_snapshot.get("amount_decimal")
                if amount_decimal is not None:
                    price_amount = float(amount_decimal)
                price_source = "stripe"
        plan_details.append(
            {
                "id": plan.id,
                "name": plan.name,
                "price_label": price_label,
                "price_per_user": price_amount,
                "included_users": plan.included_users,
                "extra_user_price": float(plan.extra_user_price) if plan.extra_user_price else None,
                "price_source": price_source,
                "billing_interval": billing_interval,
                "tagline": _plan_tagline(plan),
                "access_level": _plan_access_level(plan),
                "feature_points": _plan_feature_points(plan),
                "is_recommended": index == 1,
                "limits": {
                    "max_users": plan.max_users,
                    "max_rows_per_month": plan.max_rows_per_month,
                    "includes_quickbooks": plan.includes_quickbooks,
                    "includes_producer_portal": plan.includes_producer_portal,
                    "includes_api": plan.includes_api,
                },
            }
        )
    return plan_details


def marketing_highlights() -> list[dict[str, str]]:
    return [
        {
            "icon": "bi-bar-chart-line",
            "title": "Revenue intelligence",
            "description": "Unify commission statements, spot variances instantly, and give every leader the numbers they trust.",
        },
        {
            "icon": "bi-diagram-3",
            "title": "Workflow automation",
            "description": "Route imports, notify producers, and publish payouts automatically with audit-ready tracking.",
        },
        {
            "icon": "bi-people",
            "title": "Team visibility",
            "description": "Role-based access, manager workspaces, and producer scorecards keep everyone aligned on goals.",
        },
        {
            "icon": "bi-cloud-check",
            "title": "Open API",
            "description": "Secure REST, GraphQL, and webhook endpoints let you sync payroll, HR, and analytics into your own stack.",
        },
    ]


def marketing_metrics() -> list[dict[str, str]]:
    return [
        {"value": "12M+", "label": "Rows reconciled per year"},
        {"value": "3 min", "label": "Average variance resolution"},
        {"value": "97%", "label": "Customer retention"},
    ]


def marketing_timeline() -> list[dict[str, str]]:
    return [
        {
            "title": "Connect carriers",
            "description": "Upload CSV statements or sync integrations to build a central data warehouse in hours, not months.",
        },
        {
            "title": "Reconcile automatically",
            "description": "AI-powered normalization detects missing rows, mismatched splits, and policy exceptions before payroll.",
        },
        {
            "title": "Empower producers",
            "description": "Share tailored portals, automate payout approvals, and keep teams informed with alerts and dashboards.",
        },
    ]


def marketing_operations_pillars() -> list[dict[str, str]]:
    return [
        {
            "icon": "bi-speedometer2",
            "title": "Realtime health",
            "stat": "Live dashboards & anomaly alerts",
            "description": "Spot exceptions instantly with streaming variance alerts, KPIs that refresh every minute, and rich audit timelines.",
        },
        {
            "icon": "bi-cpu",
            "title": "Augmented automations",
            "stat": "70+ intelligent workflows",
            "description": "Automate imports, payouts, escalations, and compliance reviews with configurable playbooks built for insurance revenue ops.",
        },
        {
            "icon": "bi-shield-lock",
            "title": "Enterprise trust",
            "stat": "SOC 2 aligned controls",
            "description": "Encryption in transit and at rest, fine-grained roles, and retention policies that meet even the strictest carrier requirements.",
        },
    ]


def marketing_personas() -> list[dict[str, object]]:
    return [
        {
            "title": "Agency principals",
            "icon": "bi-briefcase",
            "summary": "Forecast growth with revenue insights, drill into producer productivity, and model commission scenarios without spreadsheets.",
            "focus_points": [
                "Executive dashboards that show ARR, MRR, and renewal pipeline in one place",
                "Variance reports that flag policies at risk before renewals lapse",
                "Investor-ready exports with narrative highlights and performance trends",
            ],
        },
        {
            "title": "Operations leaders",
            "icon": "bi-kanban",
            "summary": "Standardise reconciliation, eliminate manual uploads, and keep every workspace aligned on SLAs and compliance steps.",
            "focus_points": [
                "Workflow builder with branching approvals and retry logic",
                "Bulk import wizard with column matching, validation, and rollbacks",
                "Exception inbox that prioritises high-value discrepancies for quick resolution",
            ],
        },
        {
            "title": "Producers & managers",
            "icon": "bi-graph-up",
            "summary": "Give producers self-service access to payouts, scorecards, and client movements so they can plan every conversation.",
            "focus_points": [
                "Live compensation statements with drill-downs to policy, carrier, and split",
                "Goal tracking that compares actuals vs targets with coaching insights",
                "Mobile-ready portal with notifications for approvals, clawbacks, and bonuses",
            ],
        },
    ]


def marketing_integrations() -> list[dict[str, str]]:
    return [
        {"name": "Vertafore", "category": "Carrier & agency systems"},
        {"name": "Applied Epic", "category": "Carrier & agency systems"},
        {"name": "EZLynx", "category": "Carrier & agency systems"},
        {"name": "QuickBooks Online", "category": "Accounting"},
        {"name": "Sage Intacct", "category": "Accounting"},
        {"name": "Slack", "category": "Collaboration"},
        {"name": "Microsoft Teams", "category": "Collaboration"},
        {"name": "Snowflake", "category": "Data warehouse"},
        {"name": "Power BI", "category": "Analytics"},
        {"name": "Tableau", "category": "Analytics"},
    ]


def marketing_testimonials() -> list[dict[str, str]]:
    return [
        {
            "quote": "TrackYourSheets turned weekly fire drills into a predictable rhythm. Our finance team closes the books two days faster every month.",
            "name": "Avery Mitchell",
            "role": "COO, Beacon Insurance Partners",
        },
        {
            "quote": "Producers finally trust the payout numbers. The portal puts everything in context and we caught three high-value variances in the first week.",
            "name": "Jordan Rivers",
            "role": "VP of Sales, Summit Brokerage",
        },
        {
            "quote": "Implementation was shockingly smooth. The automation playbooks mirrored our compliance checklist out of the box.",
            "name": "Priya Desai",
            "role": "Director of Operations, Northwind Mutual",
        },
    ]


def marketing_top_questions() -> list[dict[str, str]]:
    return [
        {
            "question": "How quickly can we get started?",
            "answer": "Most agencies import their first carrier statements within 48 hours. Guided onboarding and a migration specialist help you map data, configure roles, and launch workspaces step-by-step.",
        },
        {
            "question": "What security certifications do you maintain?",
            "answer": "TrackYourSheets follows SOC 2 Type II controls, enforces SSO with SAML or OAuth, and provides full audit trails for every data change. Data is encrypted at rest with AES-256 and in transit with TLS 1.3.",
        },
        {
            "question": "Can we connect our existing BI stack?",
            "answer": "Yes. Use the REST or GraphQL API, schedule warehouse syncs to Snowflake or BigQuery, and stream webhook events for payroll approvals, HR escalations, and commission updates.",
        },
        {
            "question": "Do you support multi-entity agencies?",
            "answer": "Workspaces, role-based permissions, and consolidated reporting make it easy to manage multiple offices or brands while preserving autonomy and data privacy.",
        },
    ]
