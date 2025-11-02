# TrackYourSheets HR Portal

The HR portal centralises people operations tooling for agency leaders. Access it from the top navigation (HR) if you hold the **owner**, **admin**, **agent**, **bookkeeper**, or dedicated **hr** role. Producers and other contributor-only personas can still submit concerns through the HR support form, but they cannot open the management workspace.

## Feature tour

- **Overview dashboard** – Track headcount, active vs. pending onboarding, two-factor adoption, role distribution, recent hires, anniversaries, open HR reports, and workspace coverage in one view. Every widget is clickable, leading to deeper detail pages.
- **Employee directory** – Filter by office, workspace, status, or role (including the new HR role) and export a CSV snapshot from your browser. Each profile summarises job data, emergency contacts, payroll history, HR interactions, and document acknowledgements.
- **Onboarding tracker** – Monitors the last 90 days of invites and flags missing steps: account activation, first login, two-factor, workspace assignment, notification confirmation, and policy acknowledgements. Use the quick actions on each row to nudge teammates by email.
- **Policies & benefits hub** – Curated resource cards linking to handbook, benefits, PTO, compliance, DEI training, and insurance licencing artefacts. You can categorise resources and record acknowledgement receipts directly in the portal.
- **Documents & acknowledgements** – Upload policy PDFs, manage acknowledgement status, and filter by category (policy, payroll, compliance, culture, custom). The portal surfaces who signed and timestamps every confirmation.
- **HR reports & complaint queue** – Intake forms route to a triaged queue with priority labels, assignment options, and resolution timelines. HR specialists, admins, and agents can collaborate on notes before closing an issue.
- **Security quick actions** – Card controls surface notification preferences, two-factor enforcement, and password reset toggles, pulling live adoption percentages from the org record.

## Daily operations checklist

1. **Assign the HR role** – Invite HR-only teammates via Admin → Invite teammate and select “HR specialist”. They will see the HR dashboard without needing broader admin permissions.
2. **Review inboxes** – Start each day on the HR Overview dashboard and open urgent complaints or overdue onboarding steps straight from the tiles.
3. **Update resources** – Replace placeholder document links in `app/hr.py` with your own hosted files so teammates download live policies. Use categories to keep compliance and payroll documents distinct.
4. **Audit payroll tie-ins** – Jump to the Payroll tab (documented in `docs/payroll.md`) to confirm recent payouts match HR records. The payroll quick links live under the HR navigation for rapid context switching.
5. **Celebrate milestones** – Use the Upcoming anniversaries widget to plan recognition notes and retention check-ins; export the list for your employee engagement calendar.
6. **Align with leadership** – Export role distribution and onboarding completeness metrics before leadership meetings so revenue, HR, and operations stay on the same page.

For additional configuration details see `admin/index.html` for security preferences and `app/hr.py` for portal data helpers.
