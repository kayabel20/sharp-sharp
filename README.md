# Sharp Sharp -- Automated Lending Platform

A production-grade digital lending platform for Nigeria. Unsecured personal loans from N5,000 to N1,000,000 with automated underwriting, ML credit scoring, and a 7-tier loyalty ladder.

## Live Simulation

**[Try the interactive app simulation](https://kayabel20.github.io/sharp-sharp/simulation/)**

Click through the full borrower journey: signup, KYC, loan application, real-time pipeline scoring, offer review, disbursement, repayment, and ladder promotion.

## Architecture

```
sharp-sharp/
  backend/           FastAPI backend (Python 3.11, async SQLAlchemy)
  ml-service/         ML scoring microservice (LightGBM)
  frontend/           Next.js 14 customer app + admin dashboard
  simulation/         Interactive HTML app simulation (GitHub Pages)
  docs/               BRD/PRD, architecture, flow diagrams
  infra/              Docker, K8s, Terraform configs
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python 3.11+), async SQLAlchemy 2.0 |
| Database | PostgreSQL 16 |
| Cache/Queue | Redis 7, Celery 5.4 |
| ML | LightGBM (single model, all borrowers) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Mobile | Capacitor (iOS + Android shells) |
| Auth | JWT (HS256) |
| Containers | Docker + Docker Compose |

## The 14-Step Decisioning Pipeline

Every borrower goes through a single underwriting path:

1. **Application** -- phone signup, basic PII
2. **KYC Wall** -- BVN + NIN + selfie liveness
3. **Tier Check** -- loan ladder eligibility gate
4. **Data Collection** -- employment, income, NOK
5. **Fraud Detection** -- device fingerprint + graph network analysis
6. **Bank Statement** -- Mono/Okra account linking + statement analysis
7. **Income Estimation** -- income model from bank transaction patterns
8. **Feature Engineering** -- 35-feature vector
9. **Credit Scoring** -- single LightGBM model (AUC 0.80, KS 0.49)
10. **Risk Tier Classification** -- risk tier from model output
11. **Credit Bureau** -- CRC + FirstCentral + CreditRegistry
12. **Ladder-Based Pricing** -- rate = base_rate + risk_premium - ladder_discount
13. **Loan Offer** -- dynamic offer with schedule and nano fallback
14. **Monitoring** -- PSI/AUC/KS drift tracking

## The Loan Ladder

The ladder is the primary segmentation mechanism. No persona routing -- repayment history is the differentiator.

| Tier | Name | Max Amount | Rate Discount |
|------|------|-----------|--------------|
| 1 | Bronze | N20,000 | 0% |
| 2 | Silver | N50,000 | 0.5% |
| 3 | Gold | N100,000 | 1.0% |
| 4 | Platinum | N200,000 | 1.5% |
| 5 | Diamond | N400,000 | 2.0% |
| 6 | Elite | N700,000 | 2.5% |
| 7 | Supreme | N1,000,000 | 3.0% |

## Quick Start

```bash
# Start the full stack
docker compose up -d

# Backend API + Swagger:  http://localhost:8000/docs
# ML Service:             http://localhost:8001/docs
# Frontend:               http://localhost:3000
# PostgreSQL:             localhost:5433
```

Or run the frontend natively for faster dev:

```bash
cd frontend && npm install && npx next dev
```

## API Endpoints (32)

- **Auth:** signup, login, refresh, OTP send/verify
- **Users:** profile, KYC submit, selfie, bank link/unlink, employment, ladder
- **Applications:** list, create, get, offer, accept
- **Loans:** list, active, detail, schedule, repay, repayments
- **Admin:** portfolio, review queue, review decision, risk tiers
- **Webhooks:** Flutterwave, Mono

## External Integrations

| Service | Purpose | Status |
|---------|---------|--------|
| Mono | Bank account linking + statements | Real v2 client (falls back to stub) |
| MetaMap | KYC (BVN, NIN, selfie) | Stub |
| CRC | Credit Bureau Nigeria | Stub |
| FirstCentral | Credit Bureau Nigeria | Stub |
| CreditRegistry | Credit Bureau Nigeria | Stub |
| Flutterwave | Disbursement + repayment | Stub |
| Okra | Bank data (alternative) | Stub |
| Indicina | Bank statement analysis | Stub |
| Africa's Talking | SMS/voice | Missing |

## Documentation

- [BRD & PRD](docs/BRD_PRD.md) -- business requirements, product spec, data model, roadmap
- [Architecture](docs/ARCHITECTURE.md) -- system design, pipeline flow, honest gaps assessment
- [Flow Diagram](docs/FLOW_DIAGRAM.md) -- Mermaid sequence diagrams

## White Labelling

This platform is designed to be white-labelled. To rebrand:

1. Update `backend/app/core/config.py` -- `APP_NAME`
2. Update `frontend/src/app/layout.tsx` -- title and metadata
3. Update `frontend/src/app/page.tsx` -- landing page copy
4. Update `frontend/capacitor.config.ts` -- `appId` and `appName`
5. Update `frontend/public/manifest.json` -- PWA name
6. Replace `frontend/public/*.png` icons
7. Update `frontend/tailwind.config.ts` -- brand colors

## License

Proprietary. All rights reserved.
