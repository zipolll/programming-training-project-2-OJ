"""Asynchronous SQLite connection and schema management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin', 'banned')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS languages (
    name TEXT PRIMARY KEY,
    file_ext TEXT NOT NULL,
    compile_args TEXT,
    run_args TEXT NOT NULL,
    time_limit REAL NOT NULL,
    memory_limit INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
);

CREATE TABLE IF NOT EXISTS submissions (
    submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id TEXT NOT NULL,
    language TEXT NOT NULL REFERENCES languages(name),
    code TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'success', 'error')),
    result TEXT CHECK (result IS NULL OR result IN ('AC', 'WA', 'TLE', 'MLE', 'RE', 'CE', 'UNK')),
    score INTEGER,
    counts INTEGER NOT NULL,
    compile_info TEXT,
    stdout TEXT,
    stderr TEXT,
    time REAL,
    memory REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    evaluation_version INTEGER NOT NULL DEFAULT 1 CHECK (evaluation_version > 0)
);

CREATE INDEX IF NOT EXISTS idx_submissions_user_created
ON submissions(user_id, created_at DESC, submission_id DESC);
CREATE INDEX IF NOT EXISTS idx_submissions_problem_created
ON submissions(problem_id, created_at DESC, submission_id DESC);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);

CREATE TABLE IF NOT EXISTS submission_testcases (
    submission_id INTEGER NOT NULL REFERENCES submissions(submission_id) ON DELETE CASCADE,
    evaluation_version INTEGER NOT NULL,
    testcase_id INTEGER NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('AC', 'WA', 'TLE', 'MLE', 'RE', 'CE', 'UNK')),
    time REAL NOT NULL,
    memory REAL NOT NULL,
    error_summary TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (submission_id, evaluation_version, testcase_id)
);

CREATE TABLE IF NOT EXISTS problem_log_visibility (
    problem_id TEXT PRIMARY KEY,
    public_cases INTEGER NOT NULL DEFAULT 0 CHECK (public_cases IN (0, 1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    status INTEGER NOT NULL,
    changes TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_created
ON audit_logs(actor_user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_target_created
ON audit_logs(target_type, target_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action_created
ON audit_logs(action, created_at DESC, id DESC);
"""


class Database:
    """Create configured SQLite connections without sharing them across requests."""

    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        """Create the database directory and all required tables idempotently."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connect() as connection:
            await connection.executescript(SCHEMA)
            await connection.commit()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        """Yield a row-aware connection with integrity constraints enabled."""
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        try:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
        finally:
            await connection.close()
