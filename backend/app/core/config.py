"""Application configuration using Pydantic Settings."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Sharp Sharp Lending Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development | staging | production
    BASE_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "change-me-in-production"
    API_V1_PREFIX: str = "/api/v1"
    AUTO_CREATE_TABLES: bool = True  # Bootstrap tables on first run (no Alembic yet)
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lending"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/lending"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ML Service
    ML_SERVICE_URL: str = "http://localhost:8001"

    # Integrations
    FLUTTERWAVE_SECRET_KEY: str = ""
    FLUTTERWAVE_PUBLIC_KEY: str = ""
    FLUTTERWAVE_BASE_URL: str = "https://api.flutterwave.com/v3"

    CRC_API_URL: str = ""
    CRC_USERNAME: str = ""
    CRC_PASSWORD: str = ""
    CRC_API_KEY: str = ""        # alternate name used by integrations/crc.py
    CRC_API_SECRET: str = ""

    FIRST_CENTRAL_API_URL: str = ""
    FIRST_CENTRAL_API_KEY: str = ""

    CREDIT_REGISTRY_API_URL: str = ""
    CREDIT_REGISTRY_API_KEY: str = ""
    CREDIT_REGISTRY_USERNAME: str = ""
    CREDIT_REGISTRY_PASSWORD: str = ""

    MONO_SECRET_KEY: str = ""
    MONO_PUBLIC_KEY: str = ""
    MONO_WEBHOOK_SECRET: str = ""
    MONO_BASE_URL: str = "https://api.withmono.com/v2"
    MONO_STATEMENT_PERIOD: str = "last6months"

    OKRA_SECRET_KEY: str = ""
    OKRA_BASE_URL: str = "https://api.okra.ng/v2"

    METAMAP_CLIENT_ID: str = ""
    METAMAP_CLIENT_SECRET: str = ""
    # Aliases used by integrations/metamap.py
    METAMAP_API_KEY: str = ""
    METAMAP_API_SECRET: str = ""
    METAMAP_BASE_URL: str = "https://api.metamap.com/v2"

    INDICINA_API_KEY: str = ""
    INDICINA_BASE_URL: str = "https://api.indicina.co/api/v3"

    CREDOLAB_API_KEY: str = ""
    TERRAGON_API_KEY: str = ""

    AFRICASTALKING_USERNAME: str = ""
    AFRICASTALKING_API_KEY: str = ""

    # Transaction Limits (NGN)
    MAX_TRANSACTION_AMOUNT: int = 200_000
    MAX_DAILY_CUMULATIVE: int = 500_000
    NANO_LOAN_MIN: int = 1_000
    NANO_LOAN_MAX: int = 50_000

    # Loan Ladder
    LADDER_TIERS: int = 7
    INITIAL_LOAN_MAX: int = 20_000

    # Risk Pricing
    RISK_TIERS: int = 17
    TARGET_MARGIN: float = 0.04
    COST_OF_FUNDS: float = 0.12

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
