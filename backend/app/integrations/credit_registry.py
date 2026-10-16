"""CreditRegistry bureau integration."""
import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CreditRegistryClient:
    """CreditRegistry API client — tertiary bureau."""

    BASE_URL = "https://api.creditregistry.com/v1"

    def __init__(self):
        self.username = settings.CREDIT_REGISTRY_USERNAME
        self.password = settings.CREDIT_REGISTRY_PASSWORD
        self._token = None

    async def _authenticate(self) -> str:
        if self._token:
            return self._token

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/auth/token",
                json={"username": self.username, "password": self.password},
            )
            response.raise_for_status()
            self._token = response.json().get("token")
            return self._token

    async def get_credit_report(self, bvn: str) -> dict:
        """Fetch credit report from CreditRegistry."""
        token = await self._authenticate()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/reports/credit-check",
                json={"bvn": bvn, "consent": True},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            report = data.get("data", {})
            facilities = report.get("credit_facilities", [])
            active = [f for f in facilities if f.get("status") == "performing"]

            return {
                "reference": report.get("reference"),
                "score": report.get("credit_score"),
                "total_accounts": len(facilities),
                "active_accounts": len(active),
                "total_outstanding": sum(f.get("outstanding", 0) for f in active),
                "has_default": any(f.get("classification") in ("substandard", "doubtful", "loss")
                                   for f in facilities),
                "raw_response": data,
            }
