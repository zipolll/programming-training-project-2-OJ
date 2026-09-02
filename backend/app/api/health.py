"""Application health endpoint."""

from fastapi import APIRouter

from backend.app.core.responses import ApiResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=ApiResponse)
async def health_check() -> ApiResponse:
    """Report that the API process is available."""
    return ApiResponse(data={"status": "ok"})
