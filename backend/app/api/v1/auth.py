"""Authentication endpoints — signup, login, OTP, token refresh."""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import bcrypt

from app.core.database import get_db
from app.models.user import User, UserStatus, Tier
from app.api.deps import create_access_token, create_refresh_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Request/Response Schemas ──

class SignupRequest(BaseModel):
    phone_number: str
    email: EmailStr | None = None
    first_name: str
    last_name: str
    password: str
    referral_code: str | None = None


class LoginRequest(BaseModel):
    phone_number: str
    password: str


class OTPVerifyRequest(BaseModel):
    phone_number: str
    otp: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Endpoints ──

@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    # Check duplicate phone
    existing = await db.execute(
        select(User).where(User.phone_number == req.phone_number)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already registered",
        )

    # Check duplicate email
    if req.email:
        existing_email = await db.execute(
            select(User).where(User.email == req.email)
        )
        if existing_email.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

    # Hash password
    password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()

    user = User(
        phone_number=req.phone_number,
        email=req.email,
        first_name=req.first_name,
        last_name=req.last_name,
        password_hash=password_hash,
        status=UserStatus.PENDING,
        tier=Tier.TIER_1,
        ladder_tier=1,
        referral_code=req.referral_code,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Generate tokens
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))

    logger.info(f"New signup: {user.id} — {req.phone_number}")

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=str(user.id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with phone + password."""
    result = await db.execute(
        select(User).where(User.phone_number == req.phone_number)
    )
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not bcrypt.checkpw(req.password.encode(), user.password_hash.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if user.status and user.status.value == "blacklisted":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended",
        )

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=str(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token."""
    import jwt as pyjwt
    from app.core.config import get_settings
    settings = get_settings()

    try:
        payload = pyjwt.decode(
            req.refresh_token, settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        user_id = payload["sub"]
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=user_id,
    )


@router.post("/otp/send")
async def send_otp(phone_number: str, db: AsyncSession = Depends(get_db)):
    """Send OTP to phone number for verification."""
    # TODO: Integrate Africa's Talking SMS
    return {"message": "OTP sent", "phone_number": phone_number}


@router.post("/otp/verify")
async def verify_otp(req: OTPVerifyRequest, db: AsyncSession = Depends(get_db)):
    """Verify phone OTP."""
    # TODO: Verify against stored OTP
    return {"verified": True, "phone_number": req.phone_number}
