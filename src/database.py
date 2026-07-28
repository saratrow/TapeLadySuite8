from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize(self):
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(client_id, name),
                    FOREIGN KEY(client_id) REFERENCES clients(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vendor_defaults (
                    vendor_name TEXT PRIMARY KEY COLLATE NOCASE,
                    category TEXT NOT NULL DEFAULT '',
                    payment_method TEXT NOT NULL DEFAULT '',
                    last_four TEXT NOT NULL DEFAULT '',
                    last_updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def list_clients(self):
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, name FROM clients ORDER BY name"
            ).fetchall()

    def add_client(self, name: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO clients(name) VALUES (?)",
                (name.strip(),),
            )
            conn.commit()
            return cur.lastrowid

    def list_jobs(self, client_id: int):
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, name, root_path FROM jobs "
                "WHERE client_id=? ORDER BY name",
                (client_id,),
            ).fetchall()

    def add_job(self, client_id: int, name: str, root_path: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO jobs(client_id, name, root_path) "
                "VALUES (?, ?, ?)",
                (client_id, name.strip(), root_path),
            )
            conn.commit()
            return cur.lastrowid


    def delete_job(self, job_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            conn.commit()

    def delete_client(self, client_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE client_id=?", (client_id,))
            conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
            conn.commit()

    def save_vendor_default(
        self,
        vendor_name: str,
        category: str = "",
        payment_method: str = "",
        last_four: str = "",
    ) -> None:
        vendor_name = vendor_name.strip()
        if not vendor_name:
            return

        with self.connect() as conn:
            conn.execute("""
                INSERT INTO vendor_defaults (
                    vendor_name,
                    category,
                    payment_method,
                    last_four,
                    last_updated
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(vendor_name) DO UPDATE SET
                    category=excluded.category,
                    payment_method=excluded.payment_method,
                    last_four=excluded.last_four,
                    last_updated=CURRENT_TIMESTAMP
            """, (
                vendor_name,
                category.strip(),
                payment_method.strip(),
                last_four.strip(),
            ))
            conn.commit()

    def get_vendor_default(self, vendor_name: str):
        vendor_name = vendor_name.strip()
        if not vendor_name:
            return None

        with self.connect() as conn:
            row = conn.execute("""
                SELECT category, payment_method, last_four
                FROM vendor_defaults
                WHERE vendor_name = ? COLLATE NOCASE
            """, (vendor_name,)).fetchone()

        if not row:
            return None

        return {
            "category": row[0] or "",
            "payment_method": row[1] or "",
            "last_four": row[2] or "",
        }
