"""Course test reset, with worker shutdown and administrator authentication."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from backend.app.core.responses import ApiResponse
from backend.app.core.routing import CourseRoute
from backend.app.modules.users.dependencies import require_admin
from backend.app.modules.users.models import User

router = APIRouter(route_class=CourseRoute)


@router.post("/reset/", response_model=ApiResponse)
async def reset_system(
    request: Request, response: Response,
    current_user: Annotated[User, Depends(require_admin)],
) -> ApiResponse:
    del current_user
    state = request.app.state
    await state.agent_task_manager.stop()
    await state.evaluation_task_manager.stop()
    try:
        root = state.settings.problems_path.resolve()
        paths = list(root.glob("*.json"))
        if any(path.resolve().parent != root for path in paths):
            raise ValueError("problem storage contains an external link")
        for path in paths:
            await asyncio.to_thread(path.unlink)
        await state.database.reset()
        await state.auth_service.ensure_initial_admin()
        await state.language_service.initialize()
    finally:
        await state.evaluation_task_manager.start()
        await state.agent_task_manager.start()
    response.delete_cookie(state.settings.session_cookie_name, path="/")
    response.delete_cookie(state.settings.session_bridge_cookie_name, path="/api/auth/bridge")
    return ApiResponse(msg="system reset successfully")
