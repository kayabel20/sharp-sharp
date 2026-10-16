"""Risk, Scoring, Bureau, Fraud, Income, and Feature models."""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Text, Enum, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class BureauProvider(str, PyEnum):
    CRC = "crc"
    FIRST_CENTRAL = "first_central"
    CREDIT_REGISTRY = "credit_registry"


class FraudDecision(str, PyEnum):
    PASS = "pass"
    REVIEW = "review"
    KNOCKOFF = "knockoff"


class CreditBureauReport(Base):
    """Credit bureau reports from CRC, FirstCentral, CreditRegistry."""
    __tablename__ = "credit_bureau_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Bureau
    provider = Column(Enum(BureauProvider), nullable=False)
    reference_id = Column(String(100), nullable=True)

    # Score
    bureau_score = Column(Float, nullable=True)
    score_band = Column(String(20), nullable=True)  # e.g., "A", "B", "C"
    meets_cutoff = Column(Boolean, nullable=True)
    cutoff_score = Column(Float, nullable=True)

    # Credit history
    total_accounts = Column(Integer, nullable=True)
    active_accounts = Column(Integer, nullable=True)
    closed_accounts = Column(Integer, nullable=True)
    delinquent_accounts = Column(Integer, nullable=True)

    total_outstanding = Column(Float, nullable=True)
    total_overdue = Column(Float, nullable=True)
    worst_delinquency_days = Column(Integer, nullable=True)

    # Existing loans at existing
    has_existing_loan = Column(Boolean, default=False)
    existing_loan_balance = Column(Float, nullable=True)
    existing_loan_type = Column(String(50), nullable=True)
    existing_product_type = Column(String(50), nullable=True)

    # Inquiry details
    recent_inquiries_30d = Column(Integer, nullable=True)
    recent_inquiries_90d = Column(Integer, nullable=True)

    # Raw response
    raw_response = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    status = Column(String(20), default="success")  # success, failed, timeout

    __table_args__ = (
        Index("ix_bureau_user_provider", "user_id", "provider"),
        Index("ix_bureau_application", "application_id"),
    )


class FraudScore(Base):
    """Fraud verification scores — 4 sub-scores + composite."""
    __tablename__ = "fraud_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Individual scores (0-100, higher = less risky)
    identity_verification_score = Column(Float, nullable=True)
    identity_cutoff = Column(Float, nullable=True)
    identity_passes = Column(Boolean, nullable=True)

    digital_footprint_score = Column(Float, nullable=True)
    digital_cutoff = Column(Float, nullable=True)
    digital_passes = Column(Boolean, nullable=True)

    geo_location_score = Column(Float, nullable=True)
    geo_cutoff = Column(Float, nullable=True)
    geo_passes = Column(Boolean, nullable=True)

    device_score = Column(Float, nullable=True)
    device_cutoff = Column(Float, nullable=True)
    device_passes = Column(Boolean, nullable=True)

    # Composite
    composite_fraud_score = Column(Float, nullable=True)
    composite_cutoff = Column(Float, nullable=True)

    # Graph DB results (from network analysis)
    graph_fraud_score = Column(Float, nullable=True)
    connected_defaulters = Column(Integer, default=0)
    shared_devices_with_defaulters = Column(Integer, default=0)
    shared_contacts_with_defaulters = Column(Integer, default=0)
    shared_accounts_with_defaulters = Column(Integer, default=0)
    graph_risk_level = Column(String(20), nullable=True)  # low, medium, high, critical

    # CredoLab
    credolab_score = Column(Float, nullable=True)
    credolab_data_points = Column(Integer, nullable=True)

    # Decision
    decision = Column(Enum(FraudDecision), nullable=False)
    knockoff_reason = Column(String(255), nullable=True)
    requires_manual_review = Column(Boolean, default=False)

    # Raw data
    raw_scores = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_fraud_user", "user_id"),
        Index("ix_fraud_application", "application_id"),
    )


