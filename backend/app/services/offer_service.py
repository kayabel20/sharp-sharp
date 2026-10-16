"""Offer generation service — creates loan offers with repayment schedules."""
import logging
from datetime import datetime, timedelta, date as date_type
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.loan import (
    LoanApplication, LoanOffer, LoanSchedule, Loan,
    LoanType, RepaymentFrequency
)

logger = logging.getLogger(__name__)

# Offer validity window
OFFER_VALIDITY_HOURS = 72  # 3 days


class OfferService:
    """
    Generates loan offers with pricing, tenure, and repayment schedules.
    Supports:
    - Bullet loans (single repayment)
    - Installment loans (weekly/bi-weekly/monthly)
    - Nano loans (small fallback loans for borderline cases)
    """

    # Nano loan config (CDL innovation — fallback for below-minimum)
    NANO_LOAN_AMOUNT = 5_000
    NANO_LOAN_TENURE = 14
    NANO_LOAN_RATE = 0.10

    # Minimum loan thresholds
    MIN_LOAN_AMOUNT = 5_000
    MIN_TENURE_DAYS = 7

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate(self, application: LoanApplication, user: User,
                       pricing: dict, income: dict) -> LoanOffer:
        """Generate a loan offer based on pricing engine output."""

        approved_amount = pricing["approved_amount"]
        tenure_days = pricing["tenure_days"]

        # Check for Nano loan fallback
        if approved_amount < self.MIN_LOAN_AMOUNT and approved_amount > 0:
            return await self._generate_nano_offer(application, user)

        if approved_amount <= 0:
            # Edge case: no amount approved but somehow made it here
            return await self._generate_nano_offer(application, user)

        # Determine loan type
        if tenure_days <= 30:
            loan_type = LoanType.BULLET
            repayment_frequency = RepaymentFrequency.ONE_TIME
        elif tenure_days <= 90:
            loan_type = LoanType.INSTALLMENT
            repayment_frequency = RepaymentFrequency.WEEKLY
        else:
            loan_type = LoanType.INSTALLMENT
            repayment_frequency = RepaymentFrequency.MONTHLY

        # Calculate installment amount
        total_repayment = pricing["total_repayment"]
        num_installments = self._calculate_installments(tenure_days, repayment_frequency)
        installment_amount = total_repayment / max(num_installments, 1)

        # First repayment date
        first_repayment = self._first_repayment_date(repayment_frequency)

        offer = LoanOffer(
            application_id=application.id,
            user_id=user.id,
            loan_type=loan_type,
            approved_amount=round(approved_amount, 2),
            tenure_days=tenure_days,
            interest_rate_monthly=pricing["final_rate_monthly"],
            annual_rate=pricing["annual_rate"],
            base_rate=pricing["base_rate_monthly"],
            risk_premium=pricing["risk_premium"],
            persona_adjustment=pricing["persona_adjustment"],
            ladder_discount=pricing["ladder_discount"],
            total_interest=round(pricing["total_interest"], 2),
            processing_fee=round(pricing["processing_fee"], 2),
            total_repayment=round(total_repayment, 2),
            repayment_frequency=repayment_frequency,
            number_of_installments=num_installments,
            installment_amount=round(installment_amount, 2),
            first_repayment_date=first_repayment,
            risk_tier=pricing.get("risk_tier"),
            risk_tier_name=pricing.get("risk_tier_name"),
            expires_at=datetime.utcnow() + timedelta(hours=OFFER_VALIDITY_HOURS),
            is_nano=False,
        )
        self.db.add(offer)
        await self.db.flush()

        logger.info(
            f"Offer generated: {offer.id} — ₦{approved_amount:,.0f} "
            f"at {pricing['final_rate_monthly']*100:.1f}%/mo for {tenure_days}d"
        )

        return offer

    async def _generate_nano_offer(self, application: LoanApplication,
                                    user: User) -> LoanOffer:
        """Generate a nano loan offer (CDL fallback for borderline users)."""
        interest = self.NANO_LOAN_AMOUNT * self.NANO_LOAN_RATE
        total = self.NANO_LOAN_AMOUNT + interest

        offer = LoanOffer(
            application_id=application.id,
            user_id=user.id,
            loan_type=LoanType.NANO,
            approved_amount=self.NANO_LOAN_AMOUNT,
            tenure_days=self.NANO_LOAN_TENURE,
            interest_rate_monthly=self.NANO_LOAN_RATE,
            annual_rate=self.NANO_LOAN_RATE * 12,
            base_rate=self.NANO_LOAN_RATE,
            risk_premium=0.0,
            persona_adjustment=0.0,
            ladder_discount=0.0,
            total_interest=interest,
            processing_fee=0.0,
            total_repayment=total,
            repayment_frequency=RepaymentFrequency.ONE_TIME,
            number_of_installments=1,
            installment_amount=total,
            first_repayment_date=date_type.today() + timedelta(days=self.NANO_LOAN_TENURE),
            risk_tier=None,
            risk_tier_name="Nano",
            expires_at=datetime.utcnow() + timedelta(hours=OFFER_VALIDITY_HOURS),
            is_nano=True,
        )
        self.db.add(offer)
        await self.db.flush()

        logger.info(f"Nano offer generated: {offer.id} — ₦{self.NANO_LOAN_AMOUNT:,.0f}")
        return offer

    async def generate_schedule(self, loan: Loan, offer: LoanOffer) -> list[LoanSchedule]:
        """Generate repayment schedule for an active loan."""
        schedules = []

        if offer.repayment_frequency == RepaymentFrequency.ONE_TIME:
            # Single payment — bullet / nano
            schedule = LoanSchedule(
                loan_id=loan.id,
                installment_number=1,
                due_date=loan.maturity_date,
                principal_due=offer.approved_amount,
                interest_due=offer.total_interest,
                fees_due=offer.processing_fee,
                total_due=offer.total_repayment,
            )
            self.db.add(schedule)
            schedules.append(schedule)

        else:
            # Multiple installments
            num = offer.number_of_installments
            principal_per = offer.approved_amount / num
            interest_per = offer.total_interest / num
            fee_per = offer.processing_fee / num
            total_per = offer.installment_amount

            interval = self._interval_days(offer.repayment_frequency)
            outstanding = offer.approved_amount

            for i in range(1, num + 1):
                due_date = offer.first_repayment_date + timedelta(days=interval * (i - 1))
                outstanding -= principal_per

                schedule = LoanSchedule(
                    loan_id=loan.id,
                    installment_number=i,
                    due_date=due_date,
                    principal_due=round(principal_per, 2),
                    interest_due=round(interest_per, 2),
                    fees_due=round(fee_per, 2) if i == 1 else 0,
                    total_due=round(total_per + (fee_per if i == 1 else 0), 2),
                )
                self.db.add(schedule)
                schedules.append(schedule)

        await self.db.flush()
        return schedules

    def _calculate_installments(self, tenure_days: int,
                                 frequency: RepaymentFrequency) -> int:
        """Calculate number of installments."""
        if frequency == RepaymentFrequency.ONE_TIME:
            return 1
        interval = self._interval_days(frequency)
        return max(tenure_days // interval, 1)

    def _interval_days(self, frequency: RepaymentFrequency) -> int:
        """Get interval in days between payments."""
        return {
            RepaymentFrequency.WEEKLY: 7,
            RepaymentFrequency.BIWEEKLY: 14,
            RepaymentFrequency.MONTHLY: 30,
            RepaymentFrequency.ONE_TIME: 0,
        }.get(frequency, 30)

    def _first_repayment_date(self, frequency: RepaymentFrequency) -> date_type:
        """Calculate first repayment date from today."""
        interval = self._interval_days(frequency)
        if interval == 0:
            return date_type.today() + timedelta(days=30)
        return date_type.today() + timedelta(days=interval)
