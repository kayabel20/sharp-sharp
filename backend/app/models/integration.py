"""Integration models — Bank statements, transactions, payments, and audit logs."""
import uuid
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Date,
    ForeignKey, Text, Enum, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class PaymentDirection(str, PyEnum):
    DISBURSEMENT = "disbursement"
    REPAYMENT = "repayment"
    REFUND = "refund"
    FEE = "fee"


class PaymentStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    REVERSED = "reversed"
    TIMEOUT = "timeout"


class BankStatement(Base):
    """Bank statement analysis from Indicina/Mono/Okra."""
    __tablename__ = "bank_statements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Provider
    provider = Column(String(50), nullable=False)  # "indicina", "mono", "okra"
    provider_reference = Column(String(100), nullable=True)
    account_id = Column(String(100), nullable=True)

    # Account info
    bank_name = Column(String(100), nullable=True)
    account_number = Column(String(20), nullable=True)
    account_name = Column(String(200), nullable=True)
    account_type = Column(String(50), nullable=True)
    currency = Column(String(5), default="NGN")

    # Statement period
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    months_covered = Column(Integer, nullable=True)

    # Summary analytics
    average_balance = Column(Float, nullable=True)
    average_monthly_credit = Column(Float, nullable=True)
    average_monthly_debit = Column(Float, nullable=True)
    highest_balance = Column(Float, nullable=True)
    lowest_balance = Column(Float, nullable=True)

    # Income patterns
    salary_frequency = Column(String(20), nullable=True)  # "monthly", "biweekly", "irregular"
    estimated_salary = Column(Float, nullable=True)
    salary_employer = Column(String(200), nullable=True)
    salary_day_of_month = Column(Integer, nullable=True)
    recurring_credits_count = Column(Integer, nullable=True)

    # Spend patterns
    gambling_transactions = Column(Integer, default=0)
    loan_repayments_detected = Column(Integer, default=0)
    other_lender_count = Column(Integer, default=0)

    # Risk indicators
    days_with_zero_balance = Column(Integer, nullable=True)
    overdraft_count = Column(Integer, nullable=True)
    return_cheque_count = Column(Integer, nullable=True)
    sweep_count = Column(Integer, nullable=True)  # Large rapid withdrawals

    # Affordability
    net_monthly_income = Column(Float, nullable=True)
    net_monthly_expenses = Column(Float, nullable=True)
    disposable_income = Column(Float, nullable=True)
    affordability_score = Column(Float, nullable=True)

    # Raw data
    raw_response = Column(JSON, nullable=True)
    transaction_count = Column(Integer, nullable=True)
    status = Column(String(20), default="success")

    __table_args__ = (
        Index("ix_bank_stmt_user", "user_id"),
        Index("ix_bank_stmt_application", "application_id"),
    )


class BankTransaction(Base):
    """Individual bank transactions from statement analysis."""
    __tablename__ = "bank_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id = Column(UUID(as_uuid=True), ForeignKey("bank_statements.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    transaction_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    transaction_type = Column(String(20), nullable=False)  # "credit", "debit"
    narration = Column(Text, nullable=True)
    balance_after = Column(Float, nullable=True)

    # Categorization
    category = Column(String(50), nullable=True)  # "salary", "transfer", "bill", "loan"
    sub_category = Column(String(50), nullable=True)
    is_recurring = Column(Boolean, default=False)
    is_salary = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_bank_txn_user_date", "user_id", "transaction_date"),
        Index("ix_bank_txn_statement", "statement_id"),
    )


class PaymentTransaction(Base):
    """Payment transactions — disbursements and repayments via Flutterwave etc."""
    __tablename__ = "payment_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Reference
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=True)
    application_id = Column(UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=True)

    # Transaction
    direction = Column(Enum(PaymentDirection), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(5), default="NGN")
    fee = Column(Float, default=0.0)

    # Provider
    provider = Column(String(50), nullable=False)  # "flutterwave", "paystack"
    provider_reference = Column(String(100), nullable=True, index=True)
    provider_status = Column(String(50), nullable=True)

    # Account
    bank_code = Column(String(20), nullable=True)
    account_number = Column(String(20), nullable=True)
    account_name = Column(String(200), nullable=True)

    # Status
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    failure_reason = Column(String(255), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Retry
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_retry_at = Column(DateTime, nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSON, nullable=True)

    __table_args__ = (
        Index("ix_payment_user", "user_id"),
        Index("ix_payment_loan", "loan_id"),
        Index("ix_payment_provider_ref", "provider_reference"),
        Index("ix_payment_status", "status", "direction"),
    )


class IntegrationLog(Base):
    """Audit log for all external API calls."""
    __tablename__ = "integration_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Context
    user_id = Column(UUID(as_uuid=True), nullable=True)
    application_id = Column(UUID(as_uuid=True), nullable=True)

    # Request
    service = Column(String(50), nullable=False)  # "flutterwave", "crc", "metamap"
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)  # GET, POST
    request_body = Column(JSON, nullable=True)
    request_headers = Column(JSON, nullable=True)

    # Response
    status_code = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    response_time_ms = Column(Float, nullable=True)

    # Status
    success = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_intlog_service", "service", "created_at"),
        Index("ix_intlog_user", "user_id"),
    )
