"""Model monitoring — PSI, AUC, KS tracking (FairMoney approach)."""
import logging
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class ModelMonitor:
    """
    Monitors ML model performance in production:
    - PSI (Population Stability Index) for feature drift
    - AUC / KS stats tracking
    - Score distribution monitoring
    - Alert generation when thresholds breached
    """

    PSI_WARNING_THRESHOLD = 0.10
    PSI_CRITICAL_THRESHOLD = 0.25

    def __init__(self):
        self.baseline_distributions = {}
        self.score_history = []

    def calculate_psi(self, expected: np.ndarray, actual: np.ndarray,
                      buckets: int = 10) -> float:
        """
        Calculate Population Stability Index.
        PSI < 0.10 → No significant shift
        PSI 0.10-0.25 → Moderate shift (investigate)
        PSI > 0.25 → Significant shift (retrain)
        """
        def _psi_bucket(e, a):
            e = max(e, 0.0001)
            a = max(a, 0.0001)
            return (a - e) * np.log(a / e)

        breakpoints = np.linspace(0, 1, buckets + 1)

        expected_pct = np.histogram(expected, breakpoints)[0] / len(expected)
        actual_pct = np.histogram(actual, breakpoints)[0] / len(actual)

        psi = sum(_psi_bucket(e, a) for e, a in zip(expected_pct, actual_pct))
        return float(psi)

    def calculate_ks(self, y_true: np.ndarray, y_scores: np.ndarray) -> float:
        """Calculate Kolmogorov-Smirnov statistic."""
        from scipy import stats
        defaults = y_scores[y_true == 1]
        non_defaults = y_scores[y_true == 0]

        if len(defaults) == 0 or len(non_defaults) == 0:
            return 0.0

        ks_stat, _ = stats.ks_2samp(defaults, non_defaults)
        return float(ks_stat)

    def calculate_gini(self, y_true: np.ndarray, y_scores: np.ndarray) -> float:
        """Calculate Gini coefficient (2*AUC - 1)."""
        from sklearn.metrics import roc_auc_score
        try:
            auc = roc_auc_score(y_true, y_scores)
            return 2 * auc - 1
        except Exception:
            return 0.0

    def check_drift(self, feature_name: str, current_values: np.ndarray) -> dict:
        """Check if a feature has drifted from its baseline."""
        if feature_name not in self.baseline_distributions:
            # Store as baseline
            self.baseline_distributions[feature_name] = current_values
            return {"drifted": False, "psi": 0.0}

        baseline = self.baseline_distributions[feature_name]
        psi = self.calculate_psi(baseline, current_values)

        alert_level = "ok"
        if psi > self.PSI_CRITICAL_THRESHOLD:
            alert_level = "critical"
        elif psi > self.PSI_WARNING_THRESHOLD:
            alert_level = "warning"

        return {
            "feature": feature_name,
            "psi": psi,
            "alert_level": alert_level,
            "drifted": psi > self.PSI_WARNING_THRESHOLD,
            "checked_at": datetime.utcnow().isoformat(),
        }

    def log_score(self, model_name: str, credit_score: float, pd: float):
        """Log a score for distribution monitoring."""
        self.score_history.append({
            "model": model_name,
            "score": credit_score,
            "pd": pd,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Keep last 10k scores in memory
        if len(self.score_history) > 10000:
            self.score_history = self.score_history[-10000:]

    def get_score_distribution(self, model_name: str = None) -> dict:
        """Get score distribution statistics."""
        scores = [
            s["score"] for s in self.score_history
            if model_name is None or s["model"] == model_name
        ]
        if not scores:
            return {"count": 0}

        arr = np.array(scores)
        return {
            "count": len(scores),
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "std": float(np.std(arr)),
            "p10": float(np.percentile(arr, 10)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "p90": float(np.percentile(arr, 90)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
        }
