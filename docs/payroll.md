# TrackYourSheets Payroll Operations

The payroll workspace helps finance and HR teams convert reconciled commission data into accurate payouts. It lives under the Admin navigation for owners and admins and is linked from the HR portal so HR specialists can review pay runs without leaving their workflow.

## Key concepts

- **Payroll runs** – A dated batch of commission entries ready to approve or send to Stripe. Runs capture metadata such as the processing window, who prepared the batch, and whether Stripe payouts were triggered automatically.
- **Payroll entries** – Line items for individual producers or staff members. Entries track gross commission, adjustments, bonuses, clawbacks, and employer taxes.
- **Source data** – Commission transactions generated from imports. Each entry links back to its originating batch and policy so auditors can trace every number.
- **Approvals** – Runs store status labels (`draft`, `ready`, `paid`, `archived`) plus notes for the reviewer so you know exactly when payroll was green-lit and by whom.

## End-to-end workflow

1. **Reconcile commissions** – Agents or bookkeepers reconcile carrier statements in Imports. As transactions are approved, they become eligible for payroll.
2. **Open Admin → Payroll** – Owners and admins can open the payroll dashboard directly. HR specialists follow the quick link in the HR Overview tab to land on the same screen.
3. **Create a payroll run** – Choose the statement period, add an internal reference (e.g. “March 2024 Auto/Life”), and pick whether to push payouts to Stripe automatically.
4. **Review generated entries** – The system groups transactions by producer. Adjust bonuses, manual deductions, or employer contributions inline. Use the filters to focus on a single workspace or role.
5. **Attach notes** – Add reviewer notes to explain manual adjustments. Notes appear in the HR profile view so people operations can answer teammate questions quickly.
6. **Approve and submit** – Mark the run as `ready`. If Stripe is connected, the “Send payouts” button creates disbursements and records the Stripe confirmation. Otherwise, export a CSV for manual payment and set the run to `paid` once complete.
7. **Sync with HR** – HR specialists can open an employee profile, scroll to Payroll history, and confirm the run name, amount, and payment reference without needing Admin access.
8. **Archive when reconciled** – Once finance closes the books, set the run to `archived`. Archived runs remain searchable and downloadable for audits.

## Reporting & exports

- Use the **Download payout register** button to export a CSV including employee IDs, run IDs, gross/net amounts, and Stripe references.
- The **Variance inspector** highlights producers whose payout differs from the prior period by more than 15%. Click through to review the underlying transactions before approving.
- Toggle the **“Include inactive users”** switch when processing off-cycle adjustments for terminated producers.

## Configuration checklist

- Confirm Stripe credentials are configured in `app/stripe_integration.py` and the environment variables described in `docs/stripe.md` are set.
- Map each producer to the correct workspace and agent so payroll entries inherit the right overrides and split percentages.
- Coordinate with HR to align on naming conventions for payroll runs. Matching names across HR, finance, and accounting makes downstream reconciliation easier.
- Schedule a monthly export of payroll runs to your accounting platform. The CSV structure is consistent, so you can automate the import with your preferred RPA or middleware tool.

## Troubleshooting tips

- If a producer is missing from a payroll run, confirm their workspace assignment and that their transactions were marked as approved in the Imports queue.
- To adjust a posted run, duplicate it via the **Clone run** button, apply the correction, and archive the original with a note. This preserves an audit trail of the change.
- Stripe payout failures surface in the run detail view with the error message returned by Stripe. Resolve the issue (e.g. invalid bank account) and click **Retry payout**.
- Use the **HR sync status** column to verify whether HR has reviewed a run. HR specialists can mark a run as “acknowledged” from their portal once every employee question is resolved.
