# HR Document Generation Platform — v1 Prototype

## Quick Start (Docker)

```bash
# 1. Start Docker Desktop, then:
docker compose up --build

# 2. Open http://localhost:8000
```

First boot runs migrations, seeds companies + templates + demo users automatically.

## Demo Credentials

| Role   | Username | Password     | Can do                               |
|--------|----------|--------------|--------------------------------------|
| Admin  | admin    | Admin@1234   | Everything + Django admin panel      |
| Issuer | issuer   | Issuer@1234  | Generate & download letters          |
| Viewer | viewer   | Viewer@1234  | View document list + audit log only  |

**Django admin:** http://localhost:8000/admin/ (use admin credentials)

## Features

- Generate 4 letter types: Offer Letter, Salary Letter, NOC, Experience Certificate
- Companies pre-seeded: Cadient Talent, Vorro, CommerceV3
- PDF generation via WeasyPrint (runs inside Docker — no local system deps needed)
- SHA-256 content hash stored with every document
- Full audit trail (append-only, DB trigger protected)
- HTMX-powered live employee search + dynamic form fields
- Void workflow with mandatory reason
- Re-download any previously generated document
- Django admin with CSV audit export

## Switching from SQLite to PostgreSQL

Edit `docker-compose.yml`, uncomment the `DB_*` environment variables, and add a `db:` service:

```yaml
db:
  image: postgres:15
  environment:
    POSTGRES_DB: cms_db
    POSTGRES_USER: cms_user
    POSTGRES_PASSWORD: cms_password
  volumes:
    - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

That's the only change needed — zero application code changes.

## Switching from Local Filesystem to S3

Set `DEBUG=False` in `docker-compose.yml` and add:

```yaml
- AWS_STORAGE_BUCKET_NAME=your-bucket
- AWS_S3_REGION_NAME=ap-south-1
- AWS_ACCESS_KEY_ID=...
- AWS_SECRET_ACCESS_KEY=...
```

For MinIO (local S3-compatible testing), also add:
```yaml
- AWS_S3_ENDPOINT_URL=http://minio:9000
```

## Management Commands

```bash
# Bulk generate from CSV (e.g., annual increment day)
docker compose exec web python manage.py generate_bulk \
  --template salary_letter \
  --csv /path/to/employees.csv \
  --output-dir /app/local_pdfs/bulk/ \
  --dry-run

# Daily integrity check (verify PDF hashes match storage)
docker compose exec web python manage.py reconcile_documents

# Re-seed data
docker compose exec web python manage.py seed_data --force
```

## Architecture

```
config/         Django project (settings, urls, wsgi)
accounts/       Custom User model (roles: admin / issuer / viewer)
documents/
  models.py     Company, Employee, LetterTemplate, Document, AuditEvent
  services/     Core business logic (generate_document, void_document, download_document)
  views.py      Django views + HTMX endpoints
  admin.py      Django admin customizations
  signals.py    DB triggers for AuditEvent immutability
templates/
  base.html     Bootstrap 5 layout
  documents/    UI templates (generate, list, detail)
  letter_templates/  HTML-to-PDF letter templates (WeasyPrint)
static/css/     App styles
```

