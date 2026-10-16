"""
ML Scoring Microservice — Single-model credit scoring.

Separate FastAPI service for ML inference:
- Single LightGBM model for all borrowers
- Feature validation + drift detection
- Model performance monitoring (PSI, AUC, KS)
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.scoring_engine import ScoringEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup."""
    logger.info("Loading ML models...")
    engine = ScoringEngine()
    engine.load_models()
    app.state.engine = engine
    logger.info(f"Loaded {len(engine.models)} models")
    yield
    logger.info("ML service shutting down")


app = FastAPI(
    title="Sharp Sharp ML Scoring Service",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Schemas ──

class ScoreRequest(BaseModel):
    model_name: str
    features: dict
    persona: str


class ScoreResponse(BaseModel):
    credit_score: float
    pd: float
    top_features: list[dict] | None = None
    confidence: float
    model_name: str
    model_version: str


class ModelInfo(BaseModel):
    name: str
    version: str
    model_type: str
    persona: str
    feature_count: int
    is_champion: bool


# ── Endpoints ──

@app.post("/score", response_model=ScoreResponse)
async def score(request: ScoreRequest):
    """Score a loan application using the appropriate segment model."""
    engine: ScoringEngine = app.state.engine

    try:
        result = engine.predict(
            model_name=request.model_name,
            features=request.features,
            persona=request.persona,
        )
        return ScoreResponse(**result)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Model not found: {e}")
    except Exception as e:
        logger.error(f"Scoring error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")


@app.get("/models", response_model=list[ModelInfo])
async def list_models():
    """List all loaded models."""
    engine: ScoringEngine = app.state.engine
    return [
        ModelInfo(
            name=name,
            version=m["version"],
            model_type=m["type"],
            persona=m["persona"],
            feature_count=m.get("feature_count", 0),
            is_champion=m.get("is_champion", True),
        )
        for name, m in engine.models.items()
    ]


@app.get("/health")
async def health():
    engine: ScoringEngine = app.state.engine
    return {
        "status": "healthy",
        "models_loaded": len(engine.models),
        "service": "ml-scoring",
    }
