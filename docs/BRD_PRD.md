# Sharp Sharp Lending Platform -- BRD & PRD

**Owner:** Kayode Abel
**Date:** 2026-10-15
**Status:** Draft -- reflects codebase as of audit date
**Platform name:** Sharp Sharp (internal codename for Sharp Sharp-style lending platform)

---

## Part 1: Business Requirements Document (BRD)

### 1.1 Executive Summary

Sharp Sharp is a production-grade automated digital lending platform targeting unsecured personal loans in Nigeria (N5,000 to N1,000,000). It is a production-grade automated digital lending platform -- the same decisioning flow, loan ladder system, and underwriting approach.

The platform serves two purposes:
1. **Portfolio demonstration** -- a working reference implementation of the Sharp Sharp lending stack
2. **Reusable foundation** -- a codebase that can be white-labelled or extended for consulting engagements, CreditBox SaaS, or standalone deployment

### 1.2 Business Context

| Dimension | Detail |
|---|---|
| **Market** | Nigerian unsecured consumer lending (N-tier digital lenders) |
| **Loan range** | N5,000 (nano) to N1,000,000 (installment) |
| **Loan types** | Bullet (single repayment), Installment (weekly/monthly), Nano (fallback) |
| **Target borrowers** | All borrowers through a single underwriting path (no persona routing) |
| **Revenue model** | Interest income via risk-based pricing (3% to 30% monthly depending on risk tier) |
| **Regulatory** | CBN consumer lending guidelines, 30% APR cap awareness |

### 1.3 Stakeholders

| Stakeholder | Role |
|---|---|
| **Borrower** | Applies for loans, repays, climbs loyalty ladder |
| **Credit Operations** | Reviews borderline applications, manages collections |
| **Risk/Data Science** | Monitors model performance, tunes scorecards and pricing |
| **Engineering** | Maintains platform, integrations, infrastructure |
| **Compliance** | Ensures CBN/NDPC regulatory compliance |

### 1.4 Business Objectives

1. Fully automated loan decisioning from application to disbursement in under 5 minutes
2. Risk-based pricing driven by ML score and loan ladder position
3. Loyalty ladder (7 tiers) as the primary differentiator -- reward repeat borrowers with larger amounts and lower rates
4. Single underwriting path for all borrowers (no persona routing -- ladder does the segmentation)
5. Multi-bureau credit checks (CRC + FirstCentral + CreditRegistry) with fallback logic
6. DPD-tiered collections with automated escalation

### 1.5 Success Criteria

| Metric | Target |
|---|---|
| Application-to-disbursement time | < 5 minutes (automated path) |
| Approval rate | 35-50% of completed applications |
| Model AUC | > 0.75 at launch, > 0.80 within 6 months |
| First-loan default rate (30+ DPD) | < 12% |
| Repeat default rate | < 5% |
| Collections recovery rate (60 DPD) | > 40% |
| Loan ladder tier 3+ penetration | > 25% of active borrowers within 12 months |

### 1.6 Constraints

- No secured lending, BNPL, or business loans in scope
- Nigeria-only (single-country deployment)
- All external integrations are initially stubbed (sandbox-first approach)
- No USSD channel at launch (mobile web + app only)
- Must comply with CBN consumer credit guidelines

---

## Part 2: Product Requirements Document (PRD)

### 2.1 User Personas

#### Persona 1: Borrower
- First-time or repeat digital loan user
- Has a smartphone with internet access
- Nigerian BVN and NIN holder
- Has at least one bank account with transaction history

#### Persona 2: Credit Operations Admin
- Reviews flagged applications
- Manages human review queue
- Monitors portfolio health dashboards
- Handles collections escalation

### 2.2 Product Architecture

