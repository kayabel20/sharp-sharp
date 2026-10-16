"""API v1 router — aggregates all endpoint modules."""
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.applications import router as applications_router
from app.api.v1.loans import router as loans_router
from app.api.v1.admin import router as admin_router
from app.api.v1.webhooks import router as webhooks_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(applications_router)
api_router.include_router(loans_router)
api_router.include_router(admin_router)
api_router.include_router(webhooks_router)
