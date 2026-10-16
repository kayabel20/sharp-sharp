"""Collections models — DPD-tiered collection actions and assignments."""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Text, Enum, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class CollectionChannel(str, PyEnum):
    PUSH_NOTIFICATION = "push_notification"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    ROBO_CALL = "robo_call"
    AGENT_CALL = "agent_call"
    EXTERNAL_AGENCY = "external_agency"
    LEGAL = "legal"


class CollectionOutcome(str, PyEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    PROMISE_TO_PAY = "promise_to_pay"
    PARTIAL_PAYMENT = "partial_payment"
    FULL_PAYMENT = "full_payment"
    NO_RESPONSE = "no_response"
    WRONG_NUMBER = "wrong_number"
    REFUSED = "refused"
    ESCALATED = "escalated"


class CollectionTier(Base):
    """DPD-based collection tier configuration."""
    __tablename__ = "collection_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier_name = Column(String(100), nullable=False, unique=True)
    tier_order = Column(Integer, nullable=False, unique=True)

    # DPD range
    min_dpd = Column(Integer, nullable=False)  # e.g., 0
    max_dpd = Column(Integer, nullable=False)  # e.g., 7

    # Channels for this tier
    channels = Column(JSON, nullable=False)  # ["sms", "push_notification", "whatsapp"]
    primary_channel = Column(Enum(CollectionChannel), nullable=False)

    # Assignment
    assignment_type = Column(String(50), nullable=False)  # "automated", "in_house", "outsourced", "legal"
    agency_name = Column(String(200), nullable=True)

    # Frequency
    contact_frequency_days = Column(Integer, nullable=False)  # How often to contact
    max_contacts_per_tier = Column(Integer, nullable=True)

    # Escalation
    auto_escalate = Column(Boolean, default=True)
    escalation_dpd = Column(Integer, nullable=True)  # When to move to next tier

    # Templates
    sms_template = Column(Text, nullable=True)
    whatsapp_template = Column(Text, nullable=True)
    call_script = Column(Text, nullable=True)
    email_template = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)


class CollectionAssignment(Base):
    """Assigns a delinquent loan to a collection tier/agent."""
    __tablename__ = "collection_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False)
    tier_id = Column(UUID(as_uuid=True), ForeignKey("collection_tiers.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Agent
    assigned_to = Column(String(200), nullable=True)  # Agent name or agency
    assigned_at = Column(DateTime, default=datetime.utcnow)

    # Status
    is_active = Column(Boolean, default=True)
    dpd_at_assignment = Column(Integer, nullable=False)
    outstanding_at_assignment = Column(Float, nullable=False)

    # Outcome
    total_collected = Column(Float, default=0.0)
    total_contacts = Column(Integer, default=0)
    last_contact_date = Column(DateTime, nullable=True)
    last_outcome = Column(Enum(CollectionOutcome), nullable=True)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_collection_loan", "loan_id"),
        Index("ix_collection_active", "is_active", "tier_id"),
    )


class CollectionAction(Base):
    """Individual collection action/contact record."""
    __tablename__ = "collection_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("collection_assignments.id"), nullable=False)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Action details
    channel = Column(Enum(CollectionChannel), nullable=False)
    action_type = Column(String(50), nullable=False)  # "reminder", "demand", "final_notice"
    content = Column(Text, nullable=True)  # Message sent
    recipient = Column(String(100), nullable=True)  # Phone/email

    # Result
    outcome = Column(Enum(CollectionOutcome), nullable=False)
    notes = Column(Text, nullable=True)
    promise_date = Column(DateTime, nullable=True)
    promise_amount = Column(Float, nullable=True)

    # Cost
    cost = Column(Float, default=0.0)
    provider = Column(String(50), nullable=True)  # "africastalking", "twilio", etc.
    provider_reference = Column(String(100), nullable=True)

    # Agent
    agent_name = Column(String(200), nullable=True)
    call_duration_seconds = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_action_loan", "loan_id"),
        Index("ix_action_assignment", "assignment_id"),
    )
