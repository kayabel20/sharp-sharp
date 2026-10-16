"""
Loan Pipeline Orchestrator — The 14-step decisioning engine.

This is the core brain of the lending platform. It orchestrates the entire
loan application lifecycle from submission to disbursement.

Flow:
1. Application → 2. KYC → 3. Tier Check → 4. Data Collection → 5. Fraud Check
→ 6. Bank Statement → 7. Income Estimation → 8. Feature Engineering
→ 9. ML Scoring → 10. Risk Tier → 11. Bureau Check → 12. Pricing
→ 13. Offer Generation → 14. Monitoring
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.loan import (
    LoanApplication, ApplicationStatus, LoanOffer, Loan,
    LoanType, RepaymentFrequency, DeclineReason
)
from app.services.kyc_service import KYCService
from app.services.fraud_service import FraudService
from app.services.bank_service import BankStatementService
from app.services.income_service import IncomeEstimationService
from app.services.scoring_service import MLScoringService
from app.services.bureau_service import CreditBureauService
from app.services.pricing_service import RiskPricingService
from app.services.offer_service import OfferService
from app.services.disbursement_service import DisbursementService

logger = logging.getLogger(__name__)


class LoanPipeline:
    """Orchestrates the complete loan decisioning flow."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.kyc = KYCService(db)
        self.fraud = FraudService(db)
        self.bank = BankStatementService(db)
        self.income = IncomeEstimationService(db)
        self.scoring = MLScoringService(db)
        self.bureau = CreditBureauService(db)
        self.pricing = RiskPricingService(db)
        self.offer = OfferService(db)
        self.disbursement = DisbursementService(db)

    async def process_application(self, application_id: UUID) -> dict:
        """
        Run the full 14-step pipeline on a loan application.
        Returns the final status and any offer/rejection details.
        """
        application = await self._get_application(application_id)
        user = await self._get_user(application.user_id)

        logger.info(f"Starting pipeline for application {application_id}, user {user.id}")

        try:
            # Step 1-2: KYC Verification
            await self._update_status(application, ApplicationStatus.KYC_PENDING, "kyc")
            kyc_result = await self.kyc.verify(user)
            if not kyc_result["passed"]:
                return await self._reject(application, DeclineReason.POLICY_VIOLATION,
                                         f"KYC failed: {kyc_result.get('reason', 'unknown')}")
            application.kyc_completed_at = datetime.utcnow()

            # Step 3: Tier Check + Loan Ladder
            tier_check = await self._check_tier_eligibility(user, application)
            if not tier_check["eligible"]:
                return {"status": "tier_upgrade_required", "message": tier_check["message"]}

            # Step 4: Data Collection (already done at submission)

            # Step 5: Fraud Detection (Layer 1 + Layer 2)
            await self._update_status(application, ApplicationStatus.FRAUD_CHECK, "fraud_check")
            fraud_result = await self.fraud.check(user, application)
            application.fraud_composite_score = fraud_result["composite_score"]
            application.fraud_checked_at = datetime.utcnow()
            if fraud_result["decision"] == "knockoff":
                return await self._reject(application, DeclineReason.FRAUD_KNOCKOFF,
                                         fraud_result.get("reason", "Fraud score below cutoff"))

            # Step 6: Bank Statement Analysis
            await self._update_status(application, ApplicationStatus.BANK_ANALYSIS, "bank_analysis")
            bank_result = await self.bank.analyze(user, application)
            application.bank_analyzed_at = datetime.utcnow()

            # Step 7: Income Estimation
            await self._update_status(application, ApplicationStatus.INCOME_ESTIMATION, "income_estimation")
            income_result = await self.income.estimate(user, application, bank_result)
            application.income_estimate = income_result["estimated_monthly_income"]
            application.income_confidence = income_result["confidence_score"]
            application.income_estimated_at = datetime.utcnow()
            if not income_result["passes_affordability"]:
                return await self._reject(application, DeclineReason.INCOME_INSUFFICIENT,
                                         f"DTI ratio {income_result.get('dti', 'N/A')} exceeds limit")

            # Step 8-9: Feature Engineering + ML Scoring
            await self._update_status(application, ApplicationStatus.ML_SCORING, "ml_scoring")
            score_result = await self.scoring.score(user, application, bank_result, fraud_result, income_result)
            application.ml_score = score_result["credit_score"]
            application.risk_tier = score_result["risk_tier"]
            application.ml_scored_at = datetime.utcnow()
            if score_result["decision"] == "reject":
                return await self._reject(application, DeclineReason.ML_SCORE_LOW,
                                         f"ML score {score_result['credit_score']} below threshold")

            # Step 10-11: Credit Bureau Check
            await self._update_status(application, ApplicationStatus.BUREAU_CHECK, "bureau_check")
            bureau_result = await self.bureau.check(user, application)
            application.bureau_score = bureau_result.get("best_score")
            application.bureau_checked_at = datetime.utcnow()
            if not bureau_result["meets_eligibility"]:
                return await self._reject(application, DeclineReason.BUREAU_CUTOFF,
                                         bureau_result.get("reason", "Bureau score below cutoff"))

            # Step 12: Risk-Based Pricing
            pricing_result = await self.pricing.calculate(
                user=user,
                application=application,
                ml_score=score_result,
                income=income_result,
                bureau=bureau_result
            )

            # Step 13: Generate Offer
            await self._update_status(application, ApplicationStatus.OFFER_GENERATED, "offer_generation")
            offer = await self.offer.generate(
                application=application,
                user=user,
                pricing=pricing_result,
                income=income_result
            )
            application.offer_generated_at = datetime.utcnow()
            application.decision_made_at = datetime.utcnow()

            # Check if human review needed
            if score_result.get("requires_review") or fraud_result.get("requires_review"):
                application.requires_human_review = True
                await self._update_status(application, ApplicationStatus.HUMAN_REVIEW, "human_review")
                await self.db.commit()
                return {
                    "status": "human_review",
                    "application_id": str(application_id),
                    "offer_id": str(offer.id),
                    "message": "Application requires human review before offer is shown"
                }

            await self.db.commit()
            logger.info(f"Pipeline complete for {application_id}: offer generated")

            return {
                "status": "offer_generated",
                "application_id": str(application_id),
                "offer_id": str(offer.id),
                "offer": {
                    "amount": offer.approved_amount,
                    "tenure_days": offer.tenure_days,
                    "interest_rate": offer.interest_rate_monthly,
                    "total_repayment": offer.total_repayment,
                    "installment_amount": offer.installment_amount,
                    "frequency": offer.repayment_frequency.value,
                    "risk_tier": offer.risk_tier,
                    "risk_tier_name": offer.risk_tier_name,
                    "first_repayment_date": str(offer.first_repayment_date),
                    "expires_at": str(offer.expires_at),
                }
            }

        except Exception as e:
            logger.error(f"Pipeline error for {application_id}: {e}", exc_info=True)
            await self.db.rollback()
            raise

    async def accept_offer(self, offer_id: UUID, user_id: UUID) -> dict:
        """Customer accepts a loan offer — trigger disbursement."""
        offer = await self.db.get(LoanOffer, offer_id)
        if not offer:
            raise ValueError("Offer not found")

        if offer.expires_at < datetime.utcnow():
            return {"status": "expired", "message": "Offer has expired"}

        application = await self.db.get(LoanApplication, offer.application_id)
        user = await self._get_user(user_id)

        # Mark offer as accepted
        offer.is_accepted = True
        offer.accepted_at = datetime.utcnow()
        application.status = ApplicationStatus.OFFER_ACCEPTED

        # Create loan record
        loan = await self._create_loan(user, application, offer)

        # Trigger disbursement
        application.status = ApplicationStatus.DISBURSEMENT_PENDING
        disburse_result = await self.disbursement.disburse(loan, application)

        if disburse_result["success"]:
            loan.disbursement_reference = disburse_result["reference"]
            loan.disbursement_status = "successful"
            application.status = ApplicationStatus.DISBURSED
            application.disbursed_at = datetime.utcnow()

            # Update loan ladder
            user.total_loans_taken += 1
        else:
            loan.disbursement_status = "failed"
            application.status = ApplicationStatus.OFFER_ACCEPTED  # Revert, can retry

        await self.db.commit()

        return {
            "status": "disbursed" if disburse_result["success"] else "disbursement_failed",
            "loan_id": str(loan.id),
            "reference": disburse_result.get("reference"),
        }

    # =========== PRIVATE HELPERS ===========

    async def _get_application(self, app_id: UUID) -> LoanApplication:
        result = await self.db.execute(
            select(LoanApplication).where(LoanApplication.id == app_id)
        )
        application = result.scalar_one_or_none()
        if not application:
            raise ValueError(f"Application {app_id} not found")
        return application

    async def _get_user(self, user_id: UUID) -> User:
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.kyc),
                selectinload(User.devices),
                selectinload(User.addresses),
            )
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")
        return user

    async def _update_status(self, application: LoanApplication,
                             status: ApplicationStatus, step: str):
        application.status = status
        application.current_step = step
        application.updated_at = datetime.utcnow()
        await self.db.flush()

    async def _check_tier_eligibility(self, user: User, application: LoanApplication) -> dict:
        """Check if user meets tier requirements for the requested loan."""
        # For small loans (under 200k), Tier 1/2 is fine
        if application.requested_amount and application.requested_amount <= 200_000:
            return {"eligible": True}

        # For larger loans, need Tier 3 (which requires proof of address)
        if user.tier.value in ("tier_1", "tier_2") and application.requested_amount and application.requested_amount > 200_000:
            return {
                "eligible": False,
                "message": "Tier 3 upgrade required for loans above ₦200,000. Please complete address verification."
            }

        return {"eligible": True}

    async def _reject(self, application: LoanApplication,
                      reason: DeclineReason, details: str) -> dict:
        application.status = ApplicationStatus.REJECTED
        application.decline_reason = reason
        application.decline_details = details
        application.decision_made_at = datetime.utcnow()
        await self.db.commit()
        logger.info(f"Application {application.id} rejected: {reason.value} - {details}")
        return {
            "status": "rejected",
            "application_id": str(application.id),
            "reason": reason.value,
            "details": details,
        }

    async def _create_loan(self, user: User, application: LoanApplication,
                           offer: LoanOffer) -> Loan:
        """Create loan record from accepted offer."""
        from app.models.loan import LoanStatus
        from datetime import date as date_type

        loan = Loan(
            user_id=user.id,
            application_id=application.id,
            loan_type=offer.loan_type,
            principal_amount=offer.approved_amount,
            interest_amount=offer.total_interest,
            processing_fee=offer.processing_fee,
            total_amount_due=offer.total_repayment,
            interest_rate_monthly=offer.interest_rate_monthly,
            tenure_days=offer.tenure_days,
            repayment_frequency=offer.repayment_frequency,
            status=LoanStatus.ACTIVE,
            disbursement_date=date_type.today(),
            maturity_date=date_type.today() + timedelta(days=offer.tenure_days),
            first_payment_date=offer.first_repayment_date,
            outstanding_principal=offer.approved_amount,
            outstanding_interest=offer.total_interest,
            total_outstanding=offer.total_repayment,
            risk_tier=offer.risk_tier,
            ml_score_at_disbursement=application.ml_score,
            ladder_tier_at_disbursement=user.ladder_tier,
            disbursement_account=application.disbursement_account_number,
            disbursement_bank=application.disbursement_bank_code,
        )
        self.db.add(loan)
        await self.db.flush()

        # Generate repayment schedule
        await self.offer.generate_schedule(loan, offer)

        return loan