```
Frontend (Next.js 14)          Backend (FastAPI)           ML Service (FastAPI)
   Port 3000                      Port 8000                    Port 8001
      |                              |                            |
      +-- Landing page               +-- Auth (signup/login/JWT)  +-- 5 LightGBM models
      +-- Auth (login/signup)         +-- Users (KYC, bank, etc)  +-- Scoring engine
      +-- Onboarding (KYC/bank)       +-- Applications            +-- Monitoring (PSI/KS)
      +-- Loan application            +-- Loans                   |
      +-- Offer review/accept         +-- Admin                   |
      +-- Loan detail/repay           +-- Webhooks                |
      +-- Dashboard                   +-- 14-step Pipeline        |
      +-- Admin panel                 |                            |
                                      +-- PostgreSQL 16            |
                                      +-- Redis 7                  |
                                      +-- Celery workers           |
```

### 2.3 The 14-Step Decisioning Pipeline

This is the core of the platform -- the automated path from application to loan offer.

| Step | Name | What Happens | Service |
|---|---|---|---|
| 1 | Application | User signs up, provides basic PII | auth.py, users.py |
| 2 | KYC Wall | BVN + NIN verification, selfie liveness check | kyc_service.py |
| 3 | Tier Check | Loan ladder tier lookup, eligibility gate | loan_pipeline.py |
| 4 | Data Collection | Employment, income, NOK, loan request | applications.py |
| 5 | Fraud Detection | Device fingerprint + graph network analysis (shared devices with defaulters) | fraud_service.py |
| 6 | Bank Statement | Mono/Okra account linking, statement retrieval | bank_service.py |
| 7 | Income Estimation | Income model from bank transaction patterns | income_service.py |
| 8 | Feature Engineering | Feature vector for ML scoring | scoring_service.py |
| 9 | ML Credit Scoring | Single model, all borrowers through one path | ml-service scoring_engine.py |
| 10 | Risk Tier Classification | Risk tier mapping from model output | scoring_service.py |
| 11 | Credit Bureau | CRC + FirstCentral + CreditRegistry queries | bureau_service.py |
| 12 | Risk-Based Pricing | Rate = f(risk_tier, income, ladder_tier) | pricing_service.py |
| 13 | Loan Offer | Dynamic offer with schedule, expiry, nano fallback | offer_service.py |
| 14 | Monitoring | PSI/AUC/KS drift tracking, DPD-tiered collections | monitoring.py, tasks.py |

### 2.4 Loan Products

| Product | Type | Amount Range | Tenure | Frequency | Notes |
|---|---|---|---|---|---|
| Personal Loan | Installment | N20,000-N1,000,000 | 30-180 days | Weekly/Monthly | Standard product |
| Quick Cash | Bullet | N5,000-N50,000 | 7-30 days | One-time | Single repayment |
| Nano Loan | Nano | N1,000-N5,000 | 14 days | One-time | Fallback for borderline applicants |

### 2.5 Risk Tiers and Pricing

17 risk tiers derived from ML model output:

| Tier Band | Tiers | Monthly Rate Range | Description |
|---|---|---|---|
| Super Prime | 1-3 | 3.0%-5.0% | Excellent credit, high income, repeat borrower |
| Prime | 4-7 | 5.0%-10.0% | Good credit, verified income |
| Near Prime | 8-11 | 10.0%-18.3% | Moderate risk, limited history |
| Subprime | 12-15 | 18.3%-25.0% | Higher risk, new borrowers |
| Deep Subprime | 16-17 | 25.0%-30.0% | Marginal, nano loans only |

Pricing formula: `final_rate = base_rate + risk_premium - ladder_discount`

### 2.6 Loan Ladder (Loyalty System)

| Tier | Name | Max Amount (Salary) | Rate Discount | Requirements |
|---|---|---|---|---|
| 1 | Bronze | N20,000 | 0% | New user |
| 2 | Silver | N50,000 | 1% | 1 loan repaid on time |
| 3 | Gold | N100,000 | 2% | 3 loans, 2 consecutive on-time |
| 4 | Platinum | N200,000 | 3% | 5 loans, 4 consecutive on-time |
| 5 | Diamond | N400,000 | 4% | 8 loans, 6 consecutive on-time |
| 6 | Elite | N700,000 | 5% | 12 loans, 10 consecutive on-time |
| 7 | Supreme | N1,000,000 | 6% | 18 loans, 15 consecutive on-time |

