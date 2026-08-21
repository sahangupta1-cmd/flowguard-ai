from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.routes import router


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