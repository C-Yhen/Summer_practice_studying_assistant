from fastapi import APIRouter

from backend.app.api.v1 import auth, courses
from backend.app.schemas import HealthResponse

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(courses.router)


@api_router.get("/health", response_model=HealthResponse, tags=["system"])
def api_health() -> HealthResponse:
    return HealthResponse(status="ok", service="studypilot-api", version="0.1.0")

