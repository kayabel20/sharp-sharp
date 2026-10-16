"""
Mono bank data integration — account linking + statement pull.

Wire-up
-------
Set in `.env`:
    MONO_SECRET_KEY=test_sk_xxx          # private, server-only
    MONO_PUBLIC_KEY=test_pk_xxx          # public, frontend uses this
    MONO_BASE_URL=https://api.withmono.com/v2
    MONO_STATEMENT_PERIOD=last6months    # or last3months, last12months

Sandbox: Mono provides test_pk_*/test_sk_* keys at https://app.withmono.com/dashboard/apps
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class MonoError(Exception):
    """Raised when Mono returns a non-2xx response or a malformed payload."""

    def __init__(self, message: str, status_code: int | None = None,
                 payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class MonoClient:
    """
    Mono Connect API client (v2).

    Methods:
        - exchange_token(code)        : POST /accounts/auth — public_token → account_id
        - get_account_details(id)     : GET  /accounts/{id}
        - get_account_statement(id)   : GET  /accounts/{id}/statement
        - unlink_account(id)          : POST /accounts/{id}/unlink

    Raises MonoError on transport failure or non-2xx responses, so callers can
    distinguish between "no link configured" and "link configured but failed".
    """

    def __init__(self):
        settings = get_settings()
        self.secret_key = settings.MONO_SECRET_KEY
        self.base_url = settings.MONO_BASE_URL.rstrip("/")
        self.statement_period = settings.MONO_STATEMENT_PERIOD
        self.headers = {
            "mono-sec-key": self.secret_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @property
    def is_configured(self) -> bool:
        return bool(self.secret_key)

    # ------------------------------------------------------------------ #
    # Account auth                                                       #
    # ------------------------------------------------------------------ #

    async def exchange_token(self, code: str) -> dict:
        """
        Exchange a Mono Connect public_token (a.k.a. `code`) for an account_id.

        Mono returns: {"id": "<account_id>"} on success.
        """
        url = f"{self.base_url}/accounts/auth"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url, json={"code": code}, headers=self.headers,
                )
        except httpx.HTTPError as e:
            raise MonoError(f"Mono /accounts/auth network error: {e}") from e

        if response.status_code >= 400:
            raise MonoError(
                f"Mono /accounts/auth failed: {response.text[:200]}",
                status_code=response.status_code,
                payload=_safe_json(response),
            )

        data = _safe_json(response) or {}
        account_id = data.get("id") or data.get("data", {}).get("id")
        if not account_id:
            raise MonoError(
                f"Mono /accounts/auth returned no id: {data}",
                payload=data,
            )
        return {"account_id": account_id}

    # ------------------------------------------------------------------ #
    # Account details                                                    #
    # ------------------------------------------------------------------ #

    async def get_account_details(self, account_id: str) -> dict:
        """Get account details (name, masked number, balance, institution)."""
        url = f"{self.base_url}/accounts/{account_id}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=self.headers)
        except httpx.HTTPError as e:
            raise MonoError(
                f"Mono /accounts/{{id}} network error: {e}"
            ) from e

        if response.status_code >= 400:
            raise MonoError(
                f"Mono /accounts/{{id}} failed: {response.text[:200]}",
                status_code=response.status_code,
                payload=_safe_json(response),
            )

        data = (_safe_json(response) or {}).get("data", {})
        institution = data.get("institution", {}) or {}
        account = data.get("account", data)  # v2 nests under .account
        return {
            "account_id": account.get("id") or account_id,
            "account_name": account.get("name"),
            "account_number": account.get("accountNumber") or account.get("account_number"),
            "balance_kobo": account.get("balance", 0),
            "balance": (account.get("balance", 0) or 0) / 100,
            "currency": account.get("currency", "NGN"),
            "institution": institution.get("name"),
            "bank_code": institution.get("bankCode") or institution.get("code"),
            "type": account.get("type"),
        }

    # ------------------------------------------------------------------ #
    # Statement                                                          #
    # ------------------------------------------------------------------ #

    async def get_account_statement(
        self,
        account_id: str,
        period: str | None = None,
    ) -> dict:
        """
        Pull bank statement for a linked account.

        Returns a dict shaped for `bank_service.analyze` — preserves raw_response
        under `raw_response` so transaction-level analysis can run downstream.
        """
        url = f"{self.base_url}/accounts/{account_id}/statement"
        params = {"period": period or self.statement_period, "output": "json"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params, headers=self.headers)
        except httpx.HTTPError as e:
            raise MonoError(
                f"Mono /statement network error: {e}"
            ) from e

        if response.status_code >= 400:
            raise MonoError(
                f"Mono /statement failed: {response.text[:200]}",
                status_code=response.status_code,
                payload=_safe_json(response),
            )

        data = _safe_json(response) or {}
        statement = data.get("data", {})
        transactions = statement.get("transactions", []) or []

        credits = [t for t in transactions if t.get("type") == "credit"]
        debits = [t for t in transactions if t.get("type") == "debit"]

        # Mono returns amounts in kobo
        total_credit = sum(t.get("amount", 0) for t in credits) / 100
        total_debit = sum(t.get("amount", 0) for t in debits) / 100
        months = max(
            len({t.get("date", "")[:7] for t in transactions if t.get("date")}),
            1,
        )

        institution = statement.get("institution", {}) or {}
        meta = statement.get("meta", {}) or {}
        return {
            "provider": "mono",
            "reference": statement.get("id"),
            "account_name": statement.get("name"),
            "bank_name": institution.get("name"),
            "months_covered": months,
            "average_balance": meta.get("average_balance", 0) / 100
            if isinstance(meta.get("average_balance"), (int, float))
            else 0,
            "average_monthly_credit": total_credit / months,
            "average_monthly_debit": total_debit / months,
            "transaction_count": len(transactions),
            "raw_response": data,
        }

    # ------------------------------------------------------------------ #
    # Unlink                                                             #
    # ------------------------------------------------------------------ #

    async def unlink_account(self, account_id: str) -> dict:
        """Detach a linked account; future statement pulls will fail."""
        url = f"{self.base_url}/accounts/{account_id}/unlink"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, headers=self.headers)
        except httpx.HTTPError as e:
            raise MonoError(
                f"Mono /unlink network error: {e}"
            ) from e

        if response.status_code >= 400:
            raise MonoError(
                f"Mono /unlink failed: {response.text[:200]}",
                status_code=response.status_code,
                payload=_safe_json(response),
            )
        return _safe_json(response) or {}


def _safe_json(response: httpx.Response) -> dict | None:
    try:
        return response.json()
    except ValueError:
        return None
