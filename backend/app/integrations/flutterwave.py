"""Flutterwave payment integration — disbursements + repayment collection."""
import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class FlutterwaveClient:
    """
    Flutterwave API client for:
    - Bank transfers (disbursements)
    - Transfer verification
    - Payment webhook validation
    - Account name resolution
    """

    BASE_URL = "https://api.flutterwave.com/v3"

    def __init__(self):
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    async def transfer(self, account_number: str, bank_code: str,
                       amount: float, reference: str, narration: str,
                       currency: str = "NGN") -> dict:
        """Initiate a bank transfer (disbursement)."""
        payload = {
            "account_bank": bank_code,
            "account_number": account_number,
            "amount": amount,
            "narration": narration,
            "currency": currency,
            "reference": reference,
            "callback_url": f"{settings.BASE_URL}/api/v1/webhooks/flutterwave",
            "debit_currency": "NGN",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/transfers",
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()

            return {
                "status": data.get("status"),
                "flw_ref": data.get("data", {}).get("reference"),
                "provider_status": data.get("data", {}).get("status"),
                "raw_response": data,
            }

    async def verify_transfer(self, transfer_id: str) -> dict:
        """Verify a transfer status."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/transfers/{transfer_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()

            return {
                "status": data.get("data", {}).get("status"),
                "complete_message": data.get("data", {}).get("complete_message"),
                "amount": data.get("data", {}).get("amount"),
            }

    async def resolve_account(self, account_number: str, bank_code: str) -> dict:
        """Resolve account name before disbursement."""
        payload = {
            "account_number": account_number,
            "account_bank": bank_code,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/accounts/resolve",
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()

            return {
                "account_name": data.get("data", {}).get("account_name"),
                "account_number": data.get("data", {}).get("account_number"),
            }

    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify Flutterwave webhook signature."""
        import hashlib
        expected = hashlib.sha256(
            f"{settings.FLUTTERWAVE_SECRET_KEY}".encode()
        ).hexdigest()
        return signature == expected

    async def get_banks(self, country: str = "NG") -> list[dict]:
        """Get list of supported banks."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/banks/{country}",
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
