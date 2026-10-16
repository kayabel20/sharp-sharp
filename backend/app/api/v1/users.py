"""User profile & KYC endpoints."""
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User, UserKYC
from app.api.deps import get_current_user
from app.services.kyc_service import KYCService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


# ── Schemas ──

class UserProfile(BaseModel):
    id: str
    phone_number: str
    email: str | None
    first_name: str
    last_name: str
    status: str | None
    tier: str | None
    persona: str | None
    ladder_tier: int
    total_loans_taken: int
    total_loans_repaid_on_time: int
    consecutive_on_time_repayments: int
    is_existing_customer: bool
    kyc_status: str | None


class KYCSubmitRequest(BaseModel):
    bvn: str | None = None
    nin: str | None = None


class EmploymentUpdateRequest(BaseModel):
    employment_status: str | None = None
    employer_name: str | None = None
    employer_address: str | None = None
    monthly_income: float | None = None
    ippis_number: str | None = None
    state_payroll_id: str | None = None


# ── Endpoints ──

@router.get("/me", response_model=UserProfile)
async def get_profile(user: User = Depends(get_current_user)):
    """Get current user profile."""
    kyc_status = None
    if user.kyc:
        kyc_status = user.kyc.status.value if user.kyc.status else None

    return UserProfile(
        id=str(user.id),
        phone_number=user.phone_number,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        status=user.status.value if user.status else None,
        tier=user.tier.value if user.tier else None,
        persona=user.persona.value if user.persona else None,
        ladder_tier=user.ladder_tier or 1,
        total_loans_taken=user.total_loans_taken or 0,
        total_loans_repaid_on_time=user.total_loans_repaid_on_time or 0,
        consecutive_on_time_repayments=user.consecutive_on_time_repayments or 0,
        is_existing_customer=user.is_existing_customer or False,
        kyc_status=kyc_status,
    )


