"""Celery task definitions — DPD updates, collections, ladder promotions."""
import logging
import asyncio
from datetime import datetime, date as date_type
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper to run async code from sync Celery tasks."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.tasks.update_dpd_all_loans")
def update_dpd_all_loans():
    """Update Days Past Due for all active loans."""
    _run_async(_update_dpd())


async def _update_dpd():
    from app.core.database import async_session_factory
    from app.models.loan import Loan, LoanStatus
    from sqlalchemy import select, update

    async with async_session_factory() as db:
        result = await db.execute(
            select(Loan).where(
                Loan.status.in_([
                    LoanStatus.ACTIVE,
                    LoanStatus.DELINQUENT_7,
                    LoanStatus.DELINQUENT_15,
                    LoanStatus.DELINQUENT_30,
                    LoanStatus.DELINQUENT_60,
                    LoanStatus.DELINQUENT_90,
                ])
            )
        )
        loans = result.scalars().all()

        today = date_type.today()
        updated = 0

        for loan in loans:
            if loan.maturity_date and today > loan.maturity_date:
                dpd = (today - loan.maturity_date).days
                loan.days_past_due = dpd

                # Update status based on DPD
                if dpd >= 90:
                    loan.status = LoanStatus.DELINQUENT_90
                elif dpd >= 60:
                    loan.status = LoanStatus.DELINQUENT_60
                elif dpd >= 30:
                    loan.status = LoanStatus.DELINQUENT_30
                elif dpd >= 15:
                    loan.status = LoanStatus.DELINQUENT_15
                elif dpd >= 7:
                    loan.status = LoanStatus.DELINQUENT_7

                updated += 1

        await db.commit()
        logger.info(f"DPD update complete: {updated} loans updated")


@celery_app.task(name="app.workers.tasks.assign_collections")
def assign_collections():
    """Assign delinquent loans to collection tiers."""
    _run_async(_assign_collections())


async def _assign_collections():
    from app.core.database import async_session_factory
    from app.models.loan import Loan, LoanStatus
    from app.models.collections import CollectionTier, CollectionAssignment
    from sqlalchemy import select

    async with async_session_factory() as db:
        # Get all collection tiers
        tiers_result = await db.execute(
            select(CollectionTier).where(CollectionTier.is_active == True)
            .order_by(CollectionTier.min_dpd)
        )
        tiers = tiers_result.scalars().all()

        # Get delinquent loans
        loans_result = await db.execute(
            select(Loan).where(
                Loan.status.in_([
                    LoanStatus.DELINQUENT_7, LoanStatus.DELINQUENT_15,
                    LoanStatus.DELINQUENT_30, LoanStatus.DELINQUENT_60,
                    LoanStatus.DELINQUENT_90,
                ])
            )
        )
        loans = loans_result.scalars().all()

        assigned = 0
        for loan in loans:
            dpd = loan.days_past_due or 0
            # Find matching tier
            matching_tier = None
            for tier in tiers:
                if tier.min_dpd <= dpd <= tier.max_dpd:
                    matching_tier = tier
                    break

            if matching_tier:
                # Check if already assigned to this tier
                existing = await db.execute(
                    select(CollectionAssignment).where(
                        CollectionAssignment.loan_id == loan.id,
                        CollectionAssignment.tier_id == matching_tier.id,
                        CollectionAssignment.is_active == True,
                    )
                )
                if not existing.scalar_one_or_none():
                    assignment = CollectionAssignment(
                        loan_id=loan.id,
                        tier_id=matching_tier.id,
                        dpd_at_assignment=dpd,
                        outstanding_at_assignment=loan.total_outstanding,
                    )
                    db.add(assignment)
                    assigned += 1

        await db.commit()
        logger.info(f"Collections assignment: {assigned} loans assigned")


@celery_app.task(name="app.workers.tasks.check_ladder_promotions")
def check_ladder_promotions():
    """Check and promote users on the loan ladder."""
    _run_async(_check_promotions())


async def _check_promotions():
    from app.core.database import async_session_factory
    from app.models.user import User
    from app.models.loan import LoanLadder
    from sqlalchemy import select

    async with async_session_factory() as db:
        # Get users eligible for promotion
        result = await db.execute(
            select(User).where(User.ladder_tier < 7)
        )
        users = result.scalars().all()

        promoted = 0
        for user in users:
            current = user.ladder_tier or 1
            next_tier = current + 1

            # Get next tier requirements
            ladder = await db.execute(
                select(LoanLadder).where(
                    LoanLadder.tier == next_tier,
                    LoanLadder.is_active == True,
                )
            )
            next_ladder = ladder.scalar_one_or_none()
            if not next_ladder:
                continue

            # Check requirements
            meets_loans = (user.total_loans_taken or 0) >= (next_ladder.min_loans_repaid or 0)
            meets_pct = (user.consecutive_on_time_repayments or 0) >= (next_ladder.min_consecutive_on_time or 0)

            if meets_loans and meets_pct:
                user.ladder_tier = next_tier
                promoted += 1

        await db.commit()
        logger.info(f"Ladder promotions: {promoted} users promoted")


@celery_app.task(name="app.workers.tasks.expire_old_offers")
def expire_old_offers():
    """Expire loan offers past their validity window."""
    _run_async(_expire_offers())


async def _expire_offers():
    from app.core.database import async_session_factory
    from app.models.loan import LoanOffer, LoanApplication, ApplicationStatus
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(LoanOffer).where(
                LoanOffer.is_accepted == False,
                LoanOffer.expires_at < datetime.utcnow(),
            )
        )
        offers = result.scalars().all()

        expired = 0
        for offer in offers:
            # Update application status
            app = await db.get(LoanApplication, offer.application_id)
            if app and app.status == ApplicationStatus.OFFER_GENERATED:
                app.status = ApplicationStatus.EXPIRED
                expired += 1

        await db.commit()
        logger.info(f"Expired {expired} offers")
