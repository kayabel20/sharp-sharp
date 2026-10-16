# Sharp Sharp Lending Platform — Flow Diagrams

Companion to `ARCHITECTURE.md`. Standalone diagrams for whiteboarding/decks.

---

## 1. End-to-end borrower journey (happy path)

```mermaid
flowchart TD
    A[1. Sign up<br/>phone + OTP] --> B[2. KYC<br/>BVN + NIN + selfie]
    B --> C{Tier?}
    C -->|Tier 1/2| D[3. Loan request<br/>amount + tenure]
    C -->|Need Tier 3| C1[Address verification] --> D
    D --> E[4. Data collection<br/>employment, NOK, income]
    E --> F[5. Bank link<br/>Mono / Okra widget]
    F --> G[Submit application]
    G --> H[6. Fraud check L1+L2]
    H --> I[7. Bank statement<br/>analysis]
    I --> J[8. Income estimate<br/>+ DTI affordability]
    J --> K[9. Feature engineering]
    K --> L[10. ML credit scoring]
    L --> M[11. Risk tier 1-17]
    M --> N[12. Bureau check<br/>CRC + FirstCentral + CR]
    N --> O[13. Risk-based pricing]
    O --> P[14. Loan offer]
    P --> Q{Borrower<br/>accepts?}
    Q -->|Yes| R[Disbursement<br/>via Flutterwave]
    Q -->|No| S[Offer declined]
    R --> T[Active loan +<br/>repayment schedule]
    T --> U[Monitoring<br/>DPD bucketing<br/>collections]
```

---

## 2. Decision points & rejection paths

```mermaid
flowchart LR
    Start([Application]) --> KYC{KYC pass?}
    KYC -->|No| RJ1[Reject:<br/>POLICY_VIOLATION]
    KYC -->|Yes| Tier{Tier OK<br/>for amount?}
    Tier -->|No| Up[Prompt: tier upgrade]
    Tier -->|Yes| Fraud{Fraud<br/>composite OK?}
    Fraud -->|Knockoff| RJ2[Reject:<br/>FRAUD_KNOCKOFF]
    Fraud -->|Pass| Bank[Bank analysis]
    Bank --> Inc{Affordability<br/>passes?}
    Inc -->|No| RJ3[Reject:<br/>INCOME_INSUFFICIENT]
    Inc -->|Yes| ML{ML score<br/>≥ cutoff?}
    ML -->|No| RJ4[Reject:<br/>ML_SCORE_LOW]
    ML -->|Yes| Bur{Bureau<br/>cutoff OK?}
    Bur -->|No| RJ5[Reject:<br/>BUREAU_CUTOFF]
    Bur -->|Yes| Edge{Edge case<br/>or anomaly?}
    Edge -->|Yes| HR[Human review]
    Edge -->|No| Off[Offer generated]
    HR -->|Approve| Off
    HR -->|Reject| RJ6[Reject:<br/>POLICY_VIOLATION]
    Off --> Done([Wait for accept])
```

---

## 3. Loan lifecycle (after disbursement)

```mermaid
stateDiagram-v2
    [*] --> ACTIVE: disbursed
    ACTIVE --> CURRENT: 1st payment on time
    CURRENT --> CURRENT: payments on time
    CURRENT --> DELINQUENT_7: 1-7 DPD
    DELINQUENT_7 --> DELINQUENT_15: 8-15 DPD
    DELINQUENT_15 --> DELINQUENT_30: 16-30 DPD
    DELINQUENT_30 --> DELINQUENT_60: 31-60 DPD
    DELINQUENT_60 --> DELINQUENT_90: 61-90 DPD
    DELINQUENT_90 --> DEFAULT: 90+ DPD
    DEFAULT --> WRITTEN_OFF: 180+ DPD
    DEFAULT --> RESTRUCTURED: workout
    DELINQUENT_7 --> CURRENT: caught up
    DELINQUENT_15 --> CURRENT: caught up
    DELINQUENT_30 --> CURRENT: caught up
    CURRENT --> PAID_OFF: final payment
    PAID_OFF --> [*]
    WRITTEN_OFF --> [*]
```

---

## 4. Component & data ownership

```mermaid
flowchart TB
    subgraph Frontend [Next.js Frontend]
        FA[Apply page]
        FK[KYC pages — MISSING]
        FB[Bank link — MISSING]
        FO[Offer accept — MISSING]
        FD[Dashboard]
        FAdmin[Admin]
    end

    subgraph Backend [FastAPI Backend]
        Auth[auth/users]
        Apps[applications]
        Loans[loans]
        Admin[admin]
        Hooks[webhooks]
        Pipe[loan_pipeline.py]
        KS[kyc_service]
        FS[fraud_service]
        BS[bank_service]
        IS[income_service]
        SS[scoring_service]
        BuS[bureau_service]
        PS[pricing_service]
        OS[offer_service]
        DS[disbursement_service]
    end

    subgraph ML [ML service :8001]
        Engine[scoring_engine]
        Mon[monitoring]
    end

    subgraph DB [Postgres]
        UM[(users)]
        AM[(applications)]
        OM[(offers)]
        LM[(loans)]
        RM[(repayments)]
        FM[(fraud_flags)]
    end

    subgraph Ext [External — all STUB]
        MM[MetaMap]
        Mono[Mono]
        Ind[Indicina]
        Bur[CRC/FC/CR]
        FW[Flutterwave]
    end

    Frontend --> Auth
    Frontend --> Apps
    Frontend --> Loans
    Apps --> Pipe
    Pipe --> KS --> MM
    Pipe --> FS
    Pipe --> BS --> Mono
    BS --> Ind
    Pipe --> IS
    Pipe --> SS --> Engine
    Pipe --> BuS --> Bur
    Pipe --> PS
    Pipe --> OS
    Loans --> DS --> FW
    Pipe --> DB
    Engine --> Mon
```

---

## 5. Reality heatmap

```mermaid
%%{init: {'theme':'base'}}%%
pie showData
    title "Code coverage by status (file-level estimate)"
    "BUILT (real logic)" : 45
    "STUB (mocks/scaffolds)" : 35
    "MISSING (not in repo)" : 20
```

Use this when discussing scope honestly — about half the platform is real, a third is scaffolded with mock returns, and a fifth is absent.
