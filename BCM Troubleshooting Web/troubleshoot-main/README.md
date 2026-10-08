# BCM-Troubleshooting Web

A Django web application for managing and following database-driven
troubleshooting flows. The current development database is SQLite.

## Local development (Windows PowerShell)

Run these commands from the workspace root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
Set-Location .\troubleshoot-main
& ..\.venv\Scripts\python.exe manage.py migrate
& ..\.venv\Scripts\python.exe manage.py createsuperuser
& ..\.venv\Scripts\python.exe manage.py runserver
```

The site opens at <http://127.0.0.1:8000/>. The admin is at `/admin/`.
Create product ranges, problems, flows, steps and choices in the admin before
technicians will see guide content.

## Managing configuration-driven guides

The catalog starts with VSAT, Starlink, OneWeb and Mobile. Product cards without
an active flow and starting step appear as unavailable placeholders; publishing
an active flow makes the product selectable.

Create questions in the **Configuration questions** admin. Assign each question
to one or more products, then select whether it belongs to **System
configuration** (before problem selection) or **Problem diagnosis** (after
selecting a problem). A diagnostic question may optionally be limited to one
problem. Add answer choices to each question. Set **Depends on option** when a
follow-up question should appear only for a particular answer, such as an ACU
model question after selecting an ACU type. Shared questions such as a Hydrabox
version are assigned only to the products that use them.

On each troubleshooting flow, add a configuration requirement for every
answer that must match that flow. All listed requirements must match; an
omitted question does not restrict that flow. Create separate flows for
alternative equipment or diagnosis answers. Technicians select a product,
answer its setup questions, choose a problem, and answer its diagnostic
questions before the app shows matching flows. Flow steps, branches, images,
and downloadable procedures continue to be managed in the admin.

## Deployment configuration

Use the main project entry point at `troubleshoot-main\manage.py`. Set the
following environment variables in the deployment platform's secret/config
manager; do not commit production values or `.env` files:

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY` to a unique, high-entropy value
- `DJANGO_ALLOWED_HOSTS` to comma-separated hostnames serving the application
- `DJANGO_CSRF_TRUSTED_ORIGINS` to full origins (including `https://`) when
  requests originate from a separate trusted origin
- `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_HOST_USER`,
  `DJANGO_EMAIL_HOST_PASSWORD`, `DJANGO_EMAIL_USE_TLS`,
  `DJANGO_EMAIL_USE_SSL`, `DJANGO_EMAIL_TIMEOUT` and
  `DJANGO_DEFAULT_FROM_EMAIL` when production email is required
- `DJANGO_EMAIL_BACKEND` to explicitly select a different configured backend
- `DJANGO_SECURE_SSL_REDIRECT=true` after HTTPS is configured (this defaults
  to true when debug is disabled)
- `DJANGO_SECURE_HSTS_SECONDS=31536000` only after HTTPS works for the domain
  and all clients should be required to use HTTPS
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=true` and
  `DJANGO_SECURE_HSTS_PRELOAD=true` only after every affected hostname is
  confirmed to support HTTPS
- `DJANGO_TRUST_X_FORWARDED_PROTO=true` only when a trusted reverse proxy
  overwrites the `X-Forwarded-Proto` header

Production startup intentionally fails if debug is disabled without both a
secret key, allowed-host list and SMTP host (unless a different email backend
is explicitly configured). Secure cookies, content-type protection and HTTPS
redirection are enabled when debug is disabled. HSTS remains off until
explicitly configured because it should only be enabled after the HTTPS domain
and deployment topology are confirmed. Django's deployment check may also
report optional HSTS subdomain/preload warnings; enable those only when every
affected domain is confirmed to support HTTPS.

Before serving production traffic:

1. Install the pinned dependencies and configure environment variables.
2. Run `python manage.py check --deploy` and review applicable warnings.
   HSTS subdomain/preload warnings should remain until the domain topology is
   confirmed safe for those settings.
3. Run `python manage.py migrate` and `python manage.py collectstatic --noinput`.
4. Serve the WSGI/ASGI application with a production server; do not use
   `runserver` for deployment.
5. Serve collected static files from `STATIC_ROOT` and persist/backup both the
   SQLite database and `MEDIA_ROOT`.
6. Keep media behind the authenticated application routes; do not expose the
   media directory as a public static directory.

SQLite is retained for this initial internal version. Use a persistent disk
and regular backups; plan a database migration before deploying multiple
application instances or workloads that need higher write concurrency.
