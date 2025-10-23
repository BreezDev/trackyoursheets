# TrackYourSheets

TrackYourSheets is a Flask-powered commissions CRM tailored for independent insurance agencies that need to tame multi-carrier statements and automate producer payouts. The application is optimised for deployment on [PythonAnywhere](https://www.pythonanywhere.com/) and ships with a modern Bootstrap 5 interface, multi-tenant data model, and a configurable admin console.

## Key capabilities

- **Statement intake** – Upload carrier CSV statements, map columns once, and automatically build normalised import batches with duplicate detection primitives.
- **Identity matching (foundations)** – Persist customer, policy, and producer records ready for fuzzy-matching enhancements.
- **Commission engine** – Configure per-carrier rulesets with support for new vs. renewal logic, flat amounts, and priority weighting.
- **Reconciliation pipeline** – Track batches through import → review → finalisation stages with full audit history scaffolding.
- **Payouts & analytics** – Generate producer statements, carrier mix analytics, and import health snapshots.
- **Admin controls** – Manage organisations, users, carriers, rules, and API tokens with role-based access.

## Project structure

```
app/
  __init__.py        # Flask app factory, configuration, CLI seeds
  models.py          # SQLAlchemy ORM models for all key entities
  auth.py            # Signup/login/logout views
  main.py            # Dashboard & onboarding screens
  admin.py           # Admin console blueprint
  imports.py         # Import pipeline (CSV upload, row persistence)
  reports.py         # Analytics & payout views
  templates/         # Jinja2 templates (Bootstrap 5 + custom design)
  static/css/        # Custom styles
app.py               # Entrypoint for WSGI/Flask CLI
requirements.txt     # Python dependencies
README.md            # You are here
admin.md             # Admin console operations guide
```

## Getting started locally

1. **Create a virtual environment**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Initialise the database** (SQLite by default):

   ```bash
   flask --app app.py init-db
   ```

   The command creates all tables and seeds the Starter, Growth, and Scale subscription plans.

3. **Run the development server**

   ```bash
   flask --app app.py run --debug
   ```

4. **Create your first workspace**

   - Visit `http://127.0.0.1:5000/signup`.
   - Choose a seeded plan, provide your agency details, and you’ll be redirected to onboarding.

## Deploying on PythonAnywhere

1. **Clone the repository** into your PythonAnywhere account and create a virtualenv.
2. **Install dependencies** with `pip install -r requirements.txt` inside the virtualenv.
3. **Configure environment variables** in the PythonAnywhere dashboard:
   - `SECRET_KEY` – strong random string.
   - `DATABASE_URL` (optional) – defaults to SQLite (`sqlite:///trackyoursheets.db`). For PythonAnywhere MySQL, supply `mysql+mysqlclient://user:password@host/dbname`.
4. **Run the seed command** once:

   ```bash
   flask --app /home/<user>/trackyoursheets/app.py init-db
   ```

5. **Set up the WSGI configuration** to point at `app:app`.
6. **Create scheduled tasks** (optional) to process imports, rebuild PDFs, and perform nightly backups.

## Next steps & roadmap hints

- Hook up Stripe billing (Checkout & Customer Portal) by wiring the `Subscription` model to live Stripe events.
- Extend the import pipeline with OCR (pdfplumber/Tesseract) and asynchronous job processing via PythonAnywhere scheduled tasks.
- Implement fuzzy matching and the learn-as-you-go resolver against `customers` and `policies` tables.
- Generate producer statements as downloadable PDFs using WeasyPrint or wkhtmltopdf.
- Expose webhook and API endpoints using the `APIKey` infrastructure and JWT auth.

## Testing guidance

The seed command and modular design make it straightforward to add unit tests using `pytest` or Flask’s test client. Recommended high-value areas include:

- Commission rule evaluation matrix.
- Import row validation/duplicate detection.
- Multi-tenant access controls for each role.
- Stripe webhook signature verification (when enabled).

## Support

For questions or contributions, please open an issue or contact the TrackYourSheets maintainers. Enhancements are welcome!
