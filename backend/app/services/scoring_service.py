"""ML Credit Scoring service — single model, all borrowers through one path."""
import logging
import time
from datetime import datetime
from uuid import UUID
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.loan import LoanApplication
from app.models.risk import MLScore, RiskTier, FeatureSnapshot
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MLScoringService:
    """Single-path ML credit scoring for all borrowers."""

    SCORE_THRESHOLD = 380

    def __init__(self, db: AsyncSession):
        self.db = db

    async def score(self, user: User, application: LoanApplication,
                    bank_result: dict, fraud_result: dict,
                    income_result: dict) -> dict:
        """
        Score a loan application using segment-specific ML model.
        Calls the ml-service microservice for inference.
        """
        start_time = time.time()

        # Step 1: Build feature vector
        features = await self._build_features(user, application, bank_result,
                                               fraud_result, income_result)

        # Step 2: Save feature snapshot
        snapshot = FeatureSnapshot(
            user_id=user.id,
            application_id=application.id,
            features=features,
            feature_count=len(features),
            feature_version="v1",
            bureau_features=sum(1 for k in features if k.startswith("bureau_")),
            bank_features=sum(1 for k in features if k.startswith("bank_")),
            device_features=sum(1 for k in features if k.startswith("device_")),
            behavioral_features=sum(1 for k in features if k.startswith("beh_")),
            telco_features=sum(1 for k in features if k.startswith("telco_")),
        )
        self.db.add(snapshot)

        # Step 3: Single model for all borrowers
        persona = user.persona.value if user.persona else "unknown"
        model_name = "credit_score_v1"

        # Step 4: Call ML service for inference
        try:
            score_result = await self._call_ml_service(model_name, features, persona)
        except Exception as e:
            logger.error(f"ML service call failed: {e}")
            # Fallback to rules-based scoring
            score_result = self._fallback_scoring(features, persona)

        inference_time = (time.time() - start_time) * 1000

        # Step 5: Map score to risk tier
        risk_tier = await self._map_to_risk_tier(
            score_result["credit_score"], persona
        )

        # Step 6: Determine decision
        threshold = self.SCORE_THRESHOLD
        decision = "approve" if score_result["credit_score"] >= threshold else "reject"

        # Edge cases → manual review
        requires_review = (
            abs(score_result["credit_score"] - threshold) <= 30 or  # Borderline
            score_result.get("confidence", 1.0) < 0.7  # Low confidence
        )

        # Step 7: Save ML score record
        ml_score = MLScore(
            user_id=user.id,
            application_id=application.id,
            model_name=model_name,
            model_version="v1",
            model_type="lightgbm",
            persona_segment=persona,
            probability_of_default=score_result.get("pd", 0.0),
            credit_score=score_result["credit_score"],
            score_band=self._score_to_band(score_result["credit_score"]),
            risk_tier=risk_tier["tier_number"] if risk_tier else None,
            risk_tier_name=risk_tier["tier_name"] if risk_tier else None,
            expected_npl_rate=risk_tier["expected_npl_rate"] if risk_tier else None,
            top_features=score_result.get("top_features"),
            features_used=len(features),
            inference_time_ms=inference_time,
            is_champion=True,
        )
        self.db.add(ml_score)
        await self.db.flush()

        return {
            "credit_score": score_result["credit_score"],
            "pd": score_result.get("pd", 0.0),
            "score_band": ml_score.score_band,
            "risk_tier": risk_tier["tier_number"] if risk_tier else None,
            "risk_tier_name": risk_tier["tier_name"] if risk_tier else None,
            "expected_npl_rate": risk_tier["expected_npl_rate"] if risk_tier else None,
            "decision": decision,
            "requires_review": requires_review,
            "model_name": model_name,
            "inference_time_ms": inference_time,
            "top_features": score_result.get("top_features"),
        }

    async def _build_features(self, user: User, application: LoanApplication,
                               bank_result: dict, fraud_result: dict,
                               income_result: dict) -> dict:
        """Build the feature vector from all data sources."""
        features = {}

        # User features
        features["user_age_days"] = (datetime.utcnow() - user.created_at).days if user.created_at else 0
        features["user_ladder_tier"] = user.ladder_tier
        features["user_total_loans"] = user.total_loans_taken
        features["user_on_time_pct"] = (
            user.total_loans_repaid_on_time / max(user.total_loans_taken, 1)
        )
        features["user_consecutive_on_time"] = user.consecutive_on_time_repayments
        features["user_is_existing"] = 1 if user.is_existing_customer else 0

        # Application features
        features["app_requested_amount"] = application.requested_amount or 0
        features["app_requested_tenure"] = application.requested_tenure_days or 30

        # Income features
        features["income_estimated"] = income_result.get("estimated_monthly_income", 0)
        features["income_confidence"] = income_result.get("confidence_score", 0)
        features["income_declared"] = user.declared_monthly_income or 0
        features["income_variance"] = income_result.get("income_variance", 0)
        features["income_dti"] = income_result.get("dti", 0)
        features["income_disposable"] = income_result.get("disposable_income", 0)

        # Bank statement features
        if bank_result:
            features["bank_avg_balance"] = bank_result.get("average_balance", 0)
            features["bank_avg_monthly_credit"] = bank_result.get("average_monthly_credit", 0)
            features["bank_avg_monthly_debit"] = bank_result.get("average_monthly_debit", 0)
            features["bank_salary_frequency"] = 1 if bank_result.get("salary_frequency") == "monthly" else 0
            features["bank_gambling_txns"] = bank_result.get("gambling_transactions", 0)
            features["bank_other_lenders"] = bank_result.get("other_lender_count", 0)
            features["bank_zero_balance_days"] = bank_result.get("days_with_zero_balance", 0)
            features["bank_overdraft_count"] = bank_result.get("overdraft_count", 0)
            features["bank_months_covered"] = bank_result.get("months_covered", 0)

        # Fraud features
        features["fraud_identity_score"] = fraud_result.get("identity_score", 0)
        features["fraud_digital_score"] = fraud_result.get("digital_score", 0)
        features["fraud_geo_score"] = fraud_result.get("geo_score", 0)
        features["fraud_device_score"] = fraud_result.get("device_score", 0)
        features["fraud_composite"] = fraud_result.get("composite_score", 0)
        features["fraud_graph_connected_defaulters"] = fraud_result.get("graph_result", {}).get("connected_defaulters", 0)

        # Employment features
        features["emp_is_salaried"] = 1 if user.employment_status in ("employed", "salaried", "full_time") else 0
        features["emp_has_ippis"] = 1 if user.ippis_number else 0
        features["emp_has_employer"] = 1 if user.employer_name else 0

        # Demographic features
        if user.date_of_birth:
            features["demo_age_years"] = (datetime.utcnow().date() - user.date_of_birth).days / 365.25
        features["demo_has_dependants"] = 1 if user.number_of_dependants and user.number_of_dependants > 0 else 0
        features["demo_dependant_count"] = user.number_of_dependants or 0

        return features

    async def _call_ml_service(self, model_name: str, features: dict,
                                persona: str) -> dict:
        """Call the ML scoring microservice."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.ML_SERVICE_URL}/score",
                json={
                    "model_name": model_name,
                    "features": features,
                    "persona": persona,
                }
            )
            response.raise_for_status()
            return response.json()

    def _fallback_scoring(self, features: dict, persona: str) -> dict:
        """
        Rules-based fallback scoring when ML service is unavailable.
        Uses weighted feature scoring as a simple proxy.
        """
        score = 500  # Base score

        # Income factors
        if features.get("income_estimated", 0) > 100000:
            score += 50
        elif features.get("income_estimated", 0) > 50000:
            score += 30

        # Bank factors
        if features.get("bank_avg_balance", 0) > 50000:
            score += 30
        if features.get("bank_gambling_txns", 0) > 0:
            score -= 50
        if features.get("bank_other_lenders", 0) > 3:
            score -= 30

        # History factors
        score += features.get("user_on_time_pct", 0) * 100
        score += features.get("user_ladder_tier", 1) * 15

        # Fraud factors
        score += (features.get("fraud_composite", 50) - 50) * 2

        # Employment factors
        if features.get("emp_has_ippis"):
            score += 40
        if features.get("emp_is_salaried"):
            score += 20

        score = max(min(score, 850), 300)

        return {
            "credit_score": score,
            "pd": max(0.01, 1 - (score - 300) / 550),  # Simple PD mapping
            "top_features": [
                {"feature": "income_estimated", "importance": 0.15},
                {"feature": "bank_avg_balance", "importance": 0.12},
                {"feature": "user_on_time_pct", "importance": 0.10},
            ],
            "confidence": 0.6,  # Lower confidence for fallback
        }

    async def _map_to_risk_tier(self, credit_score: float, persona: str) -> dict | None:
        """Map a credit score to a risk tier."""
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
                "expected_npl_rate": tier.expected_npl_rate,
                "interest_rate": tier.interest_rate_monthly,
                "auto_approve": tier.auto_approve,
            }

        # Default tier if none matched
        return {
            "tier_number": 10,
            "tier_name": "Standard",
            "expected_npl_rate": 0.10,
            "interest_rate": 0.15,
            "auto_approve": False,
        }

    def _score_to_band(self, score: float) -> str:
        if score >= 750:
            return "A"
        elif score >= 650:
            return "B"
        elif score >= 550:
            return "C"
        elif score >= 450:
            return "D"
        else:
            return "E"
