"""Top-level API router composition."""

from fastapi import APIRouter

from backend.app.api.health import router as health_router
from backend.app.modules.agent.router import router as agent_router
from backend.app.modules.judge.router import router as judge_router
from backend.app.modules.logs.router import (
    problem_log_router,
    submission_log_router,
)
from backend.app.modules.logs.router import (
    router as logs_router,
)
from backend.app.modules.problems.router import router as problems_router
from backend.app.modules.submissions.router import router as submissions_router
from backend.app.modules.users.auth_router import router as auth_router
from backend.app.modules.users.management_router import router as user_management_router
from backend.app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(problems_router, prefix="/problems", tags=["problems"])
api_router.include_router(problem_log_router, prefix="/problems", tags=["logs"])
api_router.include_router(judge_router, prefix="/languages", tags=["judge"])
api_router.include_router(submissions_router, prefix="/submissions", tags=["submissions"])
api_router.include_router(submission_log_router, prefix="/submissions", tags=["logs"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(user_management_router, prefix="/users", tags=["users"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(logs_router, prefix="/logs", tags=["logs"])
api_router.include_router(agent_router, prefix="/agent", tags=["agent"])
