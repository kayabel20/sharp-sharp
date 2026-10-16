"""
Sharp Sharp Lending Platform -- FastAPI Application Entry Point.

Automated loan origination system with:
- 14-step decisioning pipeline
- Multi-bureau credit checks (CRC + FirstCentral + CreditRegistry)
- Fraud detection (device fingerprint + graph network analysis)
- ML credit scoring (single path, all borrowers)
- Risk-based pricing with loan ladder discounts
- 7-tier loan ladder loyalty program
- CBN regulatory compliance
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import get_settings
from app.core.database import engine, init_db
from app.api.v1.router import api_router

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info("Starting Sharp Sharp Lending Platform...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    if settings.AUTO_CREATE_TABLES:
        try:
            await init_db()
            logger.info("Database tables ensured (AUTO_CREATE_TABLES=true)")
        except Exception as e:
            logger.error(f"init_db failed: {e}")
    yield
    logger.info("Shutting down...")
    await engine.dispose()


app = FastAPI(
    title="Sharp Sharp Lending Platform",
    description=(
        "Automated loan origination system with ML-powered credit scoring, "
        "multi-bureau checks, fraud detection, and risk-based pricing."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*.sharpsharp.com", "localhost"],
    )

app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "sharp-sharp",
        "version": "1.0.0",
    }


@app.get("/")
async def root():
    return {
        "service": "Sharp Sharp Lending Platform",
        "version": "1.0.0",
        "docs": "/docs",
    }
