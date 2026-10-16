"""Indicina (Decide) bank statement analysis integration."""
import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class IndicinaClient:
    """
    Indicina Decide API client for bank statement analysis.
    Provides:
    - Income analysis (salary detection, frequency, employer)
    - Spending analysis (categories, patterns)
    - Cash flow metrics (avg balance, credits/debits)
    - Risk indicators (gambling, other lenders, overdrafts)
    - Affordability scoring
    """

    BASE_URL = "https://api.indicina.co/api/v3"

    def __init__(self):
        self.api_key = settings.INDICINA_API_KEY
        self._token = None

    async def _get_token(self) -> str:
        if self._token:
            return self._token

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/client/auth",
                json={"client_id": self.api_key},
            )
            response.raise_for_status()
            data = response.json()
            self._token = data.get("data", {}).get("token")
            return self._token

    async def _headers(self) -> dict:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def analyze_statement(self, bvn: str = None,
                                 account_number: str = None,
                                 bank_code: str = None) -> dict:
        """
        Analyze bank statement via Indicina Decide.
        Can use BVN-based pull or MBS (Mono Bank Statement) integration.
        """
        headers = await self._headers()

        payload = {
            "customer": {
                "bvn": bvn,
                "account_number": account_number,
                "bank_code": bank_code,
            },
            "analysis_type": "full",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/analysis/request",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            analysis = data.get("data", {})
            income = analysis.get("income_analysis", {})
            spend = analysis.get("spending_analysis", {})
            cash_flow = analysis.get("cash_flow", {})
            behavioural = analysis.get("behavioural_analysis", {})

            return {
                "provider": "indicina",
                "reference": analysis.get("analysis_id"),
                "bank_name": analysis.get("bank_name"),
                "account_name": analysis.get("account_name"),
                "period_start": analysis.get("period_start"),
                "period_end": analysis.get("period_end"),
                "months_covered": cash_flow.get("months_covered", 0),
                "average_balance": cash_flow.get("average_balance", 0),
                "average_monthly_credit": cash_flow.get("average_monthly_credit", 0),
                "average_monthly_debit": cash_flow.get("average_monthly_debit", 0),
                "highest_balance": cash_flow.get("highest_balance", 0),
                "lowest_balance": cash_flow.get("lowest_balance", 0),
                "salary_frequency": income.get("salary_frequency"),
                "estimated_salary": income.get("salary_amount"),
                "salary_employer": income.get("salary_employer"),
                "salary_day_of_month": income.get("salary_day"),
                "recurring_credits_count": income.get("recurring_credits", 0),
                "gambling_transactions": behavioural.get("gambling_count", 0),
                "loan_repayments_detected": behavioural.get("loan_repayment_amount", 0),
                "other_lender_count": behavioural.get("other_lender_count", 0),
                "days_with_zero_balance": cash_flow.get("zero_balance_days", 0),
                "overdraft_count": cash_flow.get("overdraft_count", 0),
                "return_cheque_count": cash_flow.get("return_cheque_count", 0),
                "net_monthly_income": income.get("net_monthly_income"),
                "net_monthly_expenses": spend.get("net_monthly_expenses"),
                "disposable_income": income.get("disposable_income"),
                "affordability_score": analysis.get("affordability_score"),
                "transaction_count": cash_flow.get("total_transactions", 0),
                "raw_response": data,
            }

    async def get_analysis_status(self, analysis_id: str) -> dict:
        """Check status of an ongoing analysis."""
        headers = await self._headers()

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/analysis/{analysis_id}/status",
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
