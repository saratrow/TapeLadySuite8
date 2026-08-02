from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


BASE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    name TEXT NOT NULL,
    project_type TEXT NOT NULL,
    status TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    due_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    customer_id TEXT,
    project_id TEXT,
    title TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    customer_id TEXT,
    project_id TEXT,
    title TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    due_date TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS receipt_manager_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    job_name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    client_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_projects_customer_id ON projects(customer_id);
CREATE INDEX IF NOT EXISTS ix_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS ix_activities_occurred_at ON activities(occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS ix_receipt_manager_jobs_status ON receipt_manager_jobs(status);
CREATE INDEX IF NOT EXISTS ix_receipt_manager_jobs_project_id ON receipt_manager_jobs(project_id);
"""

MIGRATIONS = {
    1: [
        "ALTER TABLE projects ADD COLUMN folder_path TEXT NOT NULL DEFAULT ''",
    ],
    2: [
        "CREATE INDEX IF NOT EXISTS ix_projects_updated_at ON projects(updated_at DESC)",
    ],
    3: [
        """
        CREATE TABLE IF NOT EXISTS receipt_manager_jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL UNIQUE,
            customer_id TEXT NOT NULL,
            job_name TEXT NOT NULL,
            root_path TEXT NOT NULL,
            client_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_receipt_manager_jobs_status ON receipt_manager_jobs(status)",
        "CREATE INDEX IF NOT EXISTS ix_receipt_manager_jobs_project_id ON receipt_manager_jobs(project_id)",
    ],
}


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(BASE_SCHEMA)
            applied = {
                int(row["version"])
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }

            for version, statements in sorted(MIGRATIONS.items()):
                if version in applied:
                    continue
                for statement in statements:
                    try:
                        connection.execute(statement)
                    except sqlite3.OperationalError as exc:
                        # A prior development build may already contain the column.
                        if "duplicate column name" not in str(exc).lower():
                            raise
                connection.execute(
                    """
                    INSERT OR IGNORE INTO schema_migrations(version, applied_at)
                    VALUES (?, datetime('now'))
                    """,
                    (version,),
                )

    def scalar(self, sql: str, parameters: tuple = ()) -> int:
        with self.connect() as connection:
            row = connection.execute(sql, parameters).fetchone()
            return int(row[0]) if row else 0
