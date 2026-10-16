"""MetaMap (formerly Mati) KYC integration — BVN, NIN, Selfie verification."""
import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MetaMapClient:
    """
    MetaMap identity verification API client.
    Handles:
    - BVN verification (Bank Verification Number)
    - NIN verification (National Identity Number)
    - Selfie liveness + face match
    - Document verification
    """

    BASE_URL = "https://api.metamap.com/v2"

    def __init__(self):
        self.api_key = settings.METAMAP_API_KEY
        self.api_secret = settings.METAMAP_API_SECRET
        self._token = None

    async def _get_token(self) -> str:
        """Get or refresh OAuth token."""
        if self._token:
            return self._token

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/oauth/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": self.api_key,
                    "client_secret": self.api_secret,
                },
            )
            response.raise_for_status()
            data = response.json()
            self._token = data["access_token"]
            return self._token

    async def _headers(self) -> dict:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def verify_bvn(self, bvn: str) -> dict:
        """Verify BVN and return identity data."""
        headers = await self._headers()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/verifications/bvn",
                json={"bvn": bvn, "country": "NG"},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            result = data.get("data", {})
            return {
                "verified": result.get("status") == "verified",
                "first_name": result.get("firstName"),
                "last_name": result.get("lastName"),
                "phone": result.get("phoneNumber"),
                "date_of_birth": result.get("dateOfBirth"),
                "gender": result.get("gender"),
                "photo_url": result.get("photo"),
            }

    async def verify_nin(self, nin: str) -> dict:
        """Verify NIN and return identity data."""
        headers = await self._headers()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/verifications/nin",
                json={"nin": nin, "country": "NG"},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            result = data.get("data", {})
            return {
                "verified": result.get("status") == "verified",
                "first_name": result.get("firstName"),
                "last_name": result.get("lastName"),
                "phone": result.get("phoneNumber"),
                "date_of_birth": result.get("dateOfBirth"),
            }

    async def verify_selfie(self, user_id: str, verification_id: str = None) -> dict:
        """Verify selfie liveness and face match."""
        headers = await self._headers()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/verifications/{verification_id}",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            steps = data.get("data", {}).get("steps", [])
            liveness_step = next(
                (s for s in steps if s.get("id") == "liveness"), {}
            )
            face_match_step = next(
                (s for s in steps if s.get("id") == "face-match"), {}
            )

            return {
                "liveness": liveness_step.get("status") == "completed",
                "liveness_score": liveness_step.get("data", {}).get("score", 0.0),
                "match": face_match_step.get("status") == "completed",
                "match_score": face_match_step.get("data", {}).get("score", 0.0),
            }

    async def create_verification(self, flow_id: str, metadata: dict = None) -> dict:
        """Create a new verification session."""
        headers = await self._headers()

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/verifications",
                json={"flowId": flow_id, "metadata": metadata or {}},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            return {
                "verification_id": data.get("data", {}).get("id"),
                "url": data.get("data", {}).get("url"),
            }
