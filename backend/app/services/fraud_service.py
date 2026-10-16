"""Fraud detection service — 4-layer architecture."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, UserDevice
from app.models.loan import LoanApplication
from app.models.risk import FraudScore, FraudDecision

logger = logging.getLogger(__name__)


class FraudService:
    """Fraud detection: device fingerprint + graph network analysis."""

    # Score cutoffs (configurable)
    IDENTITY_CUTOFF = 50.0
    DIGITAL_CUTOFF = 40.0
    GEO_CUTOFF = 30.0
    DEVICE_CUTOFF = 35.0
    COMPOSITE_CUTOFF = 45.0
    GRAPH_HIGH_RISK_THRESHOLD = 3  # Connected defaulters

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check(self, user: User, application: LoanApplication) -> dict:
        """Run all fraud detection layers."""

        # Layer 1: Individual scoring (CDL approach — 4 sub-scores)
        identity_score = await self._score_identity(user)
        digital_score = await self._score_digital_footprint(user)
        geo_score = await self._score_geolocation(user)
        device_score = await self._score_device(user)

        # Composite score (weighted average)
        composite = (
            identity_score * 0.30 +
            digital_score * 0.25 +
            geo_score * 0.15 +
            device_score * 0.30
        )

        # Check cutoffs
        identity_passes = identity_score >= self.IDENTITY_CUTOFF
        digital_passes = digital_score >= self.DIGITAL_CUTOFF
        geo_passes = geo_score >= self.GEO_CUTOFF
        device_passes = device_score >= self.DEVICE_CUTOFF

        all_pass_layer1 = all([identity_passes, digital_passes, geo_passes, device_passes])

        # Layer 2: Graph DB network analysis
        graph_result = await self._graph_network_check(user)

        # Final decision
        if not all_pass_layer1:
            decision = FraudDecision.KNOCKOFF
            reason = self._get_knockoff_reason(identity_passes, digital_passes, geo_passes, device_passes)
        elif graph_result["connected_defaulters"] >= self.GRAPH_HIGH_RISK_THRESHOLD:
            decision = FraudDecision.KNOCKOFF
            reason = f"Graph: {graph_result['connected_defaulters']} connected defaulters"
        elif graph_result["connected_defaulters"] >= 1 or composite < 60:
            decision = FraudDecision.REVIEW
            reason = "Borderline fraud signals — manual review required"
        else:
            decision = FraudDecision.PASS
            reason = None

        # Save fraud score record
        fraud_score = FraudScore(
            user_id=user.id,
            application_id=application.id,
            identity_verification_score=identity_score,
            identity_cutoff=self.IDENTITY_CUTOFF,
            identity_passes=identity_passes,
            digital_footprint_score=digital_score,
            digital_cutoff=self.DIGITAL_CUTOFF,
            digital_passes=digital_passes,
            geo_location_score=geo_score,
            geo_cutoff=self.GEO_CUTOFF,
            geo_passes=geo_passes,
            device_score=device_score,
            device_cutoff=self.DEVICE_CUTOFF,
            device_passes=device_passes,
            composite_fraud_score=composite,
            composite_cutoff=self.COMPOSITE_CUTOFF,
            graph_fraud_score=graph_result.get("score", 0),
            connected_defaulters=graph_result.get("connected_defaulters", 0),
            shared_devices_with_defaulters=graph_result.get("shared_devices", 0),
            shared_contacts_with_defaulters=graph_result.get("shared_contacts", 0),
            shared_accounts_with_defaulters=graph_result.get("shared_accounts", 0),
            graph_risk_level=graph_result.get("risk_level", "low"),
            credolab_score=None,
            decision=decision,
            knockoff_reason=reason,
            requires_manual_review=(decision == FraudDecision.REVIEW),
        )
        self.db.add(fraud_score)
        await self.db.flush()

        return {
            "decision": decision.value,
            "composite_score": composite,
            "identity_score": identity_score,
            "digital_score": digital_score,
            "geo_score": geo_score,
            "device_score": device_score,
            "graph_result": graph_result,
            "reason": reason,
            "requires_review": decision == FraudDecision.REVIEW,
        }

    async def _score_identity(self, user: User) -> float:
        """Score identity verification strength."""
        score = 0.0
        kyc = user.kyc

        if not kyc:
            return 0.0

        if kyc.bvn_verified:
            score += 30
        if kyc.nin_verified:
            score += 25
        if kyc.selfie_verified:
            score += 25
            if kyc.selfie_liveness_score:
                score += kyc.selfie_liveness_score * 10
            if kyc.selfie_match_score:
                score += kyc.selfie_match_score * 10

        return min(score, 100.0)

    async def _score_digital_footprint(self, user: User) -> float:
        """Score digital presence (email age, social, etc.)."""
        score = 50.0  # Base score

        # Email domain scoring
        if user.email:
            if user.email.endswith("@gmail.com") or user.email.endswith("@yahoo.com"):
                score += 10
            elif user.email.endswith("@outlook.com") or user.email.endswith("@hotmail.com"):
                score += 8
            # Custom domain = likely professional
            elif "." in user.email.split("@")[1]:
                score += 15

        # Account age
        if user.created_at:
            days_since_signup = (datetime.utcnow() - user.created_at).days
            if days_since_signup > 180:
                score += 15
            elif days_since_signup > 30:
                score += 8

        # Has multiple verified contact methods
        if user.phone_number and user.email:
            score += 10

        return min(score, 100.0)

    async def _score_geolocation(self, user: User) -> float:
        """Score geolocation consistency."""
        score = 60.0  # Base score for Nigeria-based users

        # Check device locations
        devices = user.devices if user.devices else []
        if devices:
            primary = next((d for d in devices if d.is_primary), None)
            if primary and primary.geo_state:
                # Check if address matches device location
                addresses = user.addresses if user.addresses else []
                if addresses:
                    addr_state = addresses[0].state
                    if addr_state and primary.geo_state.lower() == addr_state.lower():
                        score += 20
                    else:
                        score -= 10

                # Nigeria check
                if primary.latitude and 4.0 <= primary.latitude <= 14.0:
                    score += 20  # Within Nigeria lat range

        return min(max(score, 0.0), 100.0)

    async def _score_device(self, user: User) -> float:
        """Score device trustworthiness."""
        score = 50.0

        devices = user.devices if user.devices else []
        if not devices:
            return 30.0  # Low score if no device registered

        primary = next((d for d in devices if d.is_primary), devices[0])

        # Device type
        if primary.device_type in ("android", "ios"):
            score += 15

        # Flagged device
        if primary.is_flagged:
            score -= 40

        # CredoLab score
        if primary.credolab_score:
            score += primary.credolab_score * 0.3

        # Multiple devices (unusual for new user)
        if len(devices) > 3:
            score -= 10

        return min(max(score, 0.0), 100.0)

    async def _graph_network_check(self, user: User) -> dict:
        """
        Graph DB network analysis.
        Checks for connections to known defaulters via shared attributes.

        In production, this queries a Neo4j/Neptune graph database.
        For now, we query the relational DB for shared device fingerprints.
        """
        connected_defaulters = 0
        shared_devices = 0
        shared_contacts = 0
        shared_accounts = 0

        # Check shared device fingerprints
        devices = user.devices if user.devices else []
        for device in devices:
            if device.fingerprint_hash:
                result = await self.db.execute(
                    select(UserDevice).where(
                        UserDevice.fingerprint_hash == device.fingerprint_hash,
                        UserDevice.user_id != user.id
                    )
                )
                shared_device_users = result.scalars().all()
                for sd in shared_device_users:
                    # Check if any shared-device user has defaulted
                    shared_user = await self.db.get(User, sd.user_id)
                    if shared_user and shared_user.status and shared_user.status.value == "blacklisted":
                        connected_defaulters += 1
                        shared_devices += 1

        # Risk level
        if connected_defaulters >= 5:
            risk_level = "critical"
        elif connected_defaulters >= 3:
            risk_level = "high"
        elif connected_defaulters >= 1:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "connected_defaulters": connected_defaulters,
            "shared_devices": shared_devices,
            "shared_contacts": shared_contacts,
            "shared_accounts": shared_accounts,
            "risk_level": risk_level,
            "score": max(100 - (connected_defaulters * 20), 0),
        }

    def _get_knockoff_reason(self, identity: bool, digital: bool,
                             geo: bool, device: bool) -> str:
        reasons = []
        if not identity:
            reasons.append("identity verification score below cutoff")
        if not digital:
            reasons.append("digital footprint score below cutoff")
        if not geo:
            reasons.append("geo-location score below cutoff")
        if not device:
            reasons.append("device score below cutoff")
        return "Fraud knockoff: " + ", ".join(reasons)
