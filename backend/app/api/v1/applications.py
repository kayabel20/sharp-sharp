"""Loan application endpoints — submit, track, accept offer."""
import logging
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.loan import LoanApplication, ApplicationStatus, LoanOffer
from app.api.deps import get_current_user
from app.services.loan_pipeline import LoanPipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/applications", tags=["Loan Applications"])


# ── Schemas ──

class ApplicationRequest(BaseModel):
    requested_amount: float
    requested_tenure_days: int = 30
    loan_purpose: str | None = None
    disbursement_account_number: str
    disbursement_bank_code: str


class ApplicationResponse(BaseModel):
    id: str
    status: str
    requested_amount: float
    requested_tenure_days: int
    current_step: str | None = None
    created_at: str


class ApplicationDetailResponse(ApplicationResponse):
    ml_score: float | None = None
    risk_tier: int | None = None
    fraud_composite_score: float | None = None
    income_estimate: float | None = None
    bureau_score: float | None = None
    decline_reason: str | None = None
    decline_details: str | None = None
    offer_id: str | None = None


class AcceptOfferRequest(BaseModel):
    offer_id: str


class OfferResponse(BaseModel):
    id: str
    approved_amount: float
    tenure_days: int
    interest_rate_monthly: float
    total_repayment: float
    installment_amount: float
    repayment_frequency: str
    risk_tier_name: str | None = None
    first_repayment_date: str | None = None
    expires_at: str


# ── Endpoints ──

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def submit_application(
    req: ApplicationRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a new loan application and trigger the decisioning pipeline."""

    # Check for existing active application
    existing = await db.execute(
        select(LoanApplication).where(
            LoanApplication.user_id == user.id,
            LoanApplication.status.notin_([
                ApplicationStatus.REJECTED,
                ApplicationStatus.DISBURSED,
                ApplicationStatus.EXPIRED,
                ApplicationStatus.CANCELLED,
                ApplicationStatus.OFFER_DECLINED,
            ]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an active loan application",
        )

    # Validate amount against tier limits
    tier = user.tier.value if user.tier else "tier_1"
    if tier in ("tier_1", "tier_2") and req.requested_amount > 200_000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tier upgrade required for loans above ₦200,000",
        )

    # Create application
    application = LoanApplication(
        user_id=user.id,
        requested_amount=req.requested_amount,
        requested_tenure_days=req.requested_tenure_days,
        loan_purpose=req.loan_purpose,
        disbursement_account_number=req.disbursement_account_number,
        disbursement_bank_code=req.disbursement_bank_code,
        status=ApplicationStatus.KYC_PENDING,
        current_step="submitted",
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)

    # Run pipeline in background
    background_tasks.add_task(_run_pipeline, str(application.id))

    logger.info(f"Application submitted: {application.id} by user {user.id}")

    return {
        "id": str(application.id),
        "status": "submitted",
        "message": "Application received. Processing will begin shortly.",
    }


@router.get("/", response_model=list[ApplicationResponse])
async def list_applications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all loan applications for current user."""
    result = await db.execute(
        select(LoanApplication)
        .where(LoanApplication.user_id == user.id)
        .order_by(LoanApplication.created_at.desc())
    )
    apps = result.scalars().all()

    return [
        ApplicationResponse(
            id=str(a.id),
            status=a.status.value,
            requested_amount=a.requested_amount,
            requested_tenure_days=a.requested_tenure_days,
            current_step=a.current_step,
            created_at=str(a.created_at),
        )
        for a in apps
    ]


@router.get("/{application_id}", response_model=ApplicationDetailResponse)
async def get_application(
    application_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed application status."""
    result = await db.execute(
        select(LoanApplication).where(
            LoanApplication.id == application_id,
            LoanApplication.user_id == user.id,
        )
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Get offer if exists
    offer_result = await db.execute(
        select(LoanOffer).where(LoanOffer.application_id == app.id)
    )
    offer = offer_result.scalar_one_or_none()

    return ApplicationDetailResponse(
        id=str(app.id),
        status=app.status.value,
        requested_amount=app.requested_amount,
        requested_tenure_days=app.requested_tenure_days,
        current_step=app.current_step,
        created_at=str(app.created_at),
        ml_score=app.ml_score,
        risk_tier=app.risk_tier,
        fraud_composite_score=app.fraud_composite_score,
        income_estimate=app.income_estimate,
        bureau_score=app.bureau_score,
        decline_reason=app.decline_reason.value if app.decline_reason else None,
        decline_details=app.decline_details,
        offer_id=str(offer.id) if offer else None,
    )


@router.get("/{application_id}/offer", response_model=OfferResponse)
async def get_offer(
    application_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the loan offer for an application."""
    result = await db.execute(
        select(LoanOffer).where(
            LoanOffer.application_id == application_id,
            LoanOffer.user_id == user.id,
        )
    )
    offer = result.scalar_one_or_none()
    if not offer:
        raise HTTPException(status_code=404, detail="No offer found for this application")

    return OfferResponse(
        id=str(offer.id),
        approved_amount=offer.approved_amount,
        tenure_days=offer.tenure_days,
        interest_rate_monthly=offer.interest_rate_monthly,
        total_repayment=offer.total_repayment,
        installment_amount=offer.installment_amount,
        repayment_frequency=offer.repayment_frequency.value,
        risk_tier_name=offer.risk_tier_name,
        first_repayment_date=str(offer.first_repayment_date) if offer.first_repayment_date else None,
        expires_at=str(offer.expires_at),
    )


@router.post("/{application_id}/accept")
async def accept_offer(
    application_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a loan offer and trigger disbursement."""
    # Get offer
    result = await db.execute(
        select(LoanOffer).where(
            LoanOffer.application_id == application_id,
            LoanOffer.user_id == user.id,
        )
    )
    offer = result.scalar_one_or_none()
    if not offer:
        raise HTTPException(status_code=404, detail="No offer found")

    if offer.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Offer has expired")

    if offer.is_accepted:
        raise HTTPException(status_code=400, detail="Offer already accepted")

    pipeline = LoanPipeline(db)
    disbursement_result = await pipeline.accept_offer(offer.id, user.id)

    return disbursement_result


# ── Background Tasks ──

async def _run_pipeline(application_id: str):
    """Run the loan pipeline in background."""
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        try:
            pipeline = LoanPipeline(db)
            result = await pipeline.process_application(UUID(application_id))
            logger.info(f"Pipeline completed for {application_id}: {result.get('status')}")
        except Exception as e:
            logger.error(f"Pipeline failed for {application_id}: {e}", exc_info=True)
