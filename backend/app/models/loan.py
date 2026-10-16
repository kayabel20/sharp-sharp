"""Loan, Application, Offer, Repayment, Schedule, and Ladder models."""
import uuid
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Date,
    ForeignKey, Text, Enum, JSON, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class LoanType(str, PyEnum):
    BULLET = "bullet"           # Single repayment
    INSTALLMENT = "installment" # Multiple repayments
    NANO = "nano"               # Small fallback loan


class ApplicationStatus(str, PyEnum):
    DRAFT = "draft"
    KYC_PENDING = "kyc_pending"
    DATA_COLLECTION = "data_collection"
    FRAUD_CHECK = "fraud_check"
    BANK_ANALYSIS = "bank_analysis"
    INCOME_ESTIMATION = "income_estimation"
    ML_SCORING = "ml_scoring"
    BUREAU_CHECK = "bureau_check"
    DECISION_PENDING = "decision_pending"
    HUMAN_REVIEW = "human_review"
    APPROVED = "approved"
    OFFER_GENERATED = "offer_generated"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"
    DISBURSEMENT_PENDING = "disbursement_pending"
    DISBURSED = "disbursed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class LoanStatus(str, PyEnum):
    ACTIVE = "active"
    CURRENT = "current"           # Payments on time
    DELINQUENT_7 = "delinquent_7"
    DELINQUENT_15 = "delinquent_15"
    DELINQUENT_30 = "delinquent_30"
    DELINQUENT_60 = "delinquent_60"
    DELINQUENT_90 = "delinquent_90"
    DEFAULT = "default"           # 90+ DPD
    PAID_OFF = "paid_off"
    WRITTEN_OFF = "written_off"
    RESTRUCTURED = "restructured"


class RepaymentStatus(str, PyEnum):
    SCHEDULED = "scheduled"
    PENDING = "pending"
    PAID = "paid"
    PARTIAL = "partial"
    OVERDUE = "overdue"
    WAIVED = "waived"


class RepaymentFrequency(str, PyEnum):
    ONE_TIME = "one_time"
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class DeclineReason(str, PyEnum):
    FRAUD_KNOCKOFF = "fraud_knockoff"
    AFFORDABILITY_FAIL = "affordability_fail"
    BUREAU_CUTOFF = "bureau_cutoff"
    ML_SCORE_LOW = "ml_score_low"
    INCOME_INSUFFICIENT = "income_insufficient"
    POLICY_VIOLATION = "policy_violation"
    BLACKLISTED = "blacklisted"
    DUPLICATE_APPLICATION = "duplicate_application"


class LoanProduct(Base):
    """Defines available loan products and their parameters."""
    __tablename__ = "loan_products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    name = Column(String(100), nullable=False, unique=True)
    loan_type = Column(Enum(LoanType), nullable=False)
    is_active = Column(Boolean, default=True)

    # Amount limits (NGN)
    min_amount = Column(Float, nullable=False)
    max_amount = Column(Float, nullable=False)

    # Tenure (days)
    min_tenure_days = Column(Integer, nullable=False)
    max_tenure_days = Column(Integer, nullable=False)
    allowed_tenures = Column(JSON, nullable=True)  # e.g., [30, 60, 90]

    # Default pricing (overridden by risk-based pricing)
    base_interest_rate_monthly = Column(Float, nullable=False)  # e.g., 0.183 for 18.3%
    processing_fee_pct = Column(Float, default=0.0)
    rollover_fee_daily_pct = Column(Float, default=0.01)  # 1% daily

    # Repayment
    allowed_frequencies = Column(JSON, nullable=True)  # ["daily","weekly","monthly"]

    # Eligibility
    min_ladder_tier = Column(Integer, default=1)
    allowed_personas = Column(JSON, nullable=True)  # ["salary_earner","self_employed"]
    min_ml_score = Column(Float, nullable=True)

    # Relationships
    applications = relationship("LoanApplication", back_populates="product")


