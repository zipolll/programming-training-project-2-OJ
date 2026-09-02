"""Application factory and ASGI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import Database
from backend.app.core.exceptions import register_exception_handlers
from backend.app.modules.judge.language_service import LanguageService
from backend.app.modules.judge.repository import LanguageRepository
from backend.app.modules.judge.service import JudgeService
from backend.app.modules.problems.repository import ProblemRepository
from backend.app.modules.problems.service import ProblemService
from backend.app.modules.users.service import AuthService


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(resolved_settings.database_path)
        await database.initialize()
        auth_service = AuthService(database, resolved_settings)
        problem_service = ProblemService(ProblemRepository(resolved_settings.problems_path))
        language_service = LanguageService(LanguageRepository(database))
        await auth_service.ensure_initial_admin()
        await problem_service.initialize()
        await language_service.initialize()
        application.state.database = database
        application.state.auth_service = auth_service
        application.state.problem_service = problem_service
        application.state.language_service = language_service
        application.state.judge_service = JudgeService(
            problem_service, language_service, resolved_settings
        )
        yield

    application = FastAPI(
        title=resolved_settings.app_name,
        debug=resolved_settings.debug,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(application)
    application.include_router(api_router, prefix=resolved_settings.api_prefix)
    return application


app = create_app()
