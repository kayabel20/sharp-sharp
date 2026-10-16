"""
Scoring Engine — LightGBM model loading, inference, and monitoring.

Single model for all borrowers (the loan ladder handles
segmentation, not persona-specific models).
"""
import logging
import os
import json
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve model dir. In Docker we default to /app/models. For local dev we fall
# back to <repo>/ml-service/models if /app/models is absent — keeps `python -m`
# working without forcing devs to set env vars.
def _resolve_model_dir() -> str:
    env_dir = os.getenv("MODEL_DIR")
    if env_dir:
        return env_dir
    docker_dir = "/app/models"
    if Path(docker_dir).exists():
        return docker_dir
    repo_dir = Path(__file__).resolve().parent.parent / "models"
    return str(repo_dir)


MODEL_DIR = _resolve_model_dir()

FEATURE_ORDER = [
    "user_age_days", "user_ladder_tier", "user_total_loans",
    "user_on_time_pct", "user_consecutive_on_time", "user_is_existing",
    "app_requested_amount", "app_requested_tenure",
    "income_estimated", "income_confidence", "income_declared",
    "income_variance", "income_dti", "income_disposable",
    "bank_avg_balance", "bank_avg_monthly_credit", "bank_avg_monthly_debit",
    "bank_salary_frequency", "bank_gambling_txns", "bank_other_lenders",
    "bank_zero_balance_days", "bank_overdraft_count", "bank_months_covered",
    "fraud_identity_score", "fraud_digital_score", "fraud_geo_score",
    "fraud_device_score", "fraud_composite",
    "fraud_graph_connected_defaulters",
    "emp_is_salaried", "emp_has_ippis", "emp_has_employer",
    "demo_age_years", "demo_has_dependants", "demo_dependant_count",
]


