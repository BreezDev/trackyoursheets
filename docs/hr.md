# TrackYourSheets HR Portal

The HR portal centralises people operations tooling for agency leaders. Access it from the top navigation (HR) if you are an owner, admin, agent, or bookkeeper.

## Features

- **Overview dashboard** – Summaries of active headcount, pending onboarding, two-factor adoption, role distribution, recent hires, anniversaries, and workspace coverage.
- **Employee directory** – Filterable directory with search across names, emails, offices, and workspaces plus last-login insights.
- **Onboarding tracker** – Checklist progress for the last 90 days covering account activation, first login, two-factor, workspace assignment, and notification confirmation.
- **Policies & benefits hub** – Curated resource cards linking to handbook, benefits, PTO, compliance, and training artefacts.
- **Security quick actions** – Admin console card groups notification preferences and two-factor controls in one place with organisation-wide adoption stats.

## Usage tips

1. **Grant access** – Only owner, admin, agent, and bookkeeper roles see the HR navigation link. Producers can still be managed, but they cannot open the portal.
2. **Update resources** – Replace the example links in `app/hr.py` with your own hosted files so teammates download live documents.
3. **Monitor onboarding** – Visit the Onboarding tab weekly to confirm every step is completed. Toggle notifications or two-factor from Admin → Security if a teammate is missing a requirement.
4. **Celebrate milestones** – Use the Upcoming anniversaries widget to plan recognitions and retention check-ins.
5. **Review workspace coverage** – Ensure each workspace lists an agent and active member count; adjust assignments from Admin → Workspaces if gaps appear.

For additional configuration details see `admin/index.html` for security preferences and `app/hr.py` for portal data helpers.
