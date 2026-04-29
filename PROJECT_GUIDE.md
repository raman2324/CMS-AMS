# CMS + AMS: Unified HR & Operations Platform

## Overview
This application is a dual-purpose enterprise platform designed to streamline Human Resources operations and financial approval workflows. It combines a **Contract Management System (CMS)** for document automation and an **Approval Management System (AMS)** for expenditure control, supplemented by an AI-powered **Contract Lens** for automated data extraction.

---

## Technical Architecture

### Core Stack
- **Framework**: Django 5.2 (Python-based backend)
- **Database**: MySQL 8.0 for structured data persistence.
- **Client-Side**: 
    - **CMS/Contract Lens**: Bootstrap 5 for a clean, professional UI.
    - **AMS**: Tailwind CSS + HTMX for a modern, reactive single-page experience without complex JS frameworks.
- **Object Storage**: S3-compatible storage (MinIO for development, AWS S3 for production).
- **Worker/Tasks**: Management commands for cron-like operations (renewals, integrity checks).

### Security & Integrity
- **Encryption**: AES-256 Fernet encryption for all documents stored in S3/MinIO.
- **Tamper Detection**: SHA-256 content hashing for every generated document to ensure data integrity.
- **Auditability**: Append-only audit trails for every document and approval request.
- **Access Control**: Role-based access (RBAC) with detailed permissions across 7 distinct organizational roles.
- **Protection**: Login throttling via `django-axes` to prevent brute-force attacks.

### Advanced Services
- **PDF Engine**: WeasyPrint for high-fidelity HTML-to-PDF rendering.
- **AI Integration**: Anthropic Claude (Sonnet) API for extracting structured metadata from contract documents.
- **Workflow Engine**: `django-fsm` (Finite State Machine) to manage complex, multi-step approval lifecycles.

---

## Key Modules & Features

### 1. CMS (Contract Management System)
*Automating the HR document lifecycle.*
- **Document Generation**: One-click generation of Offer Letters, Salary Letters, NOCs, and Experience Certificates.
- **Dynamic Templates**: HTMX-powered live employee search and real-time form field variation based on template selection.
- **Compliance Tools**: "Void" workflows with mandatory reasoning and "Legal Hold" (locking) by Finance Heads to prevent tampering or deletion.
- **Integrity Reconciliation**: Automated commands to verify that stored files match their database-recorded hashes.

### 2. AMS (Approval Management System)
*Managing company spending and subscriptions.*
- **Unified Inbox**: A centralized place for managers and finance teams to approve or reject requests.
- **Lifecycle Management**: 
    - **Expenses**: Simple one-off reimbursement flow.
    - **Subscriptions**: Complex flow including IT provisioning (vendor IDs) and active renewal cycles.
- **C-suite Logic**: Automatic escalation logic where senior leadership skips the manager approval step.
- **Evidence Persistence**: Secure storage for receipts (PDF/Image) associated with each request.

### 3. Contract Lens (AI Analysis)
*Digital transformation for physical contracts.*
- **AI Extraction**: Uses Claude LLM to parse uploaded PDFs and extract fields like Customer Name, Contract Number, Effective Dates, and Notice Periods.
- **Human-in-the-Loop**: A Verification UI where staff can review AI suggestions and confirm them before final submission.
- **Encrypted Archiving**: Automatic storage of the source contract alongside its extracted metadata.

---

## Primary Use Cases

| Persona | Primary Use Case |
| :--- | :--- |
| **HR / Finance Executive** | Issuing secure employment letters and tracking their status (sent, voided, or viewed). |
| **Employee** | Submitting expense reports or requesting new software subscriptions with receipt uploads. |
| **Manager / C-level** | Reviewing and approving subordinate spend requests with a transparent audit trail. |
| **IT Department** | Provisioning account credentials for approved software subscriptions and entering billing start dates. |
| **Finance Head / Legal** | Auditing system-wide activities, placing legal holds on documents, and reconciling storage integrity. |
| **Operations Team** | Using AI to quickly digitize legacy contract data into a searchable database. |

---

## Deployment & Scalability
- **Containerization**: Fully Dockerized with Compose for rapid local setup and consistent production environments.
- **Storage Independence**: Seamlessly switches from local MinIO to AWS S3 via environment variables.
- **Performance**: Optimized with Whitenoise for static file serving and Gunicorn for high-concurrency production traffic.
