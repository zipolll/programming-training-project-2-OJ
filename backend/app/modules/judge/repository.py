"""Asynchronous SQLite persistence for language configurations."""

import json
from typing import Any

from backend.app.core.database import Database
from backend.app.modules.judge.models import LanguageConfig


class LanguageRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

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