class MLScore(Base):
    """ML model credit score — segment-specific."""
    __tablename__ = "ml_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Model info
    model_name = Column(String(100), nullable=False)  # e.g., "salary_earner_v3"
    model_version = Column(String(20), nullable=False)
    model_type = Column(String(50), nullable=True)  # "lightgbm", "xgboost"
    persona_segment = Column(String(50), nullable=True)  # salary_earner, self_employed, etc.

    # Score
    probability_of_default = Column(Float, nullable=False)  # 0.0 - 1.0
    credit_score = Column(Float, nullable=False)  # Scaled score (e.g., 300-850)
    score_band = Column(String(20), nullable=True)  # A, B, C, D, E

    # Risk tier mapping
    risk_tier = Column(Integer, nullable=True)  # 1-17
    risk_tier_name = Column(String(100), nullable=True)  # "Excellent Salary Earner"
    expected_npl_rate = Column(Float, nullable=True)  # Expected NPL for this tier

    # Feature importance (top 10)
    top_features = Column(JSON, nullable=True)

    # Model metadata
    features_used = Column(Integer, nullable=True)
    inference_time_ms = Column(Float, nullable=True)

    # Champion/Challenger
    is_champion = Column(Boolean, default=True)
    experiment_id = Column(String(100), nullable=True)

    __table_args__ = (
        Index("ix_ml_score_user", "user_id"),
        Index("ix_ml_score_application", "application_id"),
        Index("ix_ml_score_model", "model_name", "model_version"),
    )


class RiskTier(Base):
    """Risk tier configuration — 17 tiers with mapped economics."""
    __tablename__ = "risk_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier_number = Column(Integer, nullable=False, unique=True)
    tier_name = Column(String(100), nullable=False)  # "Excellent New Salary"
    persona_segment = Column(String(50), nullable=True)

    # Score range
    min_score = Column(Float, nullable=False)
    max_score = Column(Float, nullable=False)

    # Risk metrics
    expected_npl_rate = Column(Float, nullable=False)
    expected_lgd = Column(Float, default=0.6)  # Loss given default

    # Pricing
    interest_rate_monthly = Column(Float, nullable=False)
    base_rate = Column(Float, nullable=False)
    risk_premium = Column(Float, nullable=False)
    processing_fee_pct = Column(Float, default=0.0)

    # Limits
    max_loan_amount = Column(Float, nullable=True)
    max_tenure_days = Column(Integer, nullable=True)

    # Policy
    auto_approve = Column(Boolean, default=True)
    requires_bureau_check = Column(Boolean, default=True)
    requires_income_verify = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IncomeEstimate(Base):
    """ML-estimated income for a user."""
    __tablename__ = "income_estimates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Estimates
    estimated_monthly_income = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)  # 0.0 - 1.0
    income_band = Column(String(20), nullable=True)  # low, medium, high

    # Breakdown
    salary_income = Column(Float, nullable=True)
    business_income = Column(Float, nullable=True)
    other_income = Column(Float, nullable=True)

    # Comparison
    declared_income = Column(Float, nullable=True)  # User's self-reported
    income_variance = Column(Float, nullable=True)  # % difference
    is_income_inflated = Column(Boolean, nullable=True)

    # Affordability
    estimated_monthly_expenses = Column(Float, nullable=True)
    estimated_disposable_income = Column(Float, nullable=True)
    debt_to_income_ratio = Column(Float, nullable=True)
    max_affordable_emi = Column(Float, nullable=True)

    # Data sources used
    sources = Column(JSON, nullable=True)  # ["indicina", "mono", "sms"]

    # Model info
    model_version = Column(String(20), nullable=True)
    features_used = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_income_user", "user_id"),
        Index("ix_income_application", "application_id"),
    )


class FeatureSnapshot(Base):
    """Snapshot of engineered features at scoring time."""
    __tablename__ = "feature_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Feature data (stored as JSON for flexibility)
    features = Column(JSON, nullable=False)  # {"feat_1": 0.5, "feat_2": 1.0, ...}
    feature_count = Column(Integer, nullable=False)
    feature_version = Column(String(20), nullable=True)

    # Source breakdown
    bureau_features = Column(Integer, default=0)
    bank_features = Column(Integer, default=0)
    device_features = Column(Integer, default=0)
    behavioral_features = Column(Integer, default=0)
    telco_features = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_feature_application", "application_id"),
    )
