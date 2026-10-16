"""FirstCentral Credit Bureau integration."""
import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class FirstCentralClient:
    """FirstCentral Credit Bureau API client — secondary bureau."""

    BASE_URL = "https://api.firstcentral.com.ng/v1"

    def __init__(self):
        self.api_key = settings.FIRST_CENTRAL_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def get_credit_report(self, bvn: str) -> dict:
        """Fetch credit report from FirstCentral by BVN."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/reports/credit",
                json={"bvn": bvn},
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()

            report = data.get("data", {})
            accounts = report.get("accounts", [])
            active = [a for a in accounts if a.get("account_status") == "active"]

            return {
                "reference": report.get("report_id"),
                "score": report.get("score"),
                "total_accounts": len(accounts),
                "active_accounts": len(active),
                "closed_accounts": len(accounts) - len(active),
                "delinquent_accounts": sum(1 for a in accounts if a.get("dpd", 0) > 0),
                "total_outstanding": sum(a.get("balance", 0) for a in active),
                "has_default": report.get("has_default_history", False),
                "max_dpd": max((a.get("dpd", 0) for a in accounts), default=0),
                "raw_response": data,
            }
