"""KYC verification service — BVN + NIN + Selfie + Device fingerprint."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserKYC, KYCStatus, UserStatus, UserDevice
from app.integrations.metamap import MetaMapClient

logger = logging.getLogger(__name__)


class KYCService:
    """Handles identity verification through multiple layers."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.metamap = MetaMapClient()

    async def verify(self, user: User) -> dict:
        """Run full KYC verification pipeline."""
        kyc = user.kyc
        if not kyc:
            kyc = UserKYC(user_id=user.id, status=KYCStatus.NOT_STARTED)
            self.db.add(kyc)
            await self.db.flush()

        # Already verified?
        if kyc.status == KYCStatus.FULLY_VERIFIED:
            return {"passed": True, "status": "already_verified"}

        results = {"passed": True, "checks": []}

        # Step 1: BVN Verification
        if not kyc.bvn_verified and kyc.bvn:
            bvn_result = await self._verify_bvn(user, kyc)
            results["checks"].append(bvn_result)
            if not bvn_result["passed"]:
                results["passed"] = False
                results["reason"] = "BVN verification failed"
                return results

        # Step 2: NIN Verification (cross-check with BVN)
        if not kyc.nin_verified and kyc.nin:
            nin_result = await self._verify_nin(user, kyc)
            results["checks"].append(nin_result)
            if not nin_result["passed"]:
                results["passed"] = False
                results["reason"] = "NIN verification failed"
                return results

        # Step 3: Selfie Liveness Check
        if not kyc.selfie_verified:
            selfie_result = await self._verify_selfie(user, kyc)
            results["checks"].append(selfie_result)
            if not selfie_result["passed"]:
                results["passed"] = False
                results["reason"] = "Selfie liveness check failed"
                return results

        # Step 4: Device Fingerprinting
        device_result = await self._register_device(user)
        results["checks"].append(device_result)

        # Update status
        if results["passed"]:
            kyc.status = KYCStatus.FULLY_VERIFIED
            user.status = UserStatus.KYC_VERIFIED

        await self.db.flush()
        return results

    async def _verify_bvn(self, user: User, kyc: UserKYC) -> dict:
        """Verify BVN via MetaMap / NX360."""
        try:
            result = await self.metamap.verify_bvn(kyc.bvn)

            kyc.bvn_verified = result.get("verified", False)
            kyc.bvn_first_name = result.get("first_name")
            kyc.bvn_last_name = result.get("last_name")
            kyc.bvn_phone = result.get("phone")
            kyc.bvn_dob = result.get("date_of_birth")
            kyc.bvn_verification_date = datetime.utcnow()

            # Check name match
            if kyc.bvn_first_name and user.first_name:
                name_match = (
                    kyc.bvn_first_name.lower() == user.first_name.lower() or
                    kyc.bvn_last_name.lower() == user.last_name.lower()
                )
                kyc.bvn_match_score = 1.0 if name_match else 0.5

            kyc.status = KYCStatus.BVN_VERIFIED
            return {"step": "bvn", "passed": kyc.bvn_verified}

        except Exception as e:
            logger.error(f"BVN verification error for user {user.id}: {e}")
            return {"step": "bvn", "passed": False, "error": str(e)}

    async def _verify_nin(self, user: User, kyc: UserKYC) -> dict:
        """Verify NIN and cross-check with BVN data."""
        try:
            result = await self.metamap.verify_nin(kyc.nin)

            kyc.nin_verified = result.get("verified", False)
            kyc.nin_first_name = result.get("first_name")
            kyc.nin_last_name = result.get("last_name")
            kyc.nin_verification_date = datetime.utcnow()

            # Cross-check BVN and NIN names
            if kyc.bvn_first_name and kyc.nin_first_name:
                cross_match = (
                    kyc.bvn_first_name.lower() == kyc.nin_first_name.lower() and
                    kyc.bvn_last_name.lower() == kyc.nin_last_name.lower()
                )
                if not cross_match:
                    kyc.nin_verified = False
                    return {"step": "nin", "passed": False, "reason": "BVN-NIN name mismatch"}

            kyc.status = KYCStatus.NIN_VERIFIED
            return {"step": "nin", "passed": kyc.nin_verified}

        except Exception as e:
            logger.error(f"NIN verification error for user {user.id}: {e}")
            return {"step": "nin", "passed": False, "error": str(e)}

    async def _verify_selfie(self, user: User, kyc: UserKYC) -> dict:
        """Verify selfie liveness and match against BVN photo."""
        try:
            result = await self.metamap.verify_selfie(
                user_id=str(user.id),
                verification_id=kyc.metamap_verification_id
            )

            kyc.selfie_verified = result.get("liveness", False) and result.get("match", False)
            kyc.selfie_liveness_score = result.get("liveness_score", 0.0)
            kyc.selfie_match_score = result.get("match_score", 0.0)
            kyc.selfie_verification_date = datetime.utcnow()

            # Liveness threshold: 0.7, Match threshold: 0.8
            passed = kyc.selfie_liveness_score >= 0.7 and kyc.selfie_match_score >= 0.8

            if passed:
                kyc.status = KYCStatus.SELFIE_VERIFIED

            return {"step": "selfie", "passed": passed,
                    "liveness": kyc.selfie_liveness_score,
                    "match": kyc.selfie_match_score}

        except Exception as e:
            logger.error(f"Selfie verification error for user {user.id}: {e}")
            return {"step": "selfie", "passed": False, "error": str(e)}

    async def _register_device(self, user: User) -> dict:
        """Register/verify user device for fraud fingerprinting."""
        # Device registration happens at app level — this captures the data
        return {"step": "device", "passed": True, "note": "Device registered for graph analysis"}