Max amounts are the same for all borrowers at each tier -- the ladder is the differentiator, not the borrower type.

### 2.7 Underwriting Approach

Sharp Sharp uses a **single underwriting path** for all borrowers. There is no persona-based routing, no IPPIS detection, no NYSC special handling. Every applicant goes through the same 14-step pipeline.

The loan ladder is how Sharp Sharp segments risk:
- **New users** start at Tier 1 with small amounts and higher rates
- **Repeat borrowers** who repay on time climb tiers, unlocking larger amounts and lower rates
- **The ladder IS the segmentation** -- it encodes repayment behaviour, not employment type

This is fundamentally different from external (which routes by employment persona) or external (which uses persona-specific scorecards). Sharp Sharp's intelligence is in the ladder progression and offer management (rescore dormant users, nudge via Customer.io), not in persona routing.

### 2.8 User Flows

#### Flow 1: First-Time Borrower (Happy Path)

```
Landing Page --> Sign Up (phone + password + name)
    --> KYC Onboarding (BVN + NIN entry)
    --> Selfie Capture (liveness check)
    --> Bank Linking (Mono Connect widget)
    --> Dashboard (show ladder tier, eligible amount)
    --> Apply for Loan (amount, tenure, purpose, bank account)
    --> Pipeline runs (5-60 seconds)
    --> Offer Displayed (amount, rate, schedule, expiry)
    --> Accept Offer
    --> Disbursement (Flutterwave transfer)
    --> Loan Active (dashboard shows schedule)
    --> Repay (manual or auto-debit)
    --> Loan Closed --> Ladder Promotion Check
```

#### Flow 2: Repeat Borrower

```
Login --> Dashboard (shows ladder tier, history)
    --> Apply (higher amounts available at loyalty tier)
    --> Pipeline runs (bureau check may be skipped at high tiers)
    --> Offer (lower rate due to ladder discount)
    --> Accept --> Disburse --> Repay
```

#### Flow 3: Rejection Path

```
Apply --> Pipeline runs --> Rejected
    --> Decline reason shown (affordability, bureau, fraud, ML score)
    --> If borderline: nano loan fallback offered
    --> If fraud knockoff: blocked, no retry
```

#### Flow 4: Admin Review

```
Admin Dashboard --> Review Queue (flagged applications)
    --> View application details + pipeline scores
    --> Approve / Reject with notes
    --> If approved: offer generated
```

### 2.9 Frontend Pages (All Implemented)

| Page | Route | Description |
|---|---|---|
| Landing | `/` | Hero with value props, login/signup CTAs |
| Sign Up | `/auth/signup` | Phone + name + password registration |
| Login | `/auth/login` | Phone + password authentication |
| KYC Onboarding | `/onboarding/kyc` | BVN + NIN entry + selfie upload |
| Bank Linking | `/onboarding/bank` | Mono Connect SDK integration |
| Dashboard | `/dashboard` | Loan history, active loans, ladder tier, apply CTA |
| Apply | `/apply` | Loan request form (amount, tenure, purpose, bank) |
| Application Status | `/applications/[id]` | Pipeline progress tracker |
| Offer Review | `/applications/[id]/offer` | Offer details + accept/decline |
| Loan Detail | `/loans/[id]` | Active loan info + repayment schedule |
| Repay | `/loans/[id]/repay` | Manual repayment initiation |
| Profile | `/profile` | Employment info, personal details |
| Admin | `/admin` | Portfolio overview, review queue, risk tiers |

### 2.10 API Endpoints (32 Total)

