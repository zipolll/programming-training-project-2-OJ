"""Asynchronous SQLite persistence for language configurations."""

import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from backend.app.core.database import Database
from backend.app.modules.judge.models import LanguageConfig


class LanguageRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def migrate_builtin_python(self) -> None:
        """Replace a legacy absolute built-in interpreter with a portable runtime marker."""
        config = await self.get("python")
        if config is None or config.file_ext != ".py" or config.compile_args is not None:
            return
        if len(config.run_args) != 2 or config.run_args[1] != "{src}":
            return
        executable = config.run_args[0]
        if not (
            PureWindowsPath(executable).is_absolute() or PurePosixPath(executable).is_absolute()
        ):
            return
        name = PureWindowsPath(executable).name.lower()
        if not name.startswith("python"):
            return
        async with self.database.connect() as connection:
            await connection.execute(
                "UPDATE languages SET run_args = ? WHERE name = 'python'",
                (json.dumps(["__oj_python__", "{src}"]),),
            )
            await connection.commit()

    async def seed_defaults(self, defaults: tuple[LanguageConfig, ...]) -> None:
        async with self.database.connect() as connection:
            await connection.executemany(
                """
                INSERT OR IGNORE INTO languages
                    (name, file_ext, compile_args, run_args, time_limit, memory_limit, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [self._values(config) for config in defaults],
            )
            await connection.commit()

    async def list_all(self) -> list[LanguageConfig]:
        async with self.database.connect() as connection:
            cursor = await connection.execute("SELECT * FROM languages ORDER BY name")
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def get(self, name: str) -> LanguageConfig | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute("SELECT * FROM languages WHERE name = ?", (name,))
            row = await cursor.fetchone()
        return None if row is None else self._from_row(row)

    async def create(self, config: LanguageConfig) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                INSERT OR IGNORE INTO languages
                    (name, file_ext, compile_args, run_args, time_limit, memory_limit, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                self._values(config),
            )
            await connection.commit()
            return cursor.rowcount == 1

    @staticmethod
    def _values(config: LanguageConfig) -> tuple[object, ...]:
        return (
            config.name,
            config.file_ext,
            None if config.compile_args is None else json.dumps(config.compile_args),
            json.dumps(config.run_args),
            config.time_limit,
            config.memory_limit,
            int(config.enabled),
        )

    @staticmethod
    def _from_row(row: Any) -> LanguageConfig:
        return LanguageConfig(
            name=row["name"],
            file_ext=row["file_ext"],
            compile_args=None
            if row["compile_args"] is None
            else tuple(json.loads(row["compile_args"])),
            run_args=tuple(json.loads(row["run_args"])),
            time_limit=row["time_limit"],
            memory_limit=row["memory_limit"],
            enabled=bool(row["enabled"]),
        )