class LoanApplication(Base):
    """Tracks a loan application through the decisioning pipeline."""
    __tablename__ = "loan_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("loan_products.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Request
    requested_amount = Column(Float, nullable=True)
    requested_tenure_days = Column(Integer, nullable=True)
    loan_purpose = Column(String(200), nullable=True)
    repayment_frequency = Column(Enum(RepaymentFrequency), nullable=True)

    # Disbursement account
    disbursement_bank_code = Column(String(20), nullable=True)
    disbursement_account_number = Column(String(20), nullable=True)
    disbursement_account_name = Column(String(200), nullable=True)
    bvn_linked_account = Column(Boolean, default=False)

    # Status tracking
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.DRAFT, nullable=False)
    current_step = Column(String(50), nullable=True)  # Which step in the pipeline
    decline_reason = Column(Enum(DeclineReason), nullable=True)
    decline_details = Column(Text, nullable=True)

    # Pipeline timestamps
    kyc_completed_at = Column(DateTime, nullable=True)
    fraud_checked_at = Column(DateTime, nullable=True)
    bank_analyzed_at = Column(DateTime, nullable=True)
    income_estimated_at = Column(DateTime, nullable=True)
    ml_scored_at = Column(DateTime, nullable=True)
    bureau_checked_at = Column(DateTime, nullable=True)
    decision_made_at = Column(DateTime, nullable=True)
    offer_generated_at = Column(DateTime, nullable=True)
    offer_responded_at = Column(DateTime, nullable=True)
    disbursed_at = Column(DateTime, nullable=True)

    # Scores snapshot at decision time
    ml_score = Column(Float, nullable=True)
    risk_tier = Column(Integer, nullable=True)
    fraud_composite_score = Column(Float, nullable=True)
    income_estimate = Column(Float, nullable=True)
    income_confidence = Column(Float, nullable=True)
    bureau_score = Column(Float, nullable=True)
    affordability_score = Column(Float, nullable=True)

    # Human review
    requires_human_review = Column(Boolean, default=False)
    reviewer_id = Column(UUID(as_uuid=True), nullable=True)
    review_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    # Metadata
    channel = Column(String(20), default="mobile")  # mobile, web, ussd
    ip_address = Column(String(50), nullable=True)
    device_id = Column(String(255), nullable=True)

    # Relationships
    user = relationship("User", back_populates="loan_applications")
    product = relationship("LoanProduct", back_populates="applications")
    offer = relationship("LoanOffer", back_populates="application", uselist=False)
    loan = relationship("Loan", back_populates="application", uselist=False)

    __table_args__ = (
        Index("ix_application_user_status", "user_id", "status"),
        Index("ix_application_created", "created_at"),
    )


