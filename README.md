# CMS — HR Document Generation Platform

A Django 5.2 platform for HR teams to generate, manage, and audit official employment documents (Offer Letters, Salary Certificates, NOCs, Experience Certificates). Shares a MySQL database with the AMS repo over a Docker network.

---

## Architecture Overview

```
CMS  (this repo)  →  http://localhost:8001
AMS  (other repo) →  http://localhost:80

Both share:
  - shared_mysql container  (MySQL 8.0, port 3306)
  - shared_network          (Docker bridge network)
  - ams_receipts_shared     (Docker volume for cross-app file access)
```

---

## Prerequisites

Before starting CMS, run these once on your machine:

```bash
# 1. Create the shared Docker network
docker network create shared_network

# 2. Create the shared receipts volume
docker volume create ams_receipts_shared
```

> If AMS is already running these will already exist — skip if so.

---

## Quick Start

```bash
# Clone and start
git clone https://github.com/raman2324/CMS-AMS.git
cd CMS-AMS
docker compose up --build
```

First boot automatically:
- Runs all migrations
- Seeds companies, templates, and demo users
- Encrypts existing files (no-op if key not set)

App runs at **http://localhost:8001**

---

## Login Credentials

| Role | Username | Password | Access |
|------|----------|----------|--------|
| Admin | `admin` | `Admin@1234` | Django admin panel (`/admin/`) |
| Finance Head | `finance_head` | `Finance@1234` | All documents + Manage panel |
| Issuer | `issuer` | `Issuer@1234` | Generate & view own documents |
| Issuer 2 | `issuer2` | `Issuer2@1234` | Generate & view own documents |
| Viewer | `viewer` | `Viewer@1234` | Read-only document list + audit log |

> **Tip:** Use `finance_head` to explore the full app. `admin` redirects to the Django admin panel.

---

## Features

### Document Generation
- 4 letter types: **Offer Letter**, **Salary Certificate**, **NOC**, **Experience Certificate**
- PDF generation via WeasyPrint (no local system deps needed — runs inside Docker)
- HTMX-powered live employee search and dynamic form fields
- Live HTML preview before generating PDF

### Document Management
- SHA-256 content hash on every generated PDF
- Void workflow with mandatory reason (PDF retained for compliance)
- Legal hold (lock/unlock) — Finance Head only
- Re-download any previously generated document

### Finance Head Manage Panel (`/documents/manage/`)
- Create, edit, deactivate users
- Add and edit companies
- Create, edit, activate, delete letter templates
- Upload a `.docx` file to convert to HTML template (powered by Mammoth)

### Contract Lens (`/documents/contract-lens/cadient/`)
- AI-powered vendor contract analysis via Claude (Anthropic API)
- Single PDF extraction, multi-document group analysis, contract merging
- Encrypted storage for all uploaded contract files
- Separate audit log for all Contract Lens events

### Audit & Security
- Append-only audit trail (protected by DB triggers — cannot be modified or deleted)
- Separate CMS audit log and Contract Lens audit log
- Login throttling: account locked after 5 failed attempts (30-min cooldown)
- All PDFs and uploads encrypted at rest (AES-256 Fernet)
- Session expires after 8 hours or browser close

---

## Environment Variables

All configured in `docker-compose.yml`. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-key-...` | Django secret key — change in production |
| `DEBUG` | `True` | Set `False` for production |
| `DOCUMENT_ENCRYPTION_KEY` | set | Fernet key for PDF/upload encryption |
| `DB_ENGINE` | `django.db.backends.mysql` | Database backend |
| `DB_NAME` | `cms_db` | Database name |
| `DB_HOST` | `shared_mysql` | MySQL container name |
| `ANTHROPIC_API_KEY` | *(not set)* | Required for Contract Lens AI features |

To enable Contract Lens, add to `docker-compose.yml` under `environment`:
```yaml
- ANTHROPIC_API_KEY=your-key-here
```

---

## Database — Shared MySQL

CMS and AMS share the same MySQL 8.0 container (`shared_mysql`). On first boot, `init-mysql.sql` creates both databases:

```sql
CREATE DATABASE IF NOT EXISTS cms_db ...;
CREATE DATABASE IF NOT EXISTS ams_db  ...;
GRANT ALL PRIVILEGES ON cms_db.* TO 'admin'@'%';
GRANT ALL PRIVILEGES ON ams_db.*  TO 'admin'@'%';
```

**CMS** uses `cms_db`. **AMS** uses `ams_db`. They never touch each other's tables.

> If you already have a running `shared_mysql` from AMS, CMS will connect to it automatically — do **not** start the `db` service twice. Run AMS first (it owns the MySQL container), then start CMS.

---

## Running Both Repos

**Recommended order:**

```bash
# Terminal 1 — start AMS first (owns the shared_mysql container)
cd path/to/AMS
docker compose up --build

# Terminal 2 — start CMS (connects to existing shared_mysql)
cd path/to/CMS-AMS
docker compose up --build
```

Both services will be on `shared_network` and share the same MySQL instance.

---

## Management Commands

```bash
# Re-seed all demo data (companies, users, templates, employees)
docker compose exec web python manage.py seed_data --force

# Bulk generate letters from CSV
docker compose exec web python manage.py generate_bulk \
  --template salary_letter \
  --csv /path/to/employees.csv \
  --output-dir /app/local_pdfs/bulk/ \
  --dry-run

# Daily integrity check — verify PDF hashes match storage
docker compose exec web python manage.py reconcile_documents

# Encrypt files created before encryption was configured
docker compose exec web python manage.py encrypt_existing_files
```

---

## Storage — Switch to S3

Set `DEBUG=False` and add to `docker-compose.yml`:

```yaml
- AWS_STORAGE_BUCKET_NAME=your-bucket
- AWS_S3_REGION_NAME=ap-south-1
- AWS_ACCESS_KEY_ID=...
- AWS_SECRET_ACCESS_KEY=...
# For MinIO local testing:
# - AWS_S3_ENDPOINT_URL=http://minio:9000
```

No application code changes needed.

---

## Project Structure

```
config/              Django settings, URLs, WSGI
accounts/            Custom User model (roles: admin / finance_head / issuer / viewer)
documents/
  models.py          Company, Employee, LetterTemplate, Document, AuditEvent, ContractLensRecord
  views.py           Document views + Contract Lens AI endpoints
  manage_views.py    Finance Head management panel (users, companies, templates)
  manage_forms.py    Forms for the management panel
  services/          PDF generation, storage, encryption
  signals.py         DB triggers for AuditEvent immutability
  management/        CLI commands (seed_data, generate_bulk, reconcile_documents)
uploads/             General file upload management
templates/
  base.html          Bootstrap 5 + HTMX layout with sidebar
  documents/         Document list, generate, detail, audit templates
  manage/            Finance Head management panel templates
  contractlens/      Contract Lens UI templates
  letter_templates/  HTML-to-PDF letter designs (WeasyPrint)
static/css/          App styles
init-mysql.sql       Runs once on MySQL first boot — creates cms_db + ams_db
```
