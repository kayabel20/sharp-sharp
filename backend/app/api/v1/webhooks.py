"""Webhook endpoints — Flutterwave payment callbacks, Mono events."""
import logging
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core.database import get_db
from app.services.disbursement_service import DisbursementService
from app.integrations.flutterwave import FlutterwaveClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/flutterwave")
async def flutterwave_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Flutterwave payment webhook (disbursement + repayment)."""
    # Verify webhook signature
    signature = request.headers.get("verif-hash", "")
    body = await request.body()

    flw = FlutterwaveClient()
    if not flw.verify_webhook_signature(body.decode(), signature):
        logger.warning("Invalid Flutterwave webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data", {})

    logger.info(f"Flutterwave webhook: {event} — ref: {data.get('tx_ref')}")

    if event == "transfer.completed":
        # Disbursement confirmation
        service = DisbursementService(db)
        result = await service.verify_disbursement(data.get("reference", ""))
        await db.commit()
        return {"status": "processed", "result": result}

    elif event == "charge.completed":
        # Repayment received
        service = DisbursementService(db)
        result = await service.process_repayment_webhook(data)
        await db.commit()
        return {"status": "processed", "result": result}

    return {"status": "ignored", "event": event}


@router.post("/mono")
async def mono_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Mono Connect webhook (account linking events)."""
    payload = await request.json()
    event = payload.get("event")

    logger.info(f"Mono webhook: {event}")

    if event == "mono.events.account_connected":
        # Customer successfully linked their bank account
        account_id = payload.get("data", {}).get("account", {}).get("_id")
        # TODO: Store account_id for the user and trigger bank statement pull
        return {"status": "processed", "account_id": account_id}

    return {"status": "ignored", "event": event}
