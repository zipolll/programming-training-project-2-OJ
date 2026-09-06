"""Language registry business rules and built-in configurations."""

import sys

from backend.app.modules.judge.models import LanguageConfig, LanguageRegistration
from backend.app.modules.judge.repository import LanguageRepository


class LanguageAlreadyExistsError(Exception):
    """Raised when a language name is already registered."""


class LanguageNotFoundError(Exception):
    """Raised when a language is absent or disabled."""


def default_languages() -> tuple[LanguageConfig, ...]:
    return (
        LanguageConfig(
            name="python",
            file_ext=".py",
            run_args=("__oj_python__", "{src}"),
            time_limit=3.0,
            memory_limit=128,
        ),
        LanguageConfig(
            name="cpp",
            file_ext=".cpp",
            compile_args=("g++", "-std=c++14", "-O2", "-pipe", "{src}", "-o", "{exe}"),
            run_args=("{exe}",),
            time_limit=3.0,
            memory_limit=128,
        ),
    )


class LanguageService:
    def __init__(self, repository: LanguageRepository) -> None:
        self.repository = repository

    async def initialize(self) -> None:
        await self.repository.seed_defaults(default_languages())
        await self.repository.migrate_builtin_python()

    async def list_enabled_names(self) -> list[str]:
        names = [config.name for config in await self.repository.list_all() if config.enabled]
        built_in_order = {"python": 0, "cpp": 1}
        return sorted(names, key=lambda name: (built_in_order.get(name, 2), name))

    async def get_enabled(self, name: str) -> LanguageConfig:
        config = await self.repository.get(name)
        if config is None or not config.enabled:
            raise LanguageNotFoundError
        if config.run_args[0] == "__oj_python__":
            config = config.model_copy(update={"run_args": (sys.executable, *config.run_args[1:])})
        return config

    async def register(self, registration: LanguageRegistration) -> LanguageConfig:
        config = registration.to_config()
        if not await self.repository.create(config):
            raise LanguageAlreadyExistsError
        return config
