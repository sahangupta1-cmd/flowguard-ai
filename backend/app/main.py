from __future__ import annotations
from backend.app.ai.routes import router as ai_router

from fastapi import FastAPI

from backend.app.api.routes import router
from backend.app.ingestion.routes import router as ingestion_router


app = FastAPI(
    title="FlowGuard AI",
    description=(
        "Operational finance reconciliation and "
        "cash intelligence API."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


app.include_router(router)
app.include_router(ai_router)
app.include_router(ingestion_router)
