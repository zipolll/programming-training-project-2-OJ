"""Application factory and ASGI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import Database
from backend.app.core.exceptions import register_exception_handlers
from backend.app.modules.agent.client import OpenAICompatibleClient
from backend.app.modules.agent.crypto import CredentialCipher
from backend.app.modules.agent.repository import AgentRepository
from backend.app.modules.agent.task_manager import AgentTaskManager
from backend.app.modules.agent.tools import AgentTools
from backend.app.modules.judge.language_service import LanguageService
from backend.app.modules.judge.repository import LanguageRepository
from backend.app.modules.judge.service import JudgeService
from backend.app.modules.logs.audit_repository import AuditRepository
from backend.app.modules.logs.audit_service import AuditService
from backend.app.modules.logs.repository import EvaluationLogRepository
from backend.app.modules.logs.service import EvaluationLogService
from backend.app.modules.problems.repository import ProblemRepository
from backend.app.modules.problems.service import ProblemService
from backend.app.modules.submissions.repository import SubmissionRepository
from backend.app.modules.submissions.service import SubmissionService
from backend.app.modules.submissions.task_manager import EvaluationTaskManager
from backend.app.modules.users.service import AuthService, UserService


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
        submission_repository = SubmissionRepository(database)
        evaluation_manager = EvaluationTaskManager(
            submission_repository,
            problem_service,
            language_service,
            lambda: application.state.judge_service,
            resolved_settings,
        )
        submission_service = SubmissionService(
            submission_repository,
            problem_service,
            language_service,
            evaluation_manager,
            resolved_settings,
        )
        application.state.submission_repository = submission_repository
        audit_service = AuditService(AuditRepository(database))
        application.state.audit_service = audit_service
        application.state.user_service = UserService(auth_service, audit_service)
        application.state.evaluation_log_service = EvaluationLogService(
            EvaluationLogRepository(database),
            submission_repository,
            problem_service,
            audit_service,
        )
        application.state.evaluation_task_manager = evaluation_manager
        application.state.submission_service = submission_service
        agent_repository = AgentRepository(database)
        agent_cipher = CredentialCipher(resolved_settings.credential_encryption_key)
        agent_model_client = OpenAICompatibleClient(agent_repository, agent_cipher)
        agent_manager = AgentTaskManager(
            agent_repository,
            agent_model_client,
            AgentTools(problem_service, language_service, resolved_settings),
            problem_service,
            resolved_settings,
        )
        application.state.agent_repository = agent_repository
        application.state.agent_cipher = agent_cipher
        application.state.agent_model_client = agent_model_client
        application.state.agent_task_manager = agent_manager
        await evaluation_manager.start()
        await agent_manager.start()
        try:
            yield
        finally:
            await agent_manager.stop()
            await evaluation_manager.stop()

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