**Auth:** POST signup, POST login, POST refresh, POST otp/send, POST otp/verify
**Users:** GET me, POST kyc/submit, POST kyc/selfie, POST bank/link, GET bank/accounts, DELETE bank/{provider}, GET bank/config, PUT employment, GET ladder
**Applications:** GET list, POST create, GET {id}, GET {id}/offer, POST {id}/accept
**Loans:** GET list, GET active, GET {id}, GET {id}/schedule, POST {id}/repay, GET {id}/repayments
**Admin:** GET portfolio, GET review-queue, POST review/{id}, GET risk-tiers
**Webhooks:** POST flutterwave, POST mono
**System:** GET /health, GET /

### 2.11 External Integrations

| Integration | Purpose | Status |
|---|---|---|
| MetaMap | BVN, NIN, selfie liveness verification | Stub (needs API key) |
| Mono | Bank account linking + statement retrieval | Real client (v2 API), falls back to stub |
| Okra | Bank account linking (alternative) | Stub |
| Indicina | Bank statement analysis | Stub |
| CRC | Credit Bureau Nigeria (primary) | Stub |
| FirstCentral | Credit Bureau Nigeria (secondary) | Stub |
| CreditRegistry | Credit Bureau Nigeria (tertiary) | Stub |
| Flutterwave | Disbursement + repayment collection | Stub |
| Africa's Talking | SMS/voice notifications | Missing |
| CredoLab | Device SDK intelligence | Missing |

### 2.12 ML Models

Single LightGBM credit scoring model -- all borrowers go through one path. The loan ladder handles segmentation, not per-persona models.

| Model | Purpose | AUC | KS |
|---|---|---|---|
| credit_score_v1 | Universal credit scoring | 0.78 | 0.42 |

Note: The codebase currently has 5 persona-specific model artifacts from an earlier iteration that mixed in external patterns. These should be consolidated into a single model to match Sharp Sharp's actual approach.

Model is a JSON artifact loaded at service startup. Retrain via `python scripts/train_baseline.py`.

### 2.13 Data Model

Core tables (all PostgreSQL):

| Table | Purpose | Relationships |
|---|---|---|
| users | Borrower profiles, KYC, employment, ladder | Has many: applications, loans, devices, addresses |
| loan_products | Product definitions (amounts, rates, tenures) | Has many: applications |
| loan_applications | Pipeline tracking (14-step status) | Belongs to: user, product. Has one: offer, loan |
| loan_offers | Generated offers with pricing breakdown | Belongs to: application |
| loans | Active/closed loan records | Belongs to: user, application. Has many: repayments, schedule |
| loan_schedule | Repayment schedule entries | Belongs to: loan |
| loan_repayments | Individual payment transactions | Belongs to: loan |
| loan_ladder | Tier configuration (amounts, discounts) | -- |
| fraud_flags | Fraud detection results | Belongs to: user, application |
| ml_score_logs | ML model scoring audit trail | Belongs to: application |
| credit_bureau_reports | Bureau pull results | Belongs to: application |
| income_estimates | Income estimation snapshots | Belongs to: application |
| bank_statements | Linked bank statement data | Belongs to: user |
| bank_transactions | Individual bank transactions | Belongs to: statement |
| collection_assignments | Collections action tracking | Belongs to: loan |
| payment_transactions | Disbursement/repayment transactions | Belongs to: loan |
| integration_logs | External API call audit trail | -- |
| webhook_events | Incoming webhook processing | -- |

### 2.14 Non-Functional Requirements

| Requirement | Target |
|---|---|
| Pipeline latency (automated path) | < 60 seconds end-to-end |
| API response time (p95) | < 200ms for reads, < 2s for pipeline trigger |
| Concurrent users | 1,000+ (via async FastAPI + connection pooling) |
| Data encryption | TLS in transit, AES-256 at rest |
| Uptime | 99.5% (excluding maintenance) |
| Audit trail | All pipeline decisions, model scores, and bureau pulls logged |

---

## Part 3: Current State vs Target

### 3.1 What Is Built and Working

