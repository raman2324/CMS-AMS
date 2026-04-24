# CMS + AMS — Unified HR Platform

A Django 5.2 application combining two systems:

- **CMS** (Contract Management System) — Generate, manage, and audit HR letters (Offer Letters, Salary Letters, NOCs, Experience Certificates)
- **AMS** (Approval Management System) — Workflow engine for employee expense and subscription approval requests

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Demo Credentials](#demo-credentials)
- [Application URLs](#application-urls)
- [Role Reference](#role-reference)
- [AMS Approval Flow](#ams-approval-flow)
- [Document Storage (MinIO / S3)](#document-storage-minio--s3)
- [Database](#database)
- [Environment Variables](#environment-variables)
- [Management Commands](#management-commands)
- [Architecture](#architecture)
- [Production Deployment](#production-deployment)

---

## Features

### CMS — Document Generation
- Generate 4 letter types: **Offer Letter**, **Salary Letter**, **No Objection Certificate**, **Experience Certificate**
- WeasyPrint PDF rendering (runs inside Docker — no local deps needed)
- AES-256 Fernet encryption on all stored PDFs
- SHA-256 content hash for every document (tamper detection)
- Append-only audit trail per document
- HTMX-powered live employee search and dynamic form fields
- Void workflow with mandatory reason
- Re-download any previously generated document
- Finance Head can lock documents (legal hold)

### AMS — Approval Workflow
- One-off expense and recurring subscription approval requests
- Multi-step FSM workflow: `pending_manager → pending_finance → provisioning → active`
- C-suite employees skip manager step (go direct to finance)
- Receipt upload support (PDF / JPG / PNG)
- Renewal lifecycle for active subscriptions
- IT provisioning step for subscriptions
- Email notification at each state transition
- Full audit log per request

### Shared
- Single MySQL database for both systems
- S3-compatible file storage via MinIO (dev) or AWS S3 (prod)
- Login throttling: 5 failed attempts → 30-minute lockout (django-axes)
- Session expires after 8 hours or on browser close

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 5.2 |
| Database | MySQL 8.0 |
| File Storage | MinIO (dev) / AWS S3 (prod) via django-storages |
| PDF Generation | WeasyPrint 68 |
| Encryption | cryptography (Fernet AES-256) |
| Auth | Django auth + django-allauth + django-axes |
| Frontend | Bootstrap 5 (CMS) + Tailwind CSS + HTMX (AMS) |
| Containerization | Docker + Docker Compose |
| Web Server | Gunicorn (prod) / Django runserver (dev) |
| Static Files | Whitenoise |

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Ports **8001**, **3306**, **9000**, **9001** free on your machine

### 1. Clone and start

```bash
git clone <repo-url>
cd CMS
docker compose up --build
```

First boot automatically:
1. Creates the `cms-docs` bucket in MinIO
2. Runs all Django migrations
3. Collects static files
4. Seeds companies, templates, employees, and demo users
5. Encrypts any existing files
6. Starts the development server

### 2. Open the app

| Service | URL |
|---------|-----|
| CMS / AMS App | http://192.168.80.233:8001 |
| MinIO Console | http://192.168.80.233:9001 |

> Replace `192.168.80.233` with your machine's local IP, or use `localhost`.

### 3. Useful Docker commands

```bash
# Start in background
docker compose up -d --build

# Follow logs
docker compose logs -f web

# Stop (keep data)
docker compose down

# Full reset — wipes ALL data and re-seeds from scratch
docker compose down -v && docker compose up --build

# Run a management command
docker compose exec web python manage.py <command>

# Open a shell inside the container
docker compose exec web bash
```

---

## Demo Credentials

### CMS Users (document generation)

| Role | Username | Password | Access |
|------|----------|----------|--------|
| Admin | `admin` | `Admin@1234` | Full CMS access |
| Finance Head | `finance_head` | `Finance@1234` | All documents + template management |
| Finance Executive | `issuer` | `Issuer@1234` | Generate & download own documents |
| Finance Executive | `issuer2` | `Issuer2@1234` | Generate & download own documents |
| Viewer | `viewer` | `Viewer@1234` | View list + audit log, no generation |

### AMS Users (approval workflow)

All AMS user passwords: **`Pass@1234`**

| Role | Email | Org Position |
|------|-------|--------------|
| Admin | `admin@bv.com` | C-suite (no manager) |
| Finance Head | `finance.head@bv.com` | C-suite (no manager) |
| Finance Executive | `carol@bv.com` | C-suite (approves finance queue) |
| Finance Executive | `eve@bv.com` | C-suite (approves finance queue) |
| IT | `dave@bv.com` | C-suite (provisions subscriptions) |
| Viewer | `victor@bv.com` | Read-only audit access |
| Manager | `bob@bv.com` | Reports to admin@bv.com |
| Manager | `meera@bv.com` | Reports to admin@bv.com |
| Employee | `alice@bv.com` | Reports to bob → carol/eve → done |
| Employee | `raj@bv.com` | Reports to bob → carol/eve → done |
| Employee | `priya@bv.com` | Reports to meera → carol/eve → done |
| Employee | `sam@bv.com` | Reports to meera → carol/eve → done |

---

## Application URLs

| URL | Description |
|-----|-------------|
| `/login/` | Login page |
| `/logout/` | Logout |
| `/documents/` | CMS — Document list |
| `/documents/generate/` | Generate a new PDF letter |
| `/documents/manage/` | Template + employee management (Finance Head / Admin) |
| `/uploads/` | File uploads list |
| `/uploads/upload/` | Upload a new file |
| `/ams/` | AMS home → redirects to inbox |
| `/ams/requests/inbox/` | AMS inbox (pending items for current user) |
| `/ams/requests/new/` | Submit a new approval request |
| `/ams/requests/my/` | My submitted requests |
| `/ams/requests/<id>/` | Request detail + action buttons |
| `/ams/subscriptions/` | Active subscription list |
| `/ams/expenses/` | Expense history |
| `/ams/admin-ams/` | AMS audit log (Admin / Finance Head) |

---

## Role Reference

### CMS Roles

| Role | Generate Docs | Download | Void Any | Manage Templates | Audit Log | Lock Docs |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| Admin | Yes | Yes | Yes | Yes | Yes | No |
| Finance Head | Yes | Yes | Yes | Yes | Yes | Yes |
| Finance Executive | Yes | Own only | Own only | No | No | No |
| Viewer | No | No | No | No | Yes | No |

### AMS Roles

| Role | Submit Request | Approve (Manager Step) | Approve (Finance Step) | Provision (IT) | Terminate |
|------|:---:|:---:|:---:|:---:|:---:|
| Admin | Yes (C-suite) | Yes | Yes | Yes | Yes |
| Finance Head | Yes (C-suite) | No | Yes | No | Yes |
| Finance Executive | Yes (C-suite) | No | Yes | No | Yes |
| Manager | Yes (via chain) | Yes | No | No | No |
| Employee | Yes (via chain) | No | No | No | No |
| IT | No | No | No | Yes | No |
| Viewer | No | No | No | No | No |

---

## AMS Approval Flow

### Standard Employee Flow

```
Employee submits request
        │
        ▼
  pending_manager   ← Manager sees it in Inbox
        │                 Can: Approve (choose finance exec) or Reject
        ▼
  pending_finance   ← Finance Executive sees it
        │                 Can: Approve or Reject
        │
        ├─ One-off expense ──► approved  (workflow ends)
        │
        └─ Subscription ──► provisioning  ← IT enters vendor account ID + billing start
                                  │
                                  ▼
                                active
                                  │
                       (when renewal is needed)
                                  │
                     active_pending_renewal  ← Employee clicks "Initiate Renewal"
                                  │
                               renewing     ← Finance approves or rejects renewal
                                  │
                                active  (cycle repeats)
```

### C-suite Flow

Users with no `reports_to` set are treated as C-suite and skip the manager step:

```
C-suite submits ──► pending_finance ──► approved / provisioning
```

### To test the full flow step by step

1. Log in as `alice@bv.com` → submit a new One-off request
2. Log in as `bob@bv.com` (Manager) → Inbox → Approve, select `carol@bv.com` as finance exec
3. Log in as `carol@bv.com` (Finance) → Inbox → Approve
4. Request is now `approved`

For a Recurring/Subscription request, after step 3 it moves to `provisioning`:

5. Log in as `dave@bv.com` (IT) → Inbox → enter Vendor Account ID + Billing Start → Mark as Provisioned
6. Subscription is now `active`

---

## Document Storage (MinIO / S3)

### Development — MinIO

MinIO is an S3-compatible object storage that runs as a Docker container. No AWS account needed.

| | Value |
|-|-------|
| S3 API | `http://localhost:9000` |
| Web Console | http://192.168.80.233:9001 |
| Login | `minioadmin / minioadmin` |
| Bucket | `cms-docs` |

Browse files: open MinIO console → Object Browser → `cms-docs`

All PDFs and uploads are Fernet-encrypted before being stored in the bucket.

### Switch to AWS S3 (Production)

Only environment variable changes are needed — zero code changes:

```yaml
# In docker-compose.yml web service environment, remove this line:
- AWS_S3_ENDPOINT_URL=http://minio:9000

# Update these to real AWS credentials:
- AWS_STORAGE_BUCKET_NAME=your-real-bucket
- AWS_S3_REGION_NAME=ap-south-1
- AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
- AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

Also remove the `minio:` service block from `docker-compose.yml`.

---

## Database

### Connection details (Docker dev)

```
Host:      192.168.80.233   Port: 3306
Database:  cms_db
User:      admin
Password:  secret
```

Both CMS and AMS share the single `cms_db` database via Django's default database connection. No routing needed.

### Fresh reset

```bash
docker compose down -v && docker compose up --build
```

Deletes and re-creates both MySQL and MinIO volumes, then re-seeds everything.

### Connect with a GUI client

Use TablePlus, DBeaver, or MySQL Workbench with the connection details above. All CMS tables start with `documents_` / `uploads_`, and all AMS tables start with `approvals_` / `audit_` etc.

---

## Environment Variables

Copy `.env.example` to `.env` for running outside Docker. Inside Docker, all values are set in `docker-compose.yml`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `True` | Set `False` in production |
| `SECRET_KEY` | dev key | Django secret key — use a long random string in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,...` | Comma-separated hostnames |
| `DOCUMENT_ENCRYPTION_KEY` | _(empty)_ | Fernet key — files stored unencrypted if not set |
| `DB_ENGINE` | sqlite3 | `django.db.backends.mysql` for MySQL |
| `DB_NAME` | `db.sqlite3` | Database name |
| `DB_USER` | _(empty)_ | Database username |
| `DB_PASSWORD` | _(empty)_ | Database password |
| `DB_HOST` | _(empty)_ | Database host |
| `DB_PORT` | _(empty)_ | Database port |
| `AWS_STORAGE_BUCKET_NAME` | _(empty)_ | Bucket name — activates S3 storage when set |
| `AWS_S3_REGION_NAME` | `us-east-1` | AWS / MinIO region |
| `AWS_ACCESS_KEY_ID` | _(empty)_ | AWS / MinIO access key |
| `AWS_SECRET_ACCESS_KEY` | _(empty)_ | AWS / MinIO secret key |
| `AWS_S3_ENDPOINT_URL` | _(empty)_ | MinIO endpoint — omit for real AWS S3 |
| `DEFAULT_FROM_EMAIL` | `noreply@example.com` | Sender address for notification emails |
| `EMAIL_BACKEND` | console | Django email backend class |
| `CSRF_TRUSTED_ORIGINS` | _(empty)_ | Comma-separated trusted origins (needed in production) |

### Generate an encryption key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the output as `DOCUMENT_ENCRYPTION_KEY`. Back this key up securely — losing it means losing access to all encrypted files.

---

## Management Commands

Run with: `docker compose exec web python manage.py <command>`

### Seeding

```bash
# Seed CMS demo data (idempotent — safe to re-run)
python manage.py seed_data

# Force re-create letter templates (overwrites existing HTML)
python manage.py seed_data --force

# Seed AMS users covering every role
python manage.py seed
```

### Document Operations

```bash
# Re-encrypt all stored files (run after rotating DOCUMENT_ENCRYPTION_KEY)
python manage.py encrypt_existing_files

# Verify SHA-256 hashes match storage (integrity/tamper check)
python manage.py reconcile_documents

# Bulk-generate documents from a CSV (dry-run first)
python manage.py generate_bulk --template "Offer Letter" --csv employees.csv --dry-run
python manage.py generate_bulk --template "Offer Letter" --csv employees.csv
```

### AMS Operations

```bash
# Send renewal reminder emails for expiring subscriptions
python manage.py send_renewal_reminders

# Run scheduled AMS cron tasks
python manage.py run_cron
```

---

## Architecture

```
CMS/
├── config/                  Django project (settings, urls, wsgi)
├── accounts/                Custom User model — 7 roles, UUID PK, org hierarchy
├── documents/               CMS core
│   ├── models.py            Company, Employee, LetterTemplate, Document, AuditEvent
│   ├── services/
│   │   ├── pdf_service.py   generate_document, download_document, void_document
│   │   └── storage_service.py  Fernet encrypt/decrypt + default_storage wrapper
│   ├── views.py             Document list, generate, detail, download, void
│   └── management/commands/ seed_data, encrypt_existing_files, reconcile, generate_bulk
├── uploads/                 Generic file upload handling
├── ams/
│   ├── approvals/           ApprovalRequest FSM model, views, services, URLs
│   ├── audit/               AMS AuditLog (append-only, delete raises error)
│   ├── expenses/            Expense history views
│   ├── subscriptions/       Subscription list and lifecycle views
│   └── notifications/       Email notification service
├── templates/
│   ├── base.html            Bootstrap 5 shell (CMS pages)
│   ├── ams/base.html        Tailwind CSS shell (AMS pages)
│   ├── documents/           CMS UI templates
│   ├── ams/approvals/       AMS request list, detail, new request templates
│   └── letter_templates/    WeasyPrint HTML → PDF letter templates
├── static/                  CSS and JS source
├── Dockerfile               python:3.12-slim + WeasyPrint + mysqlclient
├── docker-compose.yml       shared_mysql + minio + web
├── entrypoint.sh            Startup script: bucket → migrate → seed → serve
└── init-mysql.sql           Creates cms_db on first MySQL boot
```

### Document generation data flow

```
User fills form
    → view calls generate_document(template_id, employee_id, variables, actor)
    → Django template rendered with company + employee data
    → WeasyPrint converts HTML → deterministic PDF bytes
    → SHA-256 hash computed
    → Fernet AES-256 encrypts PDF bytes
    → default_storage.save() uploads to MinIO / AWS S3
    → Document record written to MySQL (s3_key + content_hash)
    → AuditEvent written (append-only)
```

### AMS request data flow

```
Employee submits form
    → ApprovalRequest saved (state: initial)
    → submit() service called
        → C-suite path: state → pending_finance, notify finance exec
        → standard path: state → pending_manager, notify manager
    → AuditLog entry written
    → Approver sees request in Inbox
    → Approver posts approval/rejection form
    → FSM transition → next state
    → Next actor notified, AuditLog written
```

---

## Production Deployment

### Pre-flight checklist

- [ ] Set `DEBUG=False`
- [ ] Set a long random `SECRET_KEY`
- [ ] Set `ALLOWED_HOSTS` to your domain(s)
- [ ] Generate and back up `DOCUMENT_ENCRYPTION_KEY`
- [ ] Switch to AWS S3 (update credentials, remove `AWS_S3_ENDPOINT_URL`)
- [ ] Remove the `minio:` service from `docker-compose.yml`
- [ ] Use a managed MySQL service (AWS RDS, PlanetScale) — remove the `shared_mysql:` service
- [ ] Set `CSRF_TRUSTED_ORIGINS=https://yourdomain.com`
- [ ] Configure a real email backend (`EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`)
- [ ] Set up HTTPS (nginx reverse proxy + Let's Encrypt, or a cloud load balancer)

### Gunicorn workers

When `DEBUG=False`, `entrypoint.sh` automatically starts Gunicorn instead of the dev server:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

A common rule: `workers = 2 × CPU_cores + 1`. Edit `entrypoint.sh` to tune this.
