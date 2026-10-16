"""Admin endpoints — application review, portfolio analytics, risk management."""
import logging
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.user import User
from app.models.loan import (
    LoanApplication, ApplicationStatus, LoanOffer, Loan, LoanStatus
)
from app.models.risk import MLScore, FraudScore
from app.api.deps import get_admin_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Schemas ──

class PortfolioStats(BaseModel):
    total_applications: int
    approved_count: int
    rejected_count: int
    pending_review_count: int
    total_disbursed_amount: float
    total_outstanding: float
    active_loans: int
    delinquent_loans: int
    default_rate: float
    average_ml_score: float | None


class ApplicationReview(BaseModel):
    id: str
    user_name: str
    phone: str
    requested_amount: float
    ml_score: float | None
    fraud_score: float | None
    income_estimate: float | None
    bureau_score: float | None
    status: str
    current_step: str | None
    submitted_at: str


class ReviewDecision(BaseModel):
    decision: str  # "approve" or "reject"
    reason: str | None = None


# ── Endpoints ──

@router.get("/portfolio", response_model=PortfolioStats)
async def portfolio_overview(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get portfolio-level analytics."""
    # Application counts
    total = await db.scalar(select(func.count(LoanApplication.id)))
    approved = await db.scalar(
        select(func.count(LoanApplication.id)).where(
            LoanApplication.status.in_([
                ApplicationStatus.OFFER_GENERATED,
                ApplicationStatus.OFFER_ACCEPTED,
                ApplicationStatus.DISBURSED,
            ])
        )
    )
    rejected = await db.scalar(
        select(func.count(LoanApplication.id)).where(
            LoanApplication.status == ApplicationStatus.REJECTED
        )
    )
    pending_review = await db.scalar(
        select(func.count(LoanApplication.id)).where(
            LoanApplication.status == ApplicationStatus.HUMAN_REVIEW
        )
    )

    # Loan portfolio
    active_loans = await db.scalar(
        select(func.count(Loan.id)).where(Loan.status == LoanStatus.ACTIVE)
    )
    delinquent = await db.scalar(
        select(func.count(Loan.id)).where(
            Loan.status.in_([
                LoanStatus.DELINQUENT_7, LoanStatus.DELINQUENT_15,
                LoanStatus.DELINQUENT_30, LoanStatus.DELINQUENT_60,
                LoanStatus.DELINQUENT_90,
            ])
        )
    )
    total_disbursed = await db.scalar(
        select(func.sum(Loan.principal_amount))
    ) or 0
    total_outstanding = await db.scalar(
        select(func.sum(Loan.total_outstanding)).where(
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.DELINQUENT_7,
                             LoanStatus.DELINQUENT_15, LoanStatus.DELINQUENT_30])
        )
    ) or 0

    total_loan_count = await db.scalar(select(func.count(Loan.id))) or 1
    default_count = await db.scalar(
        select(func.count(Loan.id)).where(Loan.status == LoanStatus.DEFAULT)
    ) or 0

    avg_score = await db.scalar(select(func.avg(MLScore.credit_score)))

    return PortfolioStats(
        total_applications=total or 0,
        approved_count=approved or 0,
        rejected_count=rejected or 0,
        pending_review_count=pending_review or 0,
        total_disbursed_amount=float(total_disbursed),
        total_outstanding=float(total_outstanding),
        active_loans=active_loans or 0,
        delinquent_loans=delinquent or 0,
        default_rate=default_count / total_loan_count if total_loan_count else 0,
        average_ml_score=float(avg_score) if avg_score else None,
    )


@router.get("/review-queue", response_model=list[ApplicationReview])
async def review_queue(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200),
):
    """Get applications pending human review."""
    result = await db.execute(
        select(LoanApplication)
        .where(LoanApplication.status == ApplicationStatus.HUMAN_REVIEW)
        .order_by(LoanApplication.created_at)
        .limit(limit)
    )
    apps = result.scalars().all()

    reviews = []
    for app in apps:
        user = await db.get(User, app.user_id)
        reviews.append(ApplicationReview(
            id=str(app.id),
            user_name=f"{user.first_name} {user.last_name}" if user else "Unknown",
            phone=user.phone_number if user else "",
            requested_amount=app.requested_amount,
            ml_score=app.ml_score,
            fraud_score=app.fraud_composite_score,
            income_estimate=app.income_estimate,
            bureau_score=app.bureau_score,
            status=app.status.value,
            current_step=app.current_step,
            submitted_at=str(app.created_at),
        ))

    return reviews


@router.post("/review/{application_id}")
async def review_application(
    application_id: UUID,
    decision: ReviewDecision,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject an application in manual review."""
    app = await db.get(LoanApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status != ApplicationStatus.HUMAN_REVIEW:
        raise HTTPException(status_code=400, detail="Application not in review queue")

    if decision.decision == "approve":
        app.status = ApplicationStatus.OFFER_GENERATED
        app.reviewer_id = admin.id
        app.reviewed_at = datetime.utcnow()
        app.review_notes = decision.reason

        await db.commit()
        return {"status": "approved", "application_id": str(application_id)}

    elif decision.decision == "reject":
        app.status = ApplicationStatus.REJECTED
        app.decline_details = decision.reason or "Rejected during manual review"
        app.reviewer_id = admin.id
        app.reviewed_at = datetime.utcnow()
        app.review_notes = decision.reason

        await db.commit()
        return {"status": "rejected", "application_id": str(application_id)}

    raise HTTPException(status_code=400, detail="Decision must be 'approve' or 'reject'")


@router.get("/risk-tiers")
async def list_risk_tiers(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all risk tier configurations."""
    from app.models.risk import RiskTier

    result = await db.execute(
        select(RiskTier).where(RiskTier.is_active == True).order_by(RiskTier.tier_number)
    )
    tiers = result.scalars().all()

    return [
        {
            "tier_number": t.tier_number,
            "tier_name": t.tier_name,
            "min_score": t.min_score,
            "max_score": t.max_score,
            "interest_rate_monthly": t.interest_rate_monthly,
            "expected_npl_rate": t.expected_npl_rate,
            "max_loan_amount": t.max_loan_amount,
            "max_tenure_days": t.max_tenure_days,
            "auto_approve": t.auto_approve,
        }
        for t in tiers
    ]
