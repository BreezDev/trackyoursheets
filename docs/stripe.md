# Stripe integration reference

This document explains how TrackYourSheets integrates with Stripe for subscription lifecycle events.

## Configuration

Stripe is initialised from environment variables in `app/stripe_integration.py` via `init_stripe`:

- `STRIPE_MODE` (`test` or `live`).
- `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` or the mode-specific `STRIPE_TEST_*` and `STRIPE_LIVE_*` keys.
- Price IDs per plan: `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_GROWTH`, `STRIPE_PRICE_SCALE` (or their mode-specific overrides).

The Flask app stores the configured `StripeGateway` instance on `app.extensions["stripe_gateway"]`. If the gateway is misconfigured (`secret_key` missing or price IDs absent) the UI automatically hides checkout buttons and surfaces warnings.

## Gateway helper

`StripeGateway` wraps key Stripe SDK calls:

- `ensure_customer(organization)` creates/retrieves the Stripe customer ID for an organisation and persists it on the model.
- `create_checkout_session(...)` builds a subscription checkout session using mapped price IDs. Metadata is populated with organisation, plan, and flow details so follow-up routes know how to reconcile the purchase.
- `create_billing_portal_session(...)` opens the hosted billing portal for payment method and invoice management.
- `retrieve_checkout_session(session_id)` fetches an expanded checkout session (including subscription + line items) for verification after redirect.

All methods set the API key internally, so no extra configuration is required at the call site.

## Signup flow

1. `app/auth.py::signup` automatically selects the lowest-tier plan and creates Organisation/User/Subscription records in a pending state.
2. `StripeGateway.create_checkout_session` is called with flow metadata (`flow=signup`, `user_id`, `plan_id`). The user is redirected to the hosted checkout page.
3. After Stripe redirects back to `/signup/complete` with `session_id`, `signup_complete` verifies the session (`status == "complete"`), matches it to the stored user via `client_reference_id`, and updates:
   - `Organization.plan_id`
   - `Subscription.plan`, `status`, `stripe_sub_id`, and `trial_end` (if present)
   - `Organization.trial_ends_at`
4. Nylas welcome + alert emails are triggered, the owner is logged in, and onboarding continues.

## Plan changes from settings

1. In `app/main.py::settings`, owners/admins/agents submit the plan form. The server verifies Stripe configuration and redirects to a new checkout session with metadata (`flow=plan_change`, `plan_id`, `initiated_by`). Seat quantity is derived from the number of active users.
2. Stripe redirects back to `/billing/checkout/complete` with `session_id`. The handler ensures the session completed, validates the Stripe customer, resolves the plan from metadata, updates `Organization` and `Subscription`, and clears/updates any trial end.
3. Billing contacts receive a confirmation email via `send_notification_email`. A success flash message surfaces in the UI.

## Billing portal

Owners/admins/agents can launch the Stripe billing portal via `/billing/portal`, which calls `StripeGateway.create_billing_portal_session` with the organisation's customer ID.

## Testing tips

- Ensure `.env` contains the test keys and price IDs supplied by Stripe.
- Watch the Flask logs for `Stripe gateway initialised in test mode` on startup.
- Use Stripe's test cards in checkout.
- After completing checkout, confirm the subscription status under **Settings & billing** and in the database (`subscriptions` table).
- The settings form disables manual plan updates when Stripe isn't configured, preventing drift between the app and Stripe.
