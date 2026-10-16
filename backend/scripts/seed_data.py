"""
Seed script — Populates the database with risk tiers, loan ladder config, and test users.

Usage:
    python -m scripts.seed_data

Run after: alembic upgrade head
"""
import asyncio
import sys
import os
from uuid import uuid4
from datetime import datetime, date, timedelta

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import get_settings
from app.core.database import Base

settings = get_settings()


async def seed():
    engine = create_async_engine(settings.DATABASE_URL)

    # Create tables if not exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        await seed_risk_tiers(db)
        await seed_loan_ladder(db)
        await seed_collection_tiers(db)
        await seed_test_users(db)
        await db.commit()
        print("\n✅ Database seeded successfully!")

    await engine.dispose()


async def seed_risk_tiers(db):
    """Seed 17 risk tiers (FairMoney-style)."""
    from app.models.risk import RiskTier

    tiers = [
        (1, "A+", 780, 850, 0.030, 0.005, 1_000_000, 180, True),
        (2, "A",  720, 779, 0.038, 0.008, 750_000, 150, True),
        (3, "A-", 680, 719, 0.045, 0.012, 500_000, 120, True),
        (4, "B+", 650, 679, 0.052, 0.018, 400_000, 90, True),
        (5, "B",  620, 649, 0.060, 0.025, 350_000, 90, True),
        (6, "B-", 590, 619, 0.070, 0.032, 300_000, 60, True),
        (7, "C+", 560, 589, 0.080, 0.041, 250_000, 60, False),
        (8, "C",  530, 559, 0.095, 0.050, 200_000, 45, False),
        (9, "C-", 500, 529, 0.110, 0.062, 150_000, 30, False),
        (10, "D+", 470, 499, 0.125, 0.075, 100_000, 30, False),
        (11, "D",  440, 469, 0.140, 0.090, 80_000, 30, False),
        (12, "D-", 410, 439, 0.155, 0.110, 60_000, 30, False),
        (13, "E+", 380, 409, 0.170, 0.130, 50_000, 14, False),
        (14, "E",  350, 379, 0.190, 0.160, 40_000, 14, False),
        (15, "E-", 320, 349, 0.210, 0.190, 30_000, 14, False),
        (16, "F",  300, 319, 0.240, 0.240, 20_000, 14, False),
        (17, "F-", 0, 299, 0.000, 0.300, 0, 0, False),  # Auto-reject
    ]

    for t in tiers:
        tier = RiskTier(
            tier_number=t[0], tier_name=t[1],
            min_score=t[2], max_score=t[3],
            interest_rate_monthly=t[4],
            expected_npl_rate=t[5],
            max_loan_amount=t[6],
            max_tenure_days=t[7],
            auto_approve=t[8],
            is_active=True,
        )
        db.add(tier)

    print(f"  Seeded {len(tiers)} risk tiers")


async def seed_loan_ladder(db):
    """Seed 7-tier loan ladder configuration."""
    from app.models.loan import LoanLadder

    ladders = [
        # tier, min_loans, min_on_time%, max_salary, max_self_emp, max_public, max_nysc, rate_discount
        (1, 0, 0.0, 50_000, 30_000, 50_000, 20_000, 0.000),
        (2, 1, 0.80, 100_000, 70_000, 100_000, 40_000, 0.005),
        (3, 3, 0.85, 200_000, 150_000, 200_000, 80_000, 0.010),
        (4, 5, 0.90, 350_000, 250_000, 350_000, 120_000, 0.015),
        (5, 8, 0.90, 500_000, 400_000, 500_000, 150_000, 0.020),
        (6, 12, 0.95, 750_000, 600_000, 750_000, 200_000, 0.025),
        (7, 18, 0.95, 1_000_000, 800_000, 1_000_000, 250_000, 0.030),
    ]

    for l in ladders:
        ladder = LoanLadder(
            tier=l[0],
            min_loans_required=l[1],
            min_on_time_percentage=l[2],
            max_amount_salary_earner=l[3],
            max_amount_self_employed=l[4],
            max_amount_public_sector=l[5],
            max_amount_nysc=l[6],
            rate_discount=l[7],
            is_active=True,
        )
        db.add(ladder)

    print(f"  Seeded {len(ladders)} loan ladder tiers")


async def seed_collection_tiers(db):
    """Seed DPD-based collection tiers."""
    from app.models.collections import CollectionTier

    tiers = [
        ("Soft Reminder", 1, 7, "push_notification,sms", "automated", "soft_reminder"),
        ("IVR Campaign", 8, 15, "sms,ivr", "automated", "ivr_reminder"),
        ("Agent Outreach", 16, 30, "phone_call,email", "manual", "agent_script"),
        ("Field Collection", 31, 60, "phone_call,whatsapp,field_visit", "manual", "field_visit"),
        ("Legal", 61, 90, "legal_notice,phone_call", "legal", "legal_notice"),
    ]

    for t in tiers:
        tier = CollectionTier(
            tier_name=t[0],
            dpd_min=t[1], dpd_max=t[2],
            channels=t[3],
            assignment_type=t[4],
            default_template=t[5],
            is_active=True,
        )
        db.add(tier)

    print(f"  Seeded {len(tiers)} collection tiers")


async def seed_test_users(db):
    """Seed test users for each persona type."""
    from app.models.user import User, UserKYC, UserStatus, KYCStatus, Tier, Persona
    import bcrypt

    password_hash = bcrypt.hashpw("testpassword123".encode(), bcrypt.gensalt()).decode()

    test_users = [
        ("Adebayo", "Okonkwo", "08012345001", "adebayo@test.com", Persona.SALARY_EARNER, Tier.TIER_3, 3),
        ("Chidinma", "Eze", "08012345002", "chidinma@test.com", Persona.SELF_EMPLOYED, Tier.TIER_2, 2),
        ("Tunde", "Bakare", "08012345003", "tunde@test.com", Persona.PUBLIC_SECTOR, Tier.TIER_3, 4),
        ("Aisha", "Abdullahi", "08012345004", "aisha@test.com", Persona.NYSC, Tier.TIER_1, 1),
        ("Admin", "User", "08099999999", "admin@sharpsharp.com", Persona.SALARY_EARNER, Tier.TIER_3, 5),
    ]

    for u in test_users:
        user = User(
            first_name=u[0], last_name=u[1],
            phone_number=u[2], email=u[3],
            password_hash=password_hash,
            status=UserStatus.ACTIVE,
            persona=u[4], tier=u[5],
            ladder_tier=u[6],
            total_loans_taken=u[6] * 2,
            total_loans_repaid_on_time=u[6] * 2 - 1,
            consecutive_on_time_repayments=u[6],
            is_existing_customer=True,
            is_admin=(u[0] == "Admin"),
            declared_monthly_income=150_000 if u[4] != Persona.NYSC else 33_000,
        )
        db.add(user)

    print(f"  Seeded {len(test_users)} test users (password: testpassword123)")
    print(f"  Admin login: 08099999999 / testpassword123")


if __name__ == "__main__":
    print("🌱 Seeding Sharp Sharp Lending Platform database...\n")
    asyncio.run(seed())
