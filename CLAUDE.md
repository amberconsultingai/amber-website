# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running locally

```bash
# Activate the virtual environment (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the dev server
python app.py
```

The app runs at `http://127.0.0.1:5000`. The venv folder is `venv/` (not `amber/`).

## Deploying to Render

- **Web Service** — build: `pip install -r requirements.txt`, start: `gunicorn --timeout 120 app:app`
- **Database** — Render managed PostgreSQL; use the Internal Database URL as `DATABASE_URL`
- Render free tier blocks outbound SMTP and shell access. Email is sent via Resend API. Shell commands (`flask reset-db`) cannot be run remotely.
- Adding new DB columns requires running `ALTER TABLE` SQL manually via an external PostgreSQL client (TablePlus, psql) using the external DB URL.

## Architecture

All application logic lives in two files:

- **`app.py`** — Flask app, all routes, email helpers, Cloudinary config, Flask-Limiter, Flask-Login setup. Tables are created at startup via `db.create_all()`.
- **`models.py`** — SQLAlchemy models: `User`, `File`, `Message`, `Payment`.

**User roles:** `client` or `admin`. Role is assigned at registration — if the registering email matches the `ADMIN_EMAIL` env var, they get `admin`, otherwise `client`. There is no role management UI; change via database directly.

**File storage:** Cloudinary (`resource_type='auto'`, folder `amber-consulting/{user_id}/`). Files are downloaded via the `/download/<file_id>` Flask proxy route — do not link directly to Cloudinary URLs, as `fl_attachment` is unreliable for raw file types.

**Email:** All email (contact form, password reset, notifications) uses Resend via `resend.Emails.send()`. From address is locked to `onboarding@resend.dev` on the free tier.

**Database:** SQLite locally (`sqlite:///amber.db`), PostgreSQL on Render. The `DATABASE_URL` prefix is normalised to `postgresql+psycopg://` at startup for psycopg3 compatibility.

**Session timeout:** 30-minute server-side expiry (`PERMANENT_SESSION_LIFETIME`). Client-side inactivity timer in dashboard templates redirects to `/logout?timeout=1` after 30 minutes.

## Key env vars

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing |
| `DATABASE_URL` | SQLAlchemy connection string |
| `ADMIN_EMAIL` | Email that receives admin role on registration |
| `RESEND_API_KEY` | Resend email API |
| `MAIL_RECIPIENT` | Where contact form + admin notifications are sent |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | File storage |
