"""
Train a baseline LightGBM PD model on synthetic NG borrower data.

What this does
==============
1. Generates a synthetic dataset of `n` borrower applications with persona-aware
   feature distributions roughly calibrated to the lending book signals
   (income, bank velocity, gambling, other-lender footprint, fraud composite,
   employment markers, ladder progression).
2. Defines a deterministic latent default function over those features and adds
   noise; the model has to learn the relationships, not the function itself.
3. Trains a LightGBM binary classifier per persona (5 personas → 5 artefacts).
4. Saves each model as `{persona}_credit_v1.json` plus a `.meta.json` sidecar
   with feature names, persona, calibration, and held-out AUC/KS.
5. Drops everything in `ml-service/models/` so the running ScoringEngine can
   pick them up on next startup.

This is deliberately scoped: synthetic data is for plumbing, not for production
underwriting. The real model needs actual loan-level history.

Run
===
    cd ml-service
    python scripts/train_baseline.py            # uses defaults
    python scripts/train_baseline.py --n 60000  # larger dataset
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("train_baseline")

# --------------------------------------------------------------------------- #
# Feature schema — must match ml-service/app/scoring_engine.py FEATURE_SETS    #
# --------------------------------------------------------------------------- #

FEATURES = [
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

PERSONAS = ["salary_earner", "self_employed", "public_sector", "nysc", "unknown"]

# Empirical-ish base default rates per persona (synthetic, but order matches
# what we see in NG data: NYSC and unknown highest, public sector lowest).
PERSONA_BASE_PD = {
    "salary_earner": 0.18,
    "self_employed": 0.26,
    "public_sector": 0.10,
    "nysc": 0.32,
    "unknown": 0.34,
}


# --------------------------------------------------------------------------- #
# Synthetic data generator                                                    #
# --------------------------------------------------------------------------- #

@dataclass
class GenConfig:
    n: int = 40_000
    seed: int = 7
    out_dir: Path = Path(__file__).resolve().parent.parent / "models"


def _truncated_normal(rng, mean, sd, lo, hi, size):
    """Draw normal samples then clip to [lo, hi]."""
    return np.clip(rng.normal(mean, sd, size), lo, hi)


def _bernoulli(rng, p, size):
    return (rng.random(size) < p).astype(np.int8)


def generate_dataset(cfg: GenConfig):
    """Generate a synthetic dataset stratified by persona."""
    rng = np.random.default_rng(cfg.seed)

    # Persona mix roughly mirrors NG market (salaried dominates).
    persona_probs = {
        "salary_earner": 0.45,
        "self_employed": 0.25,
        "public_sector": 0.15,
        "nysc": 0.05,
        "unknown": 0.10,
    }
    personas = rng.choice(
        list(persona_probs.keys()),
        size=cfg.n,
        p=list(persona_probs.values()),
    )

    rows: dict[str, np.ndarray] = {}

    # Demographics
    rows["demo_age_years"] = _truncated_normal(rng, 30, 7, 18, 65, cfg.n)
    rows["user_age_days"] = _truncated_normal(rng, 180, 200, 1, 1500, cfg.n)
    rows["demo_has_dependants"] = _bernoulli(rng, 0.55, cfg.n)
    rows["demo_dependant_count"] = (
        rows["demo_has_dependants"] * rng.integers(1, 5, cfg.n)
    )

    # User history (ladder + repayment behaviour)
    rows["user_total_loans"] = rng.poisson(2.0, cfg.n).astype(np.int16)
    rows["user_ladder_tier"] = np.clip(
        1 + rows["user_total_loans"] // 2, 1, 7
    ).astype(np.int8)
    rows["user_on_time_pct"] = _truncated_normal(rng, 0.78, 0.18, 0.0, 1.0, cfg.n)
    rows["user_consecutive_on_time"] = (
        rows["user_total_loans"] * rows["user_on_time_pct"]
    ).astype(np.int16)
    rows["user_is_existing"] = (rows["user_total_loans"] > 0).astype(np.int8)

    # Application sizing
    rows["app_requested_amount"] = _truncated_normal(
        rng, 80_000, 60_000, 5_000, 1_000_000, cfg.n
    )
    rows["app_requested_tenure"] = rng.choice([14, 30, 60, 90], cfg.n).astype(np.int16)

    # Income — shape it by persona
    income_means = {
        "salary_earner": 180_000,
        "self_employed": 220_000,
        "public_sector": 150_000,
        "nysc": 33_000,
        "unknown": 90_000,
    }
    income_sds = {
        "salary_earner": 80_000,
        "self_employed": 180_000,  # higher variance
        "public_sector": 50_000,
        "nysc": 5_000,
        "unknown": 60_000,
    }
    income_estimated = np.empty(cfg.n)
    for p in PERSONAS:
        mask = personas == p
        income_estimated[mask] = _truncated_normal(
            rng, income_means[p], income_sds[p], 10_000, 2_000_000, mask.sum()
        )
    rows["income_estimated"] = income_estimated
    rows["income_declared"] = income_estimated * _truncated_normal(
        rng, 1.05, 0.15, 0.5, 2.0, cfg.n
    )
    rows["income_confidence"] = _truncated_normal(rng, 0.75, 0.15, 0.2, 1.0, cfg.n)
    rows["income_variance"] = _truncated_normal(rng, 0.20, 0.15, 0.0, 1.5, cfg.n)
    # Self-employed has higher income variance
    rows["income_variance"][personas == "self_employed"] *= 1.5

    # DTI: requested instalment / income (rough)
    inst = rows["app_requested_amount"] / np.clip(rows["app_requested_tenure"] / 30, 1, 6)
    rows["income_dti"] = np.clip(inst / np.clip(income_estimated, 1, None), 0, 5)
    rows["income_disposable"] = np.clip(income_estimated - inst, -200_000, 5_000_000)

    # Bank statement signals
    rows["bank_avg_balance"] = _truncated_normal(
        rng, income_estimated * 0.4, income_estimated * 0.3, 0, 5_000_000, cfg.n
    )
    rows["bank_avg_monthly_credit"] = _truncated_normal(
        rng, income_estimated * 1.05, income_estimated * 0.25, 0, 5_000_000, cfg.n
    )
    rows["bank_avg_monthly_debit"] = _truncated_normal(
        rng, income_estimated * 0.95, income_estimated * 0.25, 0, 5_000_000, cfg.n
    )
    # Salaried personas have a clearer monthly salary cadence
    rows["bank_salary_frequency"] = np.where(
        np.isin(personas, ["salary_earner", "public_sector"]),
        _truncated_normal(rng, 0.85, 0.15, 0, 1, cfg.n),
        _truncated_normal(rng, 0.30, 0.25, 0, 1, cfg.n),
    )
    rows["bank_gambling_txns"] = rng.poisson(0.6, cfg.n).astype(np.int16)
    # 1xBet-heavy users
    heavy_gamblers = _bernoulli(rng, 0.04, cfg.n)
    rows["bank_gambling_txns"] += heavy_gamblers * rng.integers(8, 30, cfg.n)
    rows["bank_other_lenders"] = rng.poisson(1.3, cfg.n).astype(np.int16)
    rows["bank_zero_balance_days"] = rng.poisson(4.0, cfg.n).astype(np.int16)
    rows["bank_overdraft_count"] = rng.poisson(0.4, cfg.n).astype(np.int16)
    rows["bank_months_covered"] = rng.choice([1, 2, 3, 6], cfg.n).astype(np.int8)

    # Fraud composite signals (each component on 0-100 scale)
    rows["fraud_identity_score"] = _truncated_normal(rng, 80, 12, 0, 100, cfg.n)
    rows["fraud_digital_score"] = _truncated_normal(rng, 75, 15, 0, 100, cfg.n)
    rows["fraud_geo_score"] = _truncated_normal(rng, 78, 14, 0, 100, cfg.n)
    rows["fraud_device_score"] = _truncated_normal(rng, 82, 12, 0, 100, cfg.n)
    rows["fraud_composite"] = (
        rows["fraud_identity_score"] * 0.30
        + rows["fraud_digital_score"] * 0.25
        + rows["fraud_geo_score"] * 0.20
        + rows["fraud_device_score"] * 0.25
    )
    rows["fraud_graph_connected_defaulters"] = rng.poisson(0.2, cfg.n).astype(np.int16)

    # Employment markers
    rows["emp_is_salaried"] = np.isin(
        personas, ["salary_earner", "public_sector", "nysc"]
    ).astype(np.int8)
    rows["emp_has_ippis"] = (
        (personas == "public_sector") & _bernoulli(rng, 0.6, cfg.n).astype(bool)
    ).astype(np.int8)
    rows["emp_has_employer"] = (
        rows["emp_is_salaried"] & _bernoulli(rng, 0.85, cfg.n)
    ).astype(np.int8)

    # ----------------------------------------------------------------------- #
    # Latent default model — relationships the ML must learn                  #
    # ----------------------------------------------------------------------- #
    log_odds = np.zeros(cfg.n)
    log_odds += -1.6  # base intercept

    # Persona offset
    for p in PERSONAS:
        mask = personas == p
        # Convert base PD to log-odds offset
        base = PERSONA_BASE_PD[p]
        log_odds[mask] += np.log(base / (1 - base)) - np.log(0.18 / 0.82)

    # On-time history is the strongest negative-default signal
    log_odds += -2.5 * (rows["user_on_time_pct"] - 0.5)
    log_odds += -0.20 * rows["user_ladder_tier"]
    log_odds += -0.05 * np.minimum(rows["user_consecutive_on_time"], 12)

    # Income / affordability
    log_odds += -0.0000035 * rows["income_disposable"]
    log_odds += +1.30 * np.clip(rows["income_dti"], 0, 2.5)
    log_odds += -0.45 * rows["income_confidence"]

    # Bank pattern
    log_odds += +0.05 * np.minimum(rows["bank_gambling_txns"], 30)
    log_odds += +0.12 * np.minimum(rows["bank_other_lenders"], 8)
    log_odds += +0.04 * np.minimum(rows["bank_zero_balance_days"], 30)
    log_odds += -0.6 * rows["bank_salary_frequency"]
    log_odds += -0.0000020 * np.clip(rows["bank_avg_balance"], 0, 1_000_000)

    # Fraud
    log_odds += -0.025 * (rows["fraud_composite"] - 50)
    log_odds += +0.45 * np.minimum(rows["fraud_graph_connected_defaulters"], 5)

    # Employment / IPPIS payroll deduction → strong negative
    log_odds += -0.55 * rows["emp_has_ippis"]
    log_odds += -0.20 * rows["emp_is_salaried"]

    # Demographics — small effect
    log_odds += -0.012 * (rows["demo_age_years"] - 30)
    log_odds += +0.12 * np.minimum(rows["demo_dependant_count"], 5)

    # Noise
    log_odds += rng.normal(0, 0.55, cfg.n)

    pd_true = 1.0 / (1.0 + np.exp(-log_odds))
    y = (rng.random(cfg.n) < pd_true).astype(np.int8)

    # Stack into ordered matrix
    X = np.column_stack([rows[f] for f in FEATURES]).astype(np.float32)

    log.info(
        "Generated %d rows; overall default rate = %.3f",
        cfg.n, y.mean(),
    )
    for p in PERSONAS:
        mask = personas == p
        if mask.any():
            log.info(
                "  %-15s n=%-6d default_rate=%.3f",
                p, mask.sum(), y[mask].mean(),
            )

    return X, y, personas


# --------------------------------------------------------------------------- #
# Training                                                                    #
# --------------------------------------------------------------------------- #

def train_persona(X, y, persona_name: str, out_dir: Path) -> dict:
    """Train, evaluate, and persist one persona model. Returns metrics."""
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split

    if len(np.unique(y)) < 2:
        log.warning("Persona %s has single class — skipping", persona_name)
        return {"persona": persona_name, "skipped": True}

    X_tr, X_va, y_tr, y_va = train_test_split(
        X, y, test_size=0.2, random_state=7, stratify=y
    )

    train_ds = lgb.Dataset(X_tr, y_tr, feature_name=FEATURES)
    valid_ds = lgb.Dataset(X_va, y_va, feature_name=FEATURES, reference=train_ds)

    params = {
        "objective": "binary",
        "metric": "auc",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 80,
        "feature_fraction": 0.85,
        "bagging_fraction": 0.85,
        "bagging_freq": 5,
        "lambda_l2": 1.0,
        "verbosity": -1,
        "seed": 7,
    }

    booster = lgb.train(
        params,
        train_ds,
        num_boost_round=400,
        valid_sets=[valid_ds],
        callbacks=[lgb.early_stopping(30), lgb.log_evaluation(0)],
    )

    pred_va = booster.predict(X_va)
    auc = float(roc_auc_score(y_va, pred_va))
    ks = _ks_statistic(y_va, pred_va)

    model_name = f"{persona_name}_credit_v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / f"{model_name}.json"
    meta_path = out_dir / f"{model_name}.meta.json"

    booster.save_model(str(model_path))

    meta = {
        "version": "v1",
        "persona": persona_name,
        "feature_names": FEATURES,
        "is_champion": True,
        "training": {
            "n_train": int(len(X_tr)),
            "n_valid": int(len(X_va)),
            "default_rate_train": float(y_tr.mean()),
            "default_rate_valid": float(y_va.mean()),
            "auc": auc,
            "ks": ks,
            "best_iteration": int(booster.best_iteration or 0),
        },
        # Calibration intentionally omitted — synthetic AUC is meaningful but
        # the absolute PD is not. When real labels exist, fit Platt or isotonic
        # on a hold-out and store {"a": ..., "b": ...} here.
        "calibration": None,
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    log.info(
        "  %-15s AUC=%.3f  KS=%.3f  best_iter=%d  saved=%s",
        persona_name, auc, ks, meta["training"]["best_iteration"], model_path.name,
    )
    return {"persona": persona_name, "auc": auc, "ks": ks}


def _ks_statistic(y_true, y_score) -> float:
    """KS statistic = max separation between cumulative dists of 1s vs 0s."""
    order = np.argsort(-np.asarray(y_score))
    y_sorted = np.asarray(y_true)[order]
    cum_pos = np.cumsum(y_sorted) / max(y_sorted.sum(), 1)
    cum_neg = np.cumsum(1 - y_sorted) / max((1 - y_sorted).sum(), 1)
    return float(np.max(np.abs(cum_pos - cum_neg)))


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=40_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "models"),
    )
    args = parser.parse_args()

    cfg = GenConfig(n=args.n, seed=args.seed, out_dir=Path(args.out))
    log.info("Output dir: %s", cfg.out_dir)

    X, y, personas = generate_dataset(cfg)

    summary = []
    for p in PERSONAS:
        mask = personas == p
        log.info("Training %s (%d rows)", p, mask.sum())
        if mask.sum() < 500:
            log.warning("  too few rows for %s — pooling with full dataset", p)
            metrics = train_persona(X, y, p, cfg.out_dir)
        else:
            metrics = train_persona(X[mask], y[mask], p, cfg.out_dir)
        summary.append(metrics)

    summary_path = cfg.out_dir / "_training_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "n": cfg.n,
                "seed": cfg.seed,
                "feature_count": len(FEATURES),
                "models": summary,
            },
            indent=2,
        )
    )
    log.info("Wrote summary: %s", summary_path)


if __name__ == "__main__":
    sys.exit(main())
