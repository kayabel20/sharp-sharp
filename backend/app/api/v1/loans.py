"""Loan management endpoints — active loans, schedule, repayment history."""
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.loan import Loan, LoanSchedule, LoanRepayment, LoanStatus
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/loans", tags=["Loans"])


# ── Schemas ──

class LoanSummary(BaseModel):
    id: str
    principal_amount: float
    total_amount_due: float
    total_outstanding: float
    status: str
    tenure_days: int
    disbursement_date: str | None
    maturity_date: str | None
    days_past_due: int


class LoanDetail(LoanSummary):
    interest_amount: float
    processing_fee: float
    interest_rate_monthly: float
    repayment_frequency: str
    outstanding_principal: float
    outstanding_interest: float
    outstanding_fees: float
    total_paid: float
    risk_tier: int | None
    ml_score_at_disbursement: float | None
    ladder_tier_at_disbursement: int | None


class ScheduleItem(BaseModel):
    installment_number: int
    due_date: str
    total_due: float
    principal_due: float
    interest_due: float
    amount_paid: float
    is_paid: bool


class RepaymentItem(BaseModel):
    id: str
    amount: float
    payment_date: str
    payment_method: str | None
    reference: str | None
    status: str


# ── Endpoints ──

@router.get("/", response_model=list[LoanSummary])
async def list_loans(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all loans for current user."""
    result = await db.execute(
        select(Loan)
        .where(Loan.user_id == user.id)
        .order_by(Loan.created_at.desc())
    )
    loans = result.scalars().all()

    return [
        LoanSummary(
            id=str(loan.id),
            principal_amount=loan.principal_amount,
            total_amount_due=loan.total_amount_due,
            total_outstanding=loan.total_outstanding,
            status=loan.status.value,
            tenure_days=loan.tenure_days,
            disbursement_date=str(loan.disbursement_date) if loan.disbursement_date else None,
            maturity_date=str(loan.maturity_date) if loan.maturity_date else None,
            days_past_due=loan.days_past_due or 0,
        )
        for loan in loans
    ]


@router.get("/active", response_model=LoanDetail | None)
async def get_active_loan(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current active loan (if any)."""
    result = await db.execute(
        select(Loan).where(
            Loan.user_id == user.id,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.DELINQUENT_7,
                             LoanStatus.DELINQUENT_15, LoanStatus.DELINQUENT_30]),
        )
    )
    loan = result.scalar_one_or_none()
    if not loan:
        return None

    return _loan_detail(loan)


@router.get("/{loan_id}", response_model=LoanDetail)
async def get_loan(
    loan_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get loan details."""
    result = await db.execute(
        select(Loan).where(Loan.id == loan_id, Loan.user_id == user.id)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    return _loan_detail(loan)


@router.get("/{loan_id}/schedule", response_model=list[ScheduleItem])
async def get_schedule(
    loan_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get repayment schedule for a loan."""
    # Verify ownership
    loan = await db.execute(
        select(Loan).where(Loan.id == loan_id, Loan.user_id == user.id)
    )
    if not loan.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Loan not found")

    result = await db.execute(
        select(LoanSchedule)
        .where(LoanSchedule.loan_id == loan_id)
        .order_by(LoanSchedule.installment_number)
    )
    items = result.scalars().all()

    return [
        ScheduleItem(
            installment_number=s.installment_number,
            due_date=str(s.due_date),
            total_due=s.total_due,
            principal_due=s.principal_due,
            interest_due=s.interest_due,
            amount_paid=s.amount_paid or 0,
            is_paid=s.is_paid or False,
        )
        for s in items
    ]


@router.post("/{loan_id}/repay")
async def initiate_repayment(
    loan_id: UUID,
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate a repayment via Flutterwave (STUB).

    In production this calls Flutterwave to charge the borrower's account
    and returns a redirect / payment link. Here it just records intent.
    """
    amount = float(payload.get("amount", 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")

    result = await db.execute(
        select(Loan).where(Loan.id == loan_id, Loan.user_id == user.id)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    if amount > loan.total_outstanding:
        raise HTTPException(status_code=400, detail="amount exceeds outstanding")

    logger.info(f"Repayment initiated for loan {loan_id}: amount={amount} (STUB)")
    return {
        "status": "initiated",
        "loan_id": str(loan_id),
        "amount": amount,
        "reference": f"STUB-{loan_id.hex[:12]}",
        "redirect_url": None,
        "note": "Stubbed — wire Flutterwave Standard checkout in production",
    }


@router.get("/{loan_id}/repayments", response_model=list[RepaymentItem])
async def get_repayments(
    loan_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get repayment history for a loan."""
    loan = await db.execute(
        select(Loan).where(Loan.id == loan_id, Loan.user_id == user.id)
    )
    if not loan.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Loan not found")

    result = await db.execute(
        select(LoanRepayment)
        .where(LoanRepayment.loan_id == loan_id)
        .order_by(LoanRepayment.payment_date.desc())
    )
    repayments = result.scalars().all()

    return [
        RepaymentItem(
            id=str(r.id),
            amount=r.amount,
            payment_date=str(r.payment_date),
            payment_method=r.payment_method,
            reference=r.reference,
            status=r.status,
        )
        for r in repayments
    ]


def _loan_detail(loan: Loan) -> LoanDetail:
    return LoanDetail(
        id=str(loan.id),
        principal_amount=loan.principal_amount,
        total_amount_due=loan.total_amount_due,
        total_outstanding=loan.total_outstanding,
        status=loan.status.value,
        tenure_days=loan.tenure_days,
        disbursement_date=str(loan.disbursement_date) if loan.disbursement_date else None,
        maturity_date=str(loan.maturity_date) if loan.maturity_date else None,
        days_past_due=loan.days_past_due or 0,
        interest_amount=loan.interest_amount,
        processing_fee=loan.processing_fee or 0,
        interest_rate_monthly=loan.interest_rate_monthly,
        repayment_frequency=loan.repayment_frequency.value if loan.repayment_frequency else "one_time",
        outstanding_principal=loan.outstanding_principal,
        outstanding_interest=loan.outstanding_interest,
        outstanding_fees=loan.outstanding_fees or 0,
        total_paid=loan.total_paid or 0,
        risk_tier=loan.risk_tier,
        ml_score_at_disbursement=loan.ml_score_at_disbursement,
        ladder_tier_at_disbursement=loan.ladder_tier_at_disbursement,
    )