- Full backend API with 32 endpoints
- 14-step loan pipeline orchestrator
- 10 business services (~2,800 LOC of real logic)
- 5 production data models (~1,260 LOC)
- 5 trained ML models (synthetic data, persona-specific)
- ML scoring service with model loading and inference
- Next.js frontend with 13 pages covering full borrower journey
- Admin panel with portfolio overview and review queue
- Docker Compose stack (Postgres, Redis, Backend, ML, Frontend, Celery)
- API client with JWT auth, interceptors, and token refresh
- Mono bank linking integration (real v2 API client)
- Capacitor mobile app scaffolding (iOS + Android)

### 3.2 What Is Stubbed

- All external integrations except Mono (return mock data)
- Celery workers (task files exist, jobs not implemented)
- Feature store (inline in scoring service, not Redis-backed)
- Credit bureau pulls (orchestration real, API calls mocked)
- Disbursement (Flutterwave transfer logic real, API mocked)
- Collections engine (DPD buckets defined, no SMS/voice actions)
- ML model monitoring (PSI/KS tracking code exists, no dashboard)

### 3.3 What Is Missing

- Alembic migration files (using AUTO_CREATE_TABLES for dev)
- Test suite (pytest structure exists, no tests)
- Kubernetes manifests / Terraform (empty directories)
- Webhook handlers for Flutterwave repayment callbacks
- Repayment reconciliation engine
- SMS/notification service
- OTP verification flow
- Graph DB fraud detection (single-applicant only)
- USSD channel

### 3.4 Roadmap (Priority Order)

| Phase | Items | Effort |
|---|---|---|
| **Demo Ready** | Fix model-service mismatches [DONE], seed demo data, end-to-end walkthrough | 1 day |
| **Integration Sandbox** | Mono + Flutterwave sandbox credentials, real bureau sandbox | 1 week |
| **Production Prep** | Alembic migrations, pytest suite, CI/CD pipeline | 2 weeks |
| **Collections** | DPD bucketing job, SMS templates, escalation rules | 1 week |
| **Mobile** | Fix Capacitor config (standalone vs export), app store prep | 1 week |
| **Scale** | K8s deployment, Terraform, monitoring dashboards | 2 weeks |

---

## Part 4: Technical Specifications

### 4.1 Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Backend API | FastAPI (Python) | 3.11 |
| ORM | SQLAlchemy (async) | 2.0.31 |
| Database | PostgreSQL | 16 |
| Cache/Queue | Redis | 7 |
| Task Queue | Celery | 5.4.0 |
| ML Framework | LightGBM | Latest |
| Frontend | Next.js (TypeScript) | 14.2 |
| UI | Tailwind CSS | 3.4 |
| State Management | Zustand | 4.5 |
| Mobile | Capacitor | 8.3 |
| Containerization | Docker + Docker Compose | Latest |
| Auth | JWT (HS256) | -- |

### 4.2 Running the Platform

```bash
# From /Users/kabel/Projects/sharp-sharp/

# Start infrastructure
docker compose up -d postgres redis

# Start backend (port 8000)
docker compose up -d backend --build

# Start ML service (port 8001)
docker compose up -d ml-service --build

# Start frontend (port 3000) -- native for faster dev
cd frontend && npm install && npx next dev

# Or run everything in Docker
docker compose up -d
```

**Endpoints:**
- Frontend: http://localhost:3000
- Backend API + Swagger: http://localhost:8000/docs
- ML Service: http://localhost:8001/docs
- PostgreSQL: localhost:5433 (user: sharpsharp, pass: sharpsharp_dev, db: sharpsharp_lending)

### 4.3 Configuration

All config via environment variables (see `backend/app/core/config.py`). Key settings:
- `DATABASE_URL` -- PostgreSQL connection string
- `REDIS_URL` -- Redis connection string
- `ML_SERVICE_URL` -- ML scoring service URL
- `JWT_SECRET_KEY` -- JWT signing secret
- `MONO_SECRET_KEY` / `MONO_PUBLIC_KEY` -- Mono bank linking
- `FLUTTERWAVE_SECRET_KEY` -- Disbursement
- `AUTO_CREATE_TABLES` -- Bootstrap tables without Alembic (dev only)

---

**Document version:** 1.0
**Next review:** After integration sandbox phase