class ScoringEngine:
    """Manages ML models and performs inference."""

    def __init__(self):
        self.models = {}

    def load_models(self):
        """Load all available models from disk."""
        model_path = Path(MODEL_DIR)

        if model_path.exists():
            for model_file in model_path.glob("*.json"):
                stem = model_file.name
                if stem.endswith(".meta.json") or stem.startswith("_"):
                    continue
                try:
                    self._load_model(model_file)
                except Exception as e:
                    logger.warning(f"Failed to load model {model_file}: {e}")

        if "credit_score_v1" not in self.models:
            self.models["credit_score_v1"] = {
                "type": "rules_fallback",
                "version": "v1",
                "persona": "universal",
                "model": None,
                "feature_count": len(FEATURE_ORDER),
                "is_champion": True,
            }
            logger.info("Registered fallback model: credit_score_v1")

    def _load_model(self, path: Path):
        """Load a single LightGBM model from disk."""
        try:
            import lightgbm as lgb

            model_name = path.stem
            model = lgb.Booster(model_file=str(path))

            # Load metadata if exists
            meta_path = path.with_suffix(".meta.json")
            metadata = {}
            if meta_path.exists():
                with open(meta_path) as f:
                    metadata = json.load(f)

            self.models[model_name] = {
                "type": "lightgbm",
                "version": metadata.get("version", "v1"),
                "persona": metadata.get("persona", "unknown"),
                "model": model,
                "feature_names": metadata.get("feature_names", []),
                "feature_count": model.num_feature(),
                "is_champion": metadata.get("is_champion", True),
                "calibration": metadata.get("calibration", None),
            }
            logger.info(f"Loaded LightGBM model: {model_name}")

        except ImportError:
            logger.warning("LightGBM not installed, using rules-based fallback")
        except Exception as e:
            logger.error(f"Failed to load model {path}: {e}")

    def predict(self, model_name: str, features: dict, persona: str) -> dict:
        """Run inference on a single application."""
        if model_name not in self.models:
            model_name = "credit_score_v1"

        model_info = self.models[model_name]

        if model_info["type"] == "lightgbm" and model_info["model"] is not None:
            return self._predict_lgb(model_info, features)
        else:
            return self._predict_rules(features, model_name)

    def _predict_lgb(self, model_info: dict, features: dict) -> dict:
        """LightGBM model inference."""
        model = model_info["model"]
        feature_names = model_info.get("feature_names") or FEATURE_ORDER

        # Build feature vector in correct order
        X = np.array([[features.get(f, 0) for f in feature_names]])

        # Predict PD (probability of default)
        pd_raw = model.predict(X)[0]
        pd = float(np.clip(pd_raw, 0.001, 0.999))

        # Calibrate if calibration params available
        calibration = model_info.get("calibration")
        if calibration:
            pd = self._calibrate_pd(pd, calibration)

        # Map PD to credit score (300-850 range)
        credit_score = self._pd_to_score(pd)

        # Feature importance (top 10)
        importances = model.feature_importance(importance_type="gain")
        top_indices = np.argsort(importances)[::-1][:10]
        top_features = [
            {
                "feature": feature_names[i] if i < len(feature_names) else f"f_{i}",
                "importance": float(importances[i]) / max(importances.sum(), 1),
            }
            for i in top_indices
        ]

        return {
            "credit_score": credit_score,
            "pd": pd,
            "top_features": top_features,
            "confidence": 0.85,
            "model_name": "credit_score_v1",
            "model_version": model_info["version"],
        }

    def _predict_rules(self, features: dict, model_name: str) -> dict:
        """Rules-based fallback scoring -- single path, no persona adjustments."""
        score = 500

        # Income
        income = features.get("income_estimated", 0)
        if income > 100000:
            score += 50
        elif income > 50000:
            score += 30

        # Bank
        if features.get("bank_avg_balance", 0) > 50000:
            score += 30
        if features.get("bank_gambling_txns", 0) > 0:
            score -= 50
        if features.get("bank_other_lenders", 0) > 3:
            score -= 30
        if features.get("bank_zero_balance_days", 0) > 15:
            score -= 20

        # Repayment history (ladder-driven)
        score += features.get("user_on_time_pct", 0) * 100
        score += features.get("user_ladder_tier", 1) * 15
        score += features.get("user_consecutive_on_time", 0) * 5

        # Fraud
        score += (features.get("fraud_composite", 50) - 50) * 2

        # Employment (data signal, not persona routing)
        if features.get("emp_is_salaried"):
            score += 20
        if features.get("emp_has_employer"):
            score += 10

        score = max(min(score, 850), 300)
        pd = max(0.01, 1 - (score - 300) / 550)

        return {
            "credit_score": score,
            "pd": round(pd, 4),
            "top_features": [
                {"feature": "income_estimated", "importance": 0.15},
                {"feature": "bank_avg_balance", "importance": 0.12},
                {"feature": "user_on_time_pct", "importance": 0.10},
                {"feature": "fraud_composite", "importance": 0.09},
                {"feature": "emp_is_salaried", "importance": 0.08},
            ],
            "confidence": 0.6,
            "model_name": model_name,
            "model_version": "v1-rules",
        }

    def _pd_to_score(self, pd: float) -> float:
        """Map probability of default to 300-850 credit score."""
        # Log-odds based mapping (similar to FICO)
        import math
        log_odds = math.log((1 - pd) / pd)
        score = 500 + log_odds * 100
        return max(min(round(score), 850), 300)

    def _calibrate_pd(self, pd: float, calibration: dict) -> float:
        """
        Apply Platt scaling: P_cal = sigmoid(a * pd + b).

        With a=1, b=0 this is sigmoid(pd) — close to identity for pd in [0, 1]
        but not exactly. To get true identity, omit `calibration` from the meta
        file or set it to null.
        """
        a = calibration.get("a", 1.0)
        b = calibration.get("b", 0.0)
        import math
        calibrated = 1.0 / (1.0 + math.exp(-(a * pd + b)))
        return float(np.clip(calibrated, 0.001, 0.999))