@router.post("/kyc/submit")
async def submit_kyc(
    req: KYCSubmitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit BVN/NIN for KYC verification."""
    kyc = user.kyc
    if not kyc:
        kyc = UserKYC(user_id=user.id)
        db.add(kyc)

    if req.bvn:
        kyc.bvn = req.bvn
    if req.nin:
        kyc.nin = req.nin

    await db.flush()

    # Run KYC verification
    kyc_service = KYCService(db)
    result = await kyc_service.verify(user)
    await db.commit()

    return result


@router.post("/kyc/selfie")
async def upload_selfie(
    selfie: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload selfie for liveness check (STUB).

    In production: stream to S3, call MetaMap liveness, store result.
    Here: validate type/size, mark KYC selfie_verified.
    """
    if selfie.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Selfie must be jpeg/png/webp")

    contents = await selfie.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Selfie too large (max 5MB)")
    if len(contents) < 5 * 1024:
        raise HTTPException(status_code=400, detail="Selfie too small / corrupt")

    kyc = user.kyc
    if not kyc:
        kyc = UserKYC(user_id=user.id)
        db.add(kyc)

    from datetime import datetime
    kyc.selfie_verified = True
    kyc.selfie_liveness_score = 0.95  # STUB
    kyc.selfie_verification_date = datetime.utcnow()

    kyc_service = KYCService(db)
    result = await kyc_service.verify(user)
    await db.commit()

    logger.info(f"Selfie uploaded for user {user.id}: {len(contents)} bytes (STUB liveness)")
    return {"status": "ok", "size_bytes": len(contents), "kyc": result}


@router.post("/bank/link")
async def link_bank_account(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange Mono/Okra public_token for an account_id and persist on the user.

    Flow:
      1. Frontend Mono Connect widget yields a `code` (public_token) on success.
      2. We POST it to Mono /accounts/auth (server-side, with secret key).
      3. We pull /accounts/{id} for display metadata.
      4. Persist account_id + bank/account info on User so bank_service can
         pull statements at decisioning time.

    When MONO_SECRET_KEY is unset (dev without keys), falls back to the previous
    stub so the rest of the pipeline still works locally.
    """
    from datetime import datetime
    from app.integrations.mono import MonoClient, MonoError

    provider = (payload.get("provider") or "").lower()
    public_token = payload.get("public_token")
    if provider not in ("mono", "okra"):
        raise HTTPException(status_code=400, detail="provider must be 'mono' or 'okra'")
    if not public_token:
        raise HTTPException(status_code=400, detail="public_token required")

    if provider == "okra":
        # Okra is symmetric — implement when Okra keys are wired.
        raise HTTPException(
            status_code=501,
            detail="Okra link not yet implemented; use Mono.",
        )

    client = MonoClient()

    if not client.is_configured:
        # Dev fallback — keeps the front-end happy without sandbox keys.
        logger.info(
            f"Bank link (STUB — MONO_SECRET_KEY unset) user={user.id}"
        )
        user.mono_account_id = f"STUB-{user.id.hex[:8]}"
        user.mono_linked_at = datetime.utcnow()
        user.linked_bank_name = "Stub Bank Plc"
        user.linked_account_name = (user.first_name or "User") + " " + (user.last_name or "")
        user.linked_account_number = "****1234"
        await db.commit()
        return {
            "status": "linked",
            "provider": provider,
            "account_id": user.mono_account_id,
            "institution": user.linked_bank_name,
            "masked_account_number": user.linked_account_number,
            "note": "Stubbed — set MONO_SECRET_KEY to enable real linking",
        }

    try:
        exchange = await client.exchange_token(public_token)
        account_id = exchange["account_id"]
        details = await client.get_account_details(account_id)
    except MonoError as e:
        logger.warning(
            f"Mono link failed for user {user.id}: {e} status={e.status_code}"
        )
        raise HTTPException(
            status_code=502,
            detail=f"Bank linking failed: {e}",
        )

    user.mono_account_id = account_id
    user.mono_linked_at = datetime.utcnow()
    user.linked_bank_name = details.get("institution")
    user.linked_account_name = details.get("account_name")
    raw_acct = details.get("account_number") or ""
    user.linked_account_number = (
        f"****{raw_acct[-4:]}" if len(raw_acct) >= 4 else raw_acct
    )
    await db.commit()

    logger.info(
        f"Mono linked user={user.id} account_id={account_id} "
        f"bank={user.linked_bank_name}"
    )
    return {
        "status": "linked",
        "provider": provider,
        "account_id": account_id,
        "institution": user.linked_bank_name,
        "account_name": user.linked_account_name,
        "masked_account_number": user.linked_account_number,
        "balance": details.get("balance"),
    }


@router.get("/bank/accounts")
async def list_linked_banks(
    user: User = Depends(get_current_user),
):
    """List linked bank accounts."""
    accounts = []
    if user.mono_account_id:
        accounts.append({
            "provider": "mono",
            "account_id": user.mono_account_id,
            "institution": user.linked_bank_name,
            "account_name": user.linked_account_name,
            "masked_account_number": user.linked_account_number,
            "linked_at": user.mono_linked_at.isoformat() if user.mono_linked_at else None,
        })
    if user.okra_account_id:
        accounts.append({
            "provider": "okra",
            "account_id": user.okra_account_id,
            "institution": user.linked_bank_name,
            "account_name": user.linked_account_name,
            "masked_account_number": user.linked_account_number,
            "linked_at": user.okra_linked_at.isoformat() if user.okra_linked_at else None,
        })
    return accounts


@router.delete("/bank/{provider}")
async def unlink_bank(
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink a previously connected bank account."""
    from app.integrations.mono import MonoClient, MonoError

    provider = provider.lower()
    if provider == "mono":
        if not user.mono_account_id:
            raise HTTPException(status_code=404, detail="No Mono account linked")
        client = MonoClient()
        if client.is_configured and not user.mono_account_id.startswith("STUB-"):
            try:
                await client.unlink_account(user.mono_account_id)
            except MonoError as e:
                logger.warning(f"Mono unlink failed user={user.id}: {e}")
        user.mono_account_id = None
        user.mono_linked_at = None
    elif provider == "okra":
        user.okra_account_id = None
        user.okra_linked_at = None
    else:
        raise HTTPException(status_code=400, detail="Unknown provider")

    if not user.mono_account_id and not user.okra_account_id:
        user.linked_bank_name = None
        user.linked_account_name = None
        user.linked_account_number = None

    await db.commit()
    return {"status": "unlinked", "provider": provider}


@router.get("/bank/config")
async def bank_link_config():
    """
    Frontend config for the Mono Connect widget.

    Returns the public key (safe to expose) and current statement period.
    Frontend loads this once on the bank-link page to know whether to render
    the real widget or the dev stub.
    """
    from app.core.config import get_settings
    s = get_settings()
    return {
        "mono_public_key": s.MONO_PUBLIC_KEY or None,
        "mono_configured": bool(s.MONO_SECRET_KEY and s.MONO_PUBLIC_KEY),
        "okra_configured": bool(s.OKRA_SECRET_KEY),
        "statement_period": s.MONO_STATEMENT_PERIOD,
    }


@router.put("/employment")
async def update_employment(
    req: EmploymentUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update employment information."""
    if req.employment_status:
        user.employment_status = req.employment_status
    if req.employer_name:
        user.employer_name = req.employer_name
    if req.employer_address:
        user.employer_address = req.employer_address
    if req.monthly_income is not None:
        user.declared_monthly_income = req.monthly_income
    if req.ippis_number:
        user.ippis_number = req.ippis_number
    if req.state_payroll_id:
        user.state_payroll_id = req.state_payroll_id

    await db.commit()
    return {"message": "Employment information updated"}


@router.get("/ladder")
async def get_ladder_info(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's loan ladder progress."""
    from app.models.loan import LoanLadder
    from sqlalchemy import select

    current_tier = user.ladder_tier or 1
    next_tier = min(current_tier + 1, 7)

    # Get next tier requirements
    result = await db.execute(
        select(LoanLadder).where(LoanLadder.tier == next_tier, LoanLadder.is_active == True)
    )
    next_ladder = result.scalar_one_or_none()

    return {
        "current_tier": current_tier,
        "total_loans": user.total_loans_taken or 0,
        "on_time_repayments": user.total_loans_repaid_on_time or 0,
        "consecutive_on_time": user.consecutive_on_time_repayments or 0,
        "next_tier": next_tier if next_tier <= 7 else None,
        "next_tier_requirements": {
            "min_loans": next_ladder.min_loans_required if next_ladder else None,
            "min_on_time_pct": next_ladder.min_on_time_percentage if next_ladder else None,
        } if next_ladder else None,
    }
