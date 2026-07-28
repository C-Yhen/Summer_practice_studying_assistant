from fastapi import APIRouter

from backend.app.api.v1 import (
    async_tasks,
    auth,
    calendar,
    courses,
    dashboard,
    documents,
    learning,
    mcp,
    plans,
    practice,
    rag,
    recommendations,
    statistics,
)
from backend.app.dependencies import AppSettings
from backend.app.providers.llm import llm_runtime_status
from backend.app.responses import ok
from backend.app.schemas import HealthResponse

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(courses.router)
api_router.include_router(dashboard.router)
api_router.include_router(documents.router)
api_router.include_router(rag.router)
api_router.include_router(plans.router)
api_router.include_router(practice.router)
api_router.include_router(learning.router)
api_router.include_router(recommendations.router)
api_router.include_router(statistics.router)
api_router.include_router(async_tasks.router)
api_router.include_router(mcp.router)
api_router.include_router(calendar.router)


@api_router.get("/health", response_model=HealthResponse, tags=["system"])
def api_health() -> HealthResponse:
    return HealthResponse(status="ok", service="studypilot-api", version="0.1.0")


@api_router.get("/system/ai-status", tags=["system"])
def ai_status(settings: AppSettings) -> dict:
    return ok(llm_runtime_status(settings))