class LoanOffer(Base):
    """Generated loan offer after successful decisioning."""
    __tablename__ = "loan_offers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=False, unique=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    # Offer details
    loan_type = Column(Enum(LoanType), nullable=False)
    approved_amount = Column(Float, nullable=False)
    tenure_days = Column(Integer, nullable=False)
    interest_rate_monthly = Column(Float, nullable=False)  # Risk-adjusted rate
    annual_rate = Column(Float, nullable=True)
    processing_fee = Column(Float, default=0.0)
    total_interest = Column(Float, nullable=False)
    total_repayment = Column(Float, nullable=False)
    repayment_frequency = Column(Enum(RepaymentFrequency), nullable=False)
    is_nano = Column(Boolean, default=False)

    # Per-installment
    installment_amount = Column(Float, nullable=False)
    number_of_installments = Column(Integer, nullable=False)
    first_repayment_date = Column(Date, nullable=False)

    # Risk pricing breakdown
    risk_tier = Column(Integer, nullable=True)
    risk_tier_name = Column(String(100), nullable=True)
    base_rate = Column(Float, nullable=True)
    risk_premium = Column(Float, nullable=True)
    persona_adjustment = Column(Float, nullable=True)
    ladder_discount = Column(Float, nullable=True)
    final_rate = Column(Float, nullable=True)

    # Customer response
    is_accepted = Column(Boolean, nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    declined_at = Column(DateTime, nullable=True)

    # Relationships
    application = relationship("LoanApplication", back_populates="offer")


class Loan(Base):
    """Active loan record after disbursement."""
    __tablename__ = "loans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Loan details
    loan_type = Column(Enum(LoanType), nullable=False)
    principal_amount = Column(Float, nullable=False)
    interest_amount = Column(Float, nullable=False)
    processing_fee = Column(Float, default=0.0)
    total_amount_due = Column(Float, nullable=False)
    interest_rate_monthly = Column(Float, nullable=False)
    tenure_days = Column(Integer, nullable=False)
    repayment_frequency = Column(Enum(RepaymentFrequency), nullable=False)

    # Status
    status = Column(Enum(LoanStatus), default=LoanStatus.ACTIVE, nullable=False)
    days_past_due = Column(Integer, default=0)

    # Dates
    disbursement_date = Column(Date, nullable=False)
    maturity_date = Column(Date, nullable=False)
    first_payment_date = Column(Date, nullable=False)
    last_payment_date = Column(Date, nullable=True)
    fully_paid_date = Column(Date, nullable=True)

    # Balances
    outstanding_principal = Column(Float, nullable=False)
    outstanding_interest = Column(Float, nullable=False)
    outstanding_fees = Column(Float, default=0.0)
    total_outstanding = Column(Float, nullable=False)
    total_paid = Column(Float, default=0.0)
    total_rollover_fees = Column(Float, default=0.0)

    # Disbursement
    disbursement_reference = Column(String(100), nullable=True)
    disbursement_bank = Column(String(100), nullable=True)
    disbursement_account = Column(String(20), nullable=True)
    disbursement_status = Column(String(20), nullable=True)

    # Risk snapshot
    risk_tier = Column(Integer, nullable=True)
    ml_score_at_disbursement = Column(Float, nullable=True)
    ladder_tier_at_disbursement = Column(Integer, nullable=True)

    # Relationships
    user = relationship("User", back_populates="loans")
    application = relationship("LoanApplication", back_populates="loan")
    repayments = relationship("LoanRepayment", back_populates="loan")
    schedule = relationship("LoanSchedule", back_populates="loan")

    __table_args__ = (
        Index("ix_loan_user_status", "user_id", "status"),
        Index("ix_loan_dpd", "days_past_due"),
        Index("ix_loan_maturity", "maturity_date"),
        Index("ix_loan_disbursement", "disbursement_date"),
    )


class LoanSchedule(Base):
    """Repayment schedule entries for a loan."""
    __tablename__ = "loan_schedule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False)

    installment_number = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False)
    principal_due = Column(Float, nullable=False)
    interest_due = Column(Float, nullable=False)
    fees_due = Column(Float, default=0.0)
    total_due = Column(Float, nullable=False)

    principal_paid = Column(Float, default=0.0)
    interest_paid = Column(Float, default=0.0)
    fees_paid = Column(Float, default=0.0)
    total_paid = Column(Float, default=0.0)

    status = Column(Enum(RepaymentStatus), default=RepaymentStatus.SCHEDULED)
    paid_date = Column(Date, nullable=True)
    days_late = Column(Integer, default=0)

    # Relationships
    loan = relationship("Loan", back_populates="schedule")

    __table_args__ = (
        Index("ix_schedule_loan_due", "loan_id", "due_date"),
    )


class LoanRepayment(Base):
    """Individual repayment transactions."""
    __tablename__ = "loan_repayments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    amount = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)  # card, bank_transfer, direct_debit
    payment_reference = Column(String(100), nullable=True)
    payment_provider = Column(String(50), nullable=True)  # flutterwave, paystack

    # Allocation
    principal_applied = Column(Float, default=0.0)
    interest_applied = Column(Float, default=0.0)
    fees_applied = Column(Float, default=0.0)
    rollover_applied = Column(Float, default=0.0)

    status = Column(String(20), default="successful")  # successful, failed, reversed
    failure_reason = Column(String(255), nullable=True)

    # Relationships
    loan = relationship("Loan", back_populates="repayments")


class LoanLadder(Base):
    """Loan ladder tier configuration."""
    __tablename__ = "loan_ladder"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier = Column(Integer, nullable=False, unique=True)
    name = Column(String(50), nullable=False)  # "Bronze", "Silver", etc.

    # Limits per persona (JSON: {"salary_earner": 100000, "self_employed": 50000, ...})
    max_amounts = Column(JSON, nullable=False)

    # Tenure options per tier
    max_tenure_days = Column(Integer, nullable=False)
    allowed_tenures = Column(JSON, nullable=True)  # [30, 60, 90, 180]

    # Rate discount for loyalty
    rate_discount_pct = Column(Float, default=0.0)  # e.g., 0.02 = 2% off base rate

    # Promotion criteria
    min_loans_repaid = Column(Integer, nullable=False)
    min_consecutive_on_time = Column(Integer, nullable=False)

    # Priority
    priority_processing = Column(Boolean, default=False)
    skip_bureau_check = Column(Boolean, default=False)  # For very high tiers

    is_active = Column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("tier >= 1 AND tier <= 10", name="valid_tier_range"),
    )
