"""Stripe integration helpers for TrackYourSheets."""
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import os
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from flask import current_app

import stripe
from flask import Flask

from . import db
from .models import Organization, SubscriptionPlan, User


class StripeGateway:
    """Lightweight wrapper around the Stripe SDK."""

    def __init__(
        self,
        *,
        secret_key: Optional[str],
        publishable_key: Optional[str],
        mode: str,
        price_ids: Optional[Dict[str, Optional[str]]],
    ) -> None:
        self.secret_key = secret_key or ""
        self.publishable_key = publishable_key
        self.mode = mode
        self.price_ids = {k.lower(): v for k, v in (price_ids or {}).items() if v}
        if self.secret_key:
            stripe.api_key = self.secret_key
        self._price_cache: Dict[str, Dict[str, object]] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self.secret_key and self.price_ids)

    def _resolve_price(self, plan: SubscriptionPlan | str) -> Optional[str]:
        key = plan.name if isinstance(plan, SubscriptionPlan) else str(plan)
        return self.price_ids.get(key.lower())

    def plan_pricing(self, plan: SubscriptionPlan | str) -> Optional[Dict[str, object]]:
        """Return Stripe pricing metadata for a plan, cached per price ID."""

        price_id = self._resolve_price(plan)
        if not price_id or not self.secret_key:
            return None

        cached = self._price_cache.get(price_id)
        if cached:
            return cached

        try:
            stripe.api_key = self.secret_key
            price = stripe.Price.retrieve(price_id, expand=["product"])  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover - Stripe failures are logged only
            logger = getattr(current_app, "logger", None)
            if logger:
                logger.warning("Unable to retrieve Stripe price", exc_info=exc, extra={"price_id": price_id})
            return None

        unit_amount = getattr(price, "unit_amount", None)
        unit_amount_decimal = getattr(price, "unit_amount_decimal", None)
        amount_decimal = None
        if unit_amount is not None:
            amount_decimal = Decimal(unit_amount) / Decimal(100)
        elif unit_amount_decimal:
            try:
                amount_decimal = Decimal(unit_amount_decimal) / Decimal(100)
            except (TypeError, InvalidOperation):  # pragma: no cover - depends on Stripe payload
                amount_decimal = None

        currency = (getattr(price, "currency", "") or "usd").upper()
        interval = None
        recurring = getattr(price, "recurring", None)
        if recurring:
            interval = getattr(recurring, "interval", None) or recurring.get("interval")

        label = None
        if amount_decimal is not None:
            if currency == "USD":
                label = f"${amount_decimal:,.2f}"
            else:
                label = f"{amount_decimal:,.2f} {currency}"

        snapshot = {
            "price_id": price_id,
            "amount_decimal": amount_decimal,
            "currency": currency,
            "interval": interval or "month",
            "label": label,
        }

        self._price_cache[price_id] = snapshot
        return snapshot

    def ensure_customer(self, organization: Organization) -> str:
        if not organization:
            raise ValueError("Organization is required")
        if organization.stripe_customer_id:
            return organization.stripe_customer_id

        owner = next(
            (
                user
                for user in organization.users
                if user.role == "owner" and getattr(user, "email", None)
            ),
            None,
        )

        stripe.api_key = self.secret_key
        customer = stripe.Customer.create(
            email=getattr(owner, "email", None),
            name=organization.name,
            metadata={"org_id": organization.id},
        )
        organization.stripe_customer_id = customer.id
        db.session.add(organization)
        db.session.commit()
        return customer.id

    def create_checkout_session(
        self,
        *,
        organization: Organization,
        plan: SubscriptionPlan,
        quantity: int,
        success_url: str,
        cancel_url: str,
        client_reference_id: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
        subscription_metadata: Optional[Dict[str, object]] = None,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("Stripe gateway is not fully configured")
        price_id = self._resolve_price(plan)
        if not price_id:
            raise RuntimeError(f"No Stripe price configured for plan '{plan.name}'")

        stripe.api_key = self.secret_key
        customer_id = self.ensure_customer(organization)
        seat_quantity = max(int(quantity or 1), 1)
        metadata_payload: Dict[str, object] = {
            "org_id": organization.id,
            "plan": plan.name,
            "mode": self.mode,
        }
        if metadata:
            metadata_payload.update(metadata)

        subscription_metadata_payload: Dict[str, object] = {
            "org_id": organization.id,
            "plan": plan.name,
            "mode": self.mode,
        }
        if subscription_metadata:
            subscription_metadata_payload.update(subscription_metadata)

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            billing_address_collection="auto",
            allow_promotion_codes=True,
            automatic_tax={"enabled": True},
            customer_update={"address": "auto"},
            line_items=[{"price": price_id, "quantity": seat_quantity}],
            client_reference_id=client_reference_id,
            metadata=metadata_payload,
            subscription_data={
                "metadata": subscription_metadata_payload,
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session.url

    def retrieve_checkout_session(self, session_id: str):
        if not session_id:
            raise ValueError("A Stripe checkout session ID is required")
        if not self.secret_key:
            raise RuntimeError("Stripe gateway is not configured")
        stripe.api_key = self.secret_key
        return stripe.checkout.Session.retrieve(
            session_id,
            expand=["subscription", "line_items"],
        )

    def create_billing_portal_session(
        self,
        *,
        organization: Organization,
        return_url: str,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("Stripe gateway is not fully configured")
        stripe.api_key = self.secret_key
        customer_id = self.ensure_customer(organization)
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url


def _resolve_price_id(mode: str, plan_code: str) -> Optional[str]:
    candidates = []
    if mode == "live":
        candidates.append(f"STRIPE_LIVE_PRICE_{plan_code}")
    else:
        candidates.append(f"STRIPE_TEST_PRICE_{plan_code}")
    candidates.append(f"STRIPE_PRICE_{plan_code}")
    for key in candidates:
        value = os.environ.get(key)
        if value:
            return value
    return None


def init_stripe(app: Flask) -> None:
    """Initialise the Stripe gateway based on environment variables."""

    mode = (os.environ.get("STRIPE_MODE") or "test").strip().lower() or "test"
    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY")

    if mode == "live":
        secret_key = secret_key or os.environ.get("STRIPE_LIVE_SECRET_KEY")
        publishable_key = publishable_key or os.environ.get("STRIPE_LIVE_PUBLISHABLE_KEY")
    else:
        secret_key = secret_key or os.environ.get("STRIPE_TEST_SECRET_KEY")
        publishable_key = publishable_key or os.environ.get("STRIPE_TEST_PUBLISHABLE_KEY")

    price_ids = {
        "starter": _resolve_price_id(mode, "STARTER"),
        "growth": _resolve_price_id(mode, "GROWTH"),
        "scale": _resolve_price_id(mode, "SCALE"),
    }

    gateway = StripeGateway(
        secret_key=secret_key,
        publishable_key=publishable_key,
        mode=mode,
        price_ids=price_ids,
    )

    app.extensions["stripe_gateway"] = gateway
    app.config.setdefault("STRIPE_MODE", mode)
    if publishable_key:
        app.config["STRIPE_PUBLISHABLE_KEY"] = publishable_key

    if gateway.is_configured:
        app.logger.info("Stripe gateway initialised in %s mode", mode)
    elif secret_key:
        app.logger.warning(
            "Stripe secret key provided but price IDs missing; checkout disabled.",
            extra={"mode": mode},
        )
    else:
        app.logger.info("Stripe gateway not configured; skipping payments setup.")
