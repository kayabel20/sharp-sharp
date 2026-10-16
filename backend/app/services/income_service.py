"""Income Estimation service — multi-source income triangulation."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, Persona
from app.models.loan import LoanApplication
from app.models.risk import IncomeEstimate

logger = logging.getLogger(__name__)

# DTI limits per persona
DTI_LIMITS = {
    "salary_earner": 0.40,
    "self_employed": 0.35,
    "public_sector": 0.45,
    "nysc": 0.30,
    "unknown": 0.33,
}


class IncomeEstimationService:
    """
    Triangulates income from multiple sources:
    1. Declared income (user-provided)
    2. Bank statement salary detection (Indicina/Mono)
    3. Employment verification (IPPIS/payroll)
    4. Bureau reported income
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def estimate(self, user: User, application: LoanApplication,
                       bank_result: dict) -> dict:
        """Estimate monthly income and check affordability."""

        sources = {}
        weights = {}

        # Source 1: Declared income
        if user.declared_monthly_income and user.declared_monthly_income > 0:
            sources["declared"] = user.declared_monthly_income
            weights["declared"] = 0.15  # Lowest weight — self-reported

        # Source 2: Bank statement salary detection
        bank_salary = bank_result.get("estimated_salary") if bank_result else None
        if bank_salary and bank_salary > 0:
            sources["bank_salary"] = bank_salary
            weights["bank_salary"] = 0.40  # High weight — objective data

        # Source 3: Average monthly credits from bank
        avg_credit = bank_result.get("average_monthly_credit") if bank_result else None
        if avg_credit and avg_credit > 0:
            sources["bank_avg_credit"] = avg_credit
            weights["bank_avg_credit"] = 0.25

        # Source 4: IPPIS / payroll (public sector)
        if user.ippis_number and user.ippis_salary:
            sources["ippis"] = user.ippis_salary
            weights["ippis"] = 0.50  # Very high — government-verified

        # Source 5: Employer-verified income
        if user.employer_verified_income:
            sources["employer_verified"] = user.employer_verified_income
            weights["employer_verified"] = 0.45

        # Calculate weighted estimate
        if not sources:
            estimated_income = 0
            confidence = 0.0
        else:
            total_weight = sum(weights.values())
            estimated_income = sum(
                sources[k] * (weights[k] / total_weight) for k in sources
            )
            # Confidence based on number and quality of sources
            confidence = min(total_weight / 0.80, 1.0)

        # Income variance (how much sources disagree)
        income_values = list(sources.values())
        if len(income_values) >= 2:
            avg = sum(income_values) / len(income_values)
            variance = sum((v - avg) ** 2 for v in income_values) / len(income_values)
            income_variance = (variance ** 0.5) / max(avg, 1)  # CV
        else:
            income_variance = 0.0

        # High variance reduces confidence
        if income_variance > 0.5:
            confidence *= 0.7

        # Monthly expenses estimate
        avg_debit = bank_result.get("average_monthly_debit", 0) if bank_result else 0
        disposable_income = bank_result.get("disposable_income") if bank_result else None
        if disposable_income is None:
            disposable_income = max(estimated_income - avg_debit, 0)

        # Existing obligations
        existing_obligations = self._estimate_existing_obligations(user, bank_result)

        # DTI calculation
        requested_monthly = self._calculate_monthly_repayment(
            application.requested_amount or 0,
            application.requested_tenure_days or 30
        )
        total_obligations = existing_obligations + requested_monthly
        dti = total_obligations / max(estimated_income, 1)

        # Affordability check
        persona = user.persona.value if user.persona else "unknown"
        dti_limit = DTI_LIMITS.get(persona, 0.33)
        passes_affordability = dti <= dti_limit and estimated_income > 0

        # Save income estimate
        estimate = IncomeEstimate(
            user_id=user.id,
            application_id=application.id,
            declared_income=user.declared_monthly_income,
            salary_income=bank_salary,
            business_income=sources.get("employer_verified"),
            other_income=sources.get("ippis"),
            estimated_monthly_income=estimated_income,
            confidence_score=confidence,
            income_variance=income_variance,
            is_income_inflated=income_variance > 0.5 if income_variance else None,
            estimated_monthly_expenses=avg_debit,
            estimated_disposable_income=disposable_income,
            debt_to_income_ratio=dti,
            max_affordable_emi=max(disposable_income - existing_obligations, 0) if disposable_income else 0,
            sources=list(sources.keys()),
            model_version="weighted_triangulation_v1",
        )
        self.db.add(estimate)
        await self.db.flush()

        return {
            "estimated_monthly_income": estimated_income,
            "confidence_score": confidence,
            "income_sources": list(sources.keys()),
            "income_variance": income_variance,
            "monthly_expenses": avg_debit,
            "existing_obligations": existing_obligations,
            "disposable_income": disposable_income,
            "dti": dti,
            "dti_limit": dti_limit,
            "passes_affordability": passes_affordability,
        }

    def _estimate_existing_obligations(self, user: User, bank_result: dict) -> float:
        """Estimate existing monthly debt obligations."""
        obligations = 0.0

        # From bank statement: detected loan repayments
        if bank_result:
            loan_repayments = bank_result.get("loan_repayments_detected", 0)
            obligations += loan_repayments

        # From bureau data (if loaded on user)
        if hasattr(user, "active_loan_obligations"):
            obligations += user.active_loan_obligations or 0

        return obligations

    def _calculate_monthly_repayment(self, amount: float, tenure_days: int) -> float:
        """Estimate monthly repayment for requested loan (simple approximation)."""
        if amount <= 0 or tenure_days <= 0:
            return 0
        # Assume ~15% monthly interest for estimation
        monthly_rate = 0.15
        months = max(tenure_days / 30, 1)
        if months <= 1:
            return amount * (1 + monthly_rate)
        # Simple installment calculation
        return (amount * (1 + monthly_rate * months)) / months
