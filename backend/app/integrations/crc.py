"""CRC (Credit Reference Company) bureau integration."""
import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CRCClient:
    """
    CRC Credit Bureau API client.
    Primary bureau for credit checks in Nigeria.
    """

    BASE_URL = "https://api.crc-ng.com/v1"

    def __init__(self):
        self.api_key = settings.CRC_API_KEY
        self.api_secret = settings.CRC_API_SECRET
        self.headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Secret": self.api_secret,
            "Content-Type": "application/json",
        }

    async def get_credit_report(self, bvn: str) -> dict:
        """Fetch credit report from CRC by BVN."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/credit-report",
                json={"bvn": bvn, "report_type": "full"},
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()

            report = data.get("data", {})
            accounts = report.get("credit_accounts", [])
            active = [a for a in accounts if a.get("status") == "active"]
            closed = [a for a in accounts if a.get("status") == "closed"]
            delinquent = [a for a in accounts if a.get("days_past_due", 0) > 0]

            return {
                "reference": report.get("reference_number"),
                "score": report.get("credit_score"),
                "total_accounts": len(accounts),
                "active_accounts": len(active),
                "closed_accounts": len(closed),
                "delinquent_accounts": len(delinquent),
                "total_outstanding": sum(a.get("outstanding_balance", 0) for a in active),
                "monthly_payment": sum(a.get("monthly_payment", 0) for a in active),
                "oldest_account_months": report.get("oldest_account_age_months"),
                "has_default": any(a.get("classification") == "loss" for a in accounts),
                "max_dpd": max((a.get("days_past_due", 0) for a in accounts), default=0),
                "enquiries_30d": report.get("enquiry_count_30_days", 0),
                "enquiries_90d": report.get("enquiry_count_90_days", 0),
                "raw_response": data,
            }
