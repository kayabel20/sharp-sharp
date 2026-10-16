"""User, KYC, Device, and Address models."""
import uuid
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Date,
    ForeignKey, Text, Enum, JSON, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class UserStatus(str, PyEnum):
    PENDING = "pending"
    KYC_IN_PROGRESS = "kyc_in_progress"
    KYC_VERIFIED = "kyc_verified"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLACKLISTED = "blacklisted"


class KYCStatus(str, PyEnum):
    NOT_STARTED = "not_started"
    BVN_VERIFIED = "bvn_verified"
    NIN_VERIFIED = "nin_verified"
    SELFIE_VERIFIED = "selfie_verified"
    ADDRESS_VERIFIED = "address_verified"
    FULLY_VERIFIED = "fully_verified"
    FAILED = "failed"


class Gender(str, PyEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class Persona(str, PyEnum):
    SALARY_EARNER = "salary_earner"
    SELF_EMPLOYED = "self_employed"
    PUBLIC_SECTOR = "public_sector"
    NYSC = "nysc"
    STUDENT = "student"
    UNKNOWN = "unknown"


class Tier(str, PyEnum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Basic info
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    middle_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(Enum(Gender), nullable=True)

    # Status
    status = Column(Enum(UserStatus), default=UserStatus.PENDING, nullable=False)
    tier = Column(Enum(Tier), default=Tier.TIER_1, nullable=False)
    persona = Column(Enum(Persona), default=Persona.UNKNOWN, nullable=True)
    is_existing_customer = Column(Boolean, default=False)

    # Auth
    password_hash = Column(String(255), nullable=True)
    pin_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)

    # Employment
    employment_status = Column(String(50), nullable=True)
    employment_sector = Column(String(100), nullable=True)
    employer_name = Column(String(200), nullable=True)
    staff_id = Column(String(100), nullable=True)
    ippis_number = Column(String(100), nullable=True)
    state_payroll_id = Column(String(100), nullable=True)

    # Income (self-reported)
    declared_monthly_income = Column(Float, nullable=True)
    pay_day = Column(Integer, nullable=True)  # Day of month
    side_income = Column(Float, nullable=True)
    source_of_funds = Column(String(100), nullable=True)
    purpose_of_account = Column(String(100), nullable=True)

    # Verified income sources
    ippis_salary = Column(Float, nullable=True)
    employer_verified_income = Column(Float, nullable=True)

    # Personal
    marital_status = Column(String(20), nullable=True)
    number_of_dependants = Column(Integer, nullable=True)
    education_level = Column(String(50), nullable=True)

    # Next of Kin
    nok_name = Column(String(200), nullable=True)
    nok_phone = Column(String(20), nullable=True)
    nok_relationship = Column(String(50), nullable=True)

    # Loan Ladder
    ladder_tier = Column(Integer, default=1, nullable=False)
    total_loans_taken = Column(Integer, default=0)
    total_loans_repaid_on_time = Column(Integer, default=0)
    consecutive_on_time_repayments = Column(Integer, default=0)

    # Referral
    referral_code = Column(String(50), nullable=True, index=True)

    # Linked bank account (set by Mono/Okra Connect flow)
    mono_account_id = Column(String(100), nullable=True, index=True)
    mono_linked_at = Column(DateTime, nullable=True)
    okra_account_id = Column(String(100), nullable=True, index=True)
    okra_linked_at = Column(DateTime, nullable=True)
    linked_bank_name = Column(String(100), nullable=True)
    linked_account_name = Column(String(200), nullable=True)
    linked_account_number = Column(String(20), nullable=True)

    # Relationships
    kyc = relationship("UserKYC", back_populates="user", uselist=False)
    devices = relationship("UserDevice", back_populates="user")
    addresses = relationship("UserAddress", back_populates="user")
    loan_applications = relationship("LoanApplication", back_populates="user")
    loans = relationship("Loan", back_populates="user")

    __table_args__ = (
        Index("ix_users_phone_status", "phone_number", "status"),
        Index("ix_users_persona", "persona"),
        Index("ix_users_ladder", "ladder_tier"),
    )


class UserKYC(Base):
    __tablename__ = "user_kyc"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # KYC Status
    status = Column(Enum(KYCStatus), default=KYCStatus.NOT_STARTED, nullable=False)

    # BVN
    bvn = Column(String(20), nullable=True, index=True)
    bvn_verified = Column(Boolean, default=False)
    bvn_first_name = Column(String(100), nullable=True)
    bvn_last_name = Column(String(100), nullable=True)
    bvn_phone = Column(String(20), nullable=True)
    bvn_dob = Column(Date, nullable=True)
    bvn_verification_date = Column(DateTime, nullable=True)
    bvn_match_score = Column(Float, nullable=True)

    # NIN
    nin = Column(String(20), nullable=True, index=True)
    nin_verified = Column(Boolean, default=False)
    nin_first_name = Column(String(100), nullable=True)
    nin_last_name = Column(String(100), nullable=True)
    nin_verification_date = Column(DateTime, nullable=True)

    # Selfie / Biometrics
    selfie_verified = Column(Boolean, default=False)
    selfie_liveness_score = Column(Float, nullable=True)
    selfie_match_score = Column(Float, nullable=True)  # Match against BVN photo
    selfie_verification_date = Column(DateTime, nullable=True)
    govt_id_type = Column(String(50), nullable=True)
    govt_id_verified = Column(Boolean, default=False)

    # Proof of Address (for Tier 3)
    address_document_type = Column(String(50), nullable=True)
    address_verified = Column(Boolean, default=False)
    address_verification_date = Column(DateTime, nullable=True)
    address_document_url = Column(String(500), nullable=True)

    # MetaMap reference
    metamap_verification_id = Column(String(100), nullable=True)
    metamap_flow_id = Column(String(100), nullable=True)
    metamap_raw_response = Column(JSON, nullable=True)

    # Relationships
    user = relationship("User", back_populates="kyc")


class UserDevice(Base):
    __tablename__ = "user_devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Device info
    device_id = Column(String(255), nullable=False, index=True)
    device_type = Column(String(50), nullable=True)  # android, ios, web
    device_model = Column(String(100), nullable=True)
    device_os = Column(String(50), nullable=True)
    device_os_version = Column(String(20), nullable=True)
    app_version = Column(String(20), nullable=True)

    # Fingerprinting
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    fingerprint_hash = Column(String(255), nullable=True, index=True)

    # CredoLab data
    credolab_reference_id = Column(String(100), nullable=True)
    credolab_score = Column(Float, nullable=True)
    credolab_data = Column(JSON, nullable=True)

    # Geolocation
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    geo_city = Column(String(100), nullable=True)
    geo_state = Column(String(100), nullable=True)

    is_primary = Column(Boolean, default=False)
    is_flagged = Column(Boolean, default=False)
    flag_reason = Column(String(255), nullable=True)

    # Relationships
    user = relationship("User", back_populates="devices")

    __table_args__ = (
        Index("ix_device_fingerprint", "fingerprint_hash"),
        Index("ix_device_user", "user_id", "is_primary"),
    )


class UserAddress(Base):
    __tablename__ = "user_addresses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    address_line = Column(String(500), nullable=False)
    city = Column(String(100), nullable=True)
    lga = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(50), default="NG")
    postal_code = Column(String(20), nullable=True)

    residential_status = Column(String(50), nullable=True)  # owned, rented, family
    years_at_address = Column(Integer, nullable=True)
    is_primary = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Relationships
    user = relationship("User", back_populates="addresses")
