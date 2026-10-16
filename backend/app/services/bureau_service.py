"""Credit Bureau service — multi-bureau strategy (CRC + FirstCentral + CreditRegistry)."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.loan import LoanApplication
from app.models.risk import CreditBureauReport, BureauProvider
from app.integrations.crc import CRCClient
from app.integrations.first_central import FirstCentralClient
from app.integrations.credit_registry import CreditRegistryClient

logger = logging.getLogger(__name__)


class CreditBureauService:
    """
    Multi-bureau credit check strategy (CDL advantage):
    - CRC (Credit Reference Company) — primary
    - FirstCentral Credit Bureau — secondary
    - CreditRegistry — tertiary

    Uses best-of-three scoring approach.
    """

    # Bureau score cutoffs
    CRC_CUTOFF = 550
    FIRST_CENTRAL_CUTOFF = 500
    CREDIT_REGISTRY_CUTOFF = 500

    # Maximum active loans with other lenders
    MAX_ACTIVE_LOANS = 5

    def __init__(self, db: AsyncSession):
        self.db = db
        self.crc = CRCClient()
        self.first_central = FirstCentralClient()
        self.credit_registry = CreditRegistryClient()

    async def check(self, user: User, application: LoanApplication) -> dict:
        """Run multi-bureau credit check."""
        bvn = user.kyc.bvn if user.kyc else None
        if not bvn:
            return {
                "meets_eligibility": False,
                "reason": "No BVN available for bureau check",
                "best_score": None,
            }

        reports = []
        best_score = None
        total_active_loans = 0
        total_outstanding = 0
        has_default_history = False

        # Bureau 1: CRC (primary)
        crc_result = await self._check_crc(user, application, bvn)
        if crc_result:
            reports.append(crc_result)
            if crc_result.get("score"):
                best_score = crc_result["score"]

        # Bureau 2: FirstCentral
        fc_result = await self._check_first_central(user, application, bvn)
        if fc_result:
            reports.append(fc_result)
            if fc_result.get("score") and (not best_score or fc_result["score"] > best_score):
                best_score = fc_result["score"]

        # Bureau 3: CreditRegistry
        cr_result = await self._check_credit_registry(user, application, bvn)
        if cr_result:
            reports.append(cr_result)
            if cr_result.get("score") and (not best_score or cr_result["score"] > best_score):
                best_score = cr_result["score"]

        # Aggregate findings
        for report in reports:
            total_active_loans += report.get("active_loans", 0)
            total_outstanding += report.get("total_outstanding", 0)
            if report.get("has_default"):
                has_default_history = True

        # Eligibility decision
        meets_eligibility = True
        reason = None

        if not reports:
            # No bureau data — allow for first-time borrowers but flag
            return {
                "meets_eligibility": True,
                "reason": "No bureau history (first-time borrower)",
                "best_score": None,
                "is_first_time": True,
                "reports_count": 0,
            }

        if best_score and best_score < self.CRC_CUTOFF:
            meets_eligibility = False
            reason = f"Best bureau score {best_score} below cutoff {self.CRC_CUTOFF}"

        if total_active_loans > self.MAX_ACTIVE_LOANS:
            meets_eligibility = False
            reason = f"Too many active loans ({total_active_loans}) across bureaus"

        if has_default_history:
            # Don't auto-reject, but flag for review
            pass

        return {
            "meets_eligibility": meets_eligibility,
            "reason": reason,
            "best_score": best_score,
            "reports_count": len(reports),
            "total_active_loans": total_active_loans,
            "total_outstanding": total_outstanding,
            "has_default_history": has_default_history,
        }

    async def _check_crc(self, user: User, application: LoanApplication,
                         bvn: str) -> dict | None:
        """Check CRC bureau."""
        try:
            result = await self.crc.get_credit_report(bvn=bvn)

            report = CreditBureauReport(
                user_id=user.id,
                application_id=application.id,
                provider=BureauProvider.CRC,
                reference_id=result.get("reference"),
                bureau_score=result.get("score"),
                score_band=self._score_band(result.get("score")),
                total_accounts=result.get("total_accounts", 0),
                active_accounts=result.get("active_accounts", 0),
                closed_accounts=result.get("closed_accounts", 0),
                delinquent_accounts=result.get("delinquent_accounts", 0),
                total_outstanding=result.get("total_outstanding", 0),
                total_overdue=result.get("monthly_payment", 0),
                worst_delinquency_days=result.get("max_dpd", 0),
                has_existing_loan=result.get("has_default", False),
                recent_inquiries_30d=result.get("enquiries_30d", 0),
                recent_inquiries_90d=result.get("enquiries_90d", 0),
                raw_response=result.get("raw_response"),
                status="success",
            )
            self.db.add(report)
            await self.db.flush()

            return {
                "bureau": "CRC",
                "score": result.get("score"),
                "active_loans": result.get("active_accounts", 0),
                "total_outstanding": result.get("total_outstanding", 0),
                "has_default": result.get("has_default", False),
            }

        except Exception as e:
            logger.warning(f"CRC check failed for user {user.id}: {e}")
            return None

    async def _check_first_central(self, user: User, application: LoanApplication,
                                    bvn: str) -> dict | None:
        """Check FirstCentral bureau."""
        try:
            result = await self.first_central.get_credit_report(bvn=bvn)

            report = CreditBureauReport(
                user_id=user.id,
                application_id=application.id,
                provider=BureauProvider.FIRST_CENTRAL,
                reference_id=result.get("reference"),
                bureau_score=result.get("score"),
                score_band=self._score_band(result.get("score")),
                total_accounts=result.get("total_accounts", 0),
                active_accounts=result.get("active_accounts", 0),
                closed_accounts=result.get("closed_accounts", 0),
                delinquent_accounts=result.get("delinquent_accounts", 0),
                total_outstanding=result.get("total_outstanding", 0),
                has_existing_loan=result.get("has_default", False),
                worst_delinquency_days=result.get("max_dpd", 0),
                raw_response=result.get("raw_response"),
                status="success",
            )
            self.db.add(report)
            await self.db.flush()

            return {
                "bureau": "FirstCentral",
                "score": result.get("score"),
                "active_loans": result.get("active_accounts", 0),
                "total_outstanding": result.get("total_outstanding", 0),
                "has_default": result.get("has_default", False),
            }

        except Exception as e:
            logger.warning(f"FirstCentral check failed for user {user.id}: {e}")
            return None

    async def _check_credit_registry(self, user: User, application: LoanApplication,
                                      bvn: str) -> dict | None:
        """Check CreditRegistry bureau."""
        try:
            result = await self.credit_registry.get_credit_report(bvn=bvn)

            report = CreditBureauReport(
                user_id=user.id,
                application_id=application.id,
                provider=BureauProvider.CREDIT_REGISTRY,
                reference_id=result.get("reference"),
                bureau_score=result.get("score"),
                score_band=self._score_band(result.get("score")),
                total_accounts=result.get("total_accounts", 0),
                active_accounts=result.get("active_accounts", 0),
                total_outstanding=result.get("total_outstanding", 0),
                has_existing_loan=result.get("has_default", False),
                raw_response=result.get("raw_response"),
                status="success",
            )
            self.db.add(report)
            await self.db.flush()

            return {
                "bureau": "CreditRegistry",
                "score": result.get("score"),
                "active_loans": result.get("active_accounts", 0),
                "total_outstanding": result.get("total_outstanding", 0),
                "has_default": result.get("has_default", False),
            }

        except Exception as e:
            logger.warning(f"CreditRegistry check failed for user {user.id}: {e}")
            return None

    def _score_band(self, score: float | None) -> str | None:
        if score is None:
            return None
        if score >= 750:
            return "Excellent"
        elif score >= 650:
            return "Good"
        elif score >= 550:
            return "Fair"
        elif score >= 450:
            return "Poor"
        else:
            return "Very Poor"
