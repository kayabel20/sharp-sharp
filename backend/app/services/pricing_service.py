"""Risk-Based Pricing service — FairMoney-style 17-tier dynamic pricing."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.loan import LoanApplication, LoanLadder
from app.models.risk import RiskTier
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RiskPricingService:
    """
    Dynamic risk-based pricing engine:
    - Risk tier pricing from ML model output
    - Loan ladder discounts (loyalty program)
    - CBN regulatory caps
    """

    # CBN maximum interest rate (annualized)
    CBN_MAX_ANNUAL_RATE = 0.30  # 30% per annum cap for microfinance

    # Base cost structure
    COST_OF_FUNDS = settings.COST_OF_FUNDS if hasattr(settings, "COST_OF_FUNDS") else 0.12
    TARGET_MARGIN = settings.TARGET_MARGIN if hasattr(settings, "TARGET_MARGIN") else 0.04
    PROCESSING_FEE_PCT = 0.01  # 1% processing fee

    # Ladder tier discounts (monthly rate reduction)
    LADDER_DISCOUNTS = {
        1: 0.00,
        2: 0.005,
        3: 0.01,
        4: 0.015,
        5: 0.02,
        6: 0.025,
        7: 0.03,
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate(self, user: User, application: LoanApplication,
                        ml_score: dict, income: dict, bureau: dict) -> dict:
        """
        Calculate risk-based pricing for a loan application.

        Returns complete pricing breakdown:
        - Base rate (from risk tier)
        - Risk premium
        - Persona adjustment
        - Ladder discount
        - Final monthly rate
        - Processing fee
        - Total cost of loan
        """

        # Step 1: Get risk tier pricing
        risk_tier = await self._get_risk_tier(ml_score.get("credit_score", 0))
        base_rate = risk_tier["interest_rate"] if risk_tier else 0.15

        # Step 2: Calculate risk premium based on combined signals
        risk_premium = self._calculate_risk_premium(ml_score, income, bureau)

        # Step 3: Loan ladder discount (the primary segmentation mechanism)
        ladder_tier = user.ladder_tier or 1
        ladder_discount = self.LADDER_DISCOUNTS.get(ladder_tier, 0.0)

        # Step 4: Combine rates (no persona adjustment -- single path)
        monthly_rate = base_rate + risk_premium - ladder_discount
        monthly_rate = max(monthly_rate, 0.03)  # Floor at 3% monthly

        # Step 5: CBN compliance cap
        annual_rate = monthly_rate * 12
        if annual_rate > self.CBN_MAX_ANNUAL_RATE:
            monthly_rate = self.CBN_MAX_ANNUAL_RATE / 12
            annual_rate = self.CBN_MAX_ANNUAL_RATE

        # Step 6: Calculate loan amounts
        requested_amount = application.requested_amount or 0
        tenure_days = application.requested_tenure_days or 30

        # Max approved amount based on income
        max_by_income = self._max_amount_by_income(
            income.get("estimated_monthly_income", 0),
            income.get("dti_limit", 0.33),
            income.get("existing_obligations", 0),
            tenure_days,
            monthly_rate
        )

        # Max by ladder tier
        max_by_ladder = await self._get_ladder_max(user)

        # Approved amount = min of requested, income-based max, ladder max
        approved_amount = min(
            requested_amount,
            max_by_income,
            max_by_ladder
        )
        approved_amount = max(approved_amount, 0)

        # Step 7: Calculate costs
        months = max(tenure_days / 30, 1)
        total_interest = approved_amount * monthly_rate * months
        processing_fee = approved_amount * self.PROCESSING_FEE_PCT
        total_repayment = approved_amount + total_interest + processing_fee

        return {
            "approved_amount": round(approved_amount, 2),
            "tenure_days": tenure_days,
            "base_rate_monthly": round(base_rate, 4),
            "risk_premium": round(risk_premium, 4),
            "persona_adjustment": 0.0,
            "ladder_discount": round(ladder_discount, 4),
            "final_rate_monthly": round(monthly_rate, 4),
            "annual_rate": round(annual_rate, 4),
            "total_interest": round(total_interest, 2),
            "processing_fee": round(processing_fee, 2),
            "total_repayment": round(total_repayment, 2),
            "risk_tier": risk_tier["tier_number"] if risk_tier else None,
            "risk_tier_name": risk_tier["tier_name"] if risk_tier else None,
            "ladder_tier": ladder_tier,
            "max_by_income": round(max_by_income, 2),
            "max_by_ladder": round(max_by_ladder, 2),
        }

    async def _get_risk_tier(self, credit_score: float) -> dict | None:
        """Look up risk tier from database."""
        result = await self.db.execute(
            select(RiskTier).where(
                RiskTier.is_active == True,
                RiskTier.min_score <= credit_score,
                RiskTier.max_score >= credit_score,
            ).order_by(RiskTier.tier_number)
        )
        tier = result.scalar_one_or_none()

        if tier:
            return {
                "tier_number": tier.tier_number,
                "tier_name": tier.tier_name,
                "interest_rate": tier.interest_rate_monthly,
                "expected_npl_rate": tier.expected_npl_rate,
                "auto_approve": tier.auto_approve,
                "max_amount": tier.max_loan_amount,
                "max_tenure": tier.max_tenure_days,
            }

        # Default pricing
        return {
            "tier_number": 10,
            "tier_name": "Standard",
            "interest_rate": 0.15,
            "expected_npl_rate": 0.10,
            "auto_approve": False,
            "max_amount": 100_000,
            "max_tenure": 30,
        }

    def _calculate_risk_premium(self, ml_score: dict, income: dict, bureau: dict) -> float:
        """Calculate additional risk premium based on combined signals."""
        premium = 0.0

        # ML score premium
        credit_score = ml_score.get("credit_score", 500)
        if credit_score < 400:
            premium += 0.03
        elif credit_score < 500:
            premium += 0.02
        elif credit_score < 600:
            premium += 0.01

        # Income confidence premium
        confidence = income.get("confidence_score", 0.5)
        if confidence < 0.5:
            premium += 0.02
        elif confidence < 0.7:
            premium += 0.01

        # Bureau history premium
        if bureau.get("has_default_history"):
            premium += 0.03
        if bureau.get("total_active_loans", 0) > 3:
            premium += 0.01

        # High DTI premium
        dti = income.get("dti", 0)
        if dti > 0.35:
            premium += 0.015

        return premium

    def _max_amount_by_income(self, monthly_income: float, dti_limit: float,
                               existing_obligations: float, tenure_days: int,
                               monthly_rate: float) -> float:
        """Calculate maximum loan amount based on income affordability."""
        if monthly_income <= 0:
            return 0

        max_monthly_payment = (monthly_income * dti_limit) - existing_obligations
        if max_monthly_payment <= 0:
            return 0

        months = max(tenure_days / 30, 1)
        # Reverse the repayment calculation to get max principal
        max_amount = (max_monthly_payment * months) / (1 + monthly_rate * months)
        return max(max_amount, 0)

    async def _get_ladder_max(self, user: User) -> float:
        """Get max loan amount for user's ladder tier."""
        ladder_tier = user.ladder_tier or 1

        result = await self.db.execute(
            select(LoanLadder).where(
                LoanLadder.tier == ladder_tier,
                LoanLadder.is_active == True,
            )
        )
        ladder = result.scalar_one_or_none()

        if ladder:
            amounts = ladder.max_amounts or {}
            return max(amounts.values()) if amounts else 50_000

        default_limits = {
            1: 50_000, 2: 100_000, 3: 200_000,
            4: 350_000, 5: 500_000, 6: 750_000, 7: 1_000_000,
        }
        return default_limits.get(ladder_tier, 50_000)
