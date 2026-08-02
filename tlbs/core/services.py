from __future__ import annotations

from uuid import UUID

from .database import Database
from .models import Activity, Customer, Project


class ReceiptJobService:
    def __init__(self, database: Database):
        self.database = database

    def count_by_status(self, status: str) -> int:
        return self.database.scalar(
            "SELECT COUNT(*) FROM receipt_manager_jobs WHERE status = ?",
            (status,),
        )

    def list_all(self):
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT
                    r.id,
                    r.project_id,
                    r.customer_id,
                    r.job_name,
                    r.root_path,
                    r.client_name,
                    r.status,
                    r.created_at,
                    r.updated_at
                FROM receipt_manager_jobs r
                ORDER BY r.updated_at DESC
                """
            ).fetchall()


class CustomerService:
    def __init__(self, database: Database):
        self.database = database

    def create(self, customer: Customer) -> Customer:
        name = customer.name.strip()
        if not name:
            raise ValueError("Customer name is required.")

        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO customers
                (id, name, company, email, phone, address, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(customer.id), name, customer.company.strip(),
                    customer.email.strip(), customer.phone.strip(),
                    customer.address.strip(), customer.notes.strip(),
                    customer.created_at.isoformat(), customer.updated_at.isoformat(),
                ),
            )
        return customer

    def list_all(self):
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT id, name, company, email, phone, address, notes, updated_at
                FROM customers
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()

    def list_recent(self, limit: int = 10):
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT id, name, company, email, phone, updated_at
                FROM customers
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def get(self, customer_id: UUID | str):
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT * FROM customers WHERE id = ?",
                (str(customer_id),),
            ).fetchone()


class ProjectService:
    def __init__(self, database: Database):
        self.database = database

    def get(self, project_id: UUID | str):
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (str(project_id),),
            ).fetchone()

    def create(self, project: Project) -> Project:
        name = project.name.strip()
        if not name:
            raise ValueError("Project name is required.")

        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects
                (id, customer_id, name, project_type, status, description,
                 due_date, folder_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(project.id), str(project.customer_id), name,
                    project.project_type.value, project.status.value,
                    project.description.strip(),
                    project.due_date.isoformat() if project.due_date else None,
                    project.folder_path,
                    project.created_at.isoformat(), project.updated_at.isoformat(),
                ),
            )
        return project

    def count_active(self) -> int:
        return self.database.scalar(
            "SELECT COUNT(*) FROM projects WHERE status IN ('New', 'Active', 'Waiting')"
        )

    def list_recent(self, limit: int = 10):
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT
                    p.id,
                    p.customer_id,
                    p.name,
                    p.project_type,
                    p.status,
                    p.folder_path,
                    p.updated_at,
                    c.name AS customer_name
                FROM projects p
                JOIN customers c ON c.id = p.customer_id
                ORDER BY p.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()


class ActivityService:
    def __init__(self, database: Database):
        self.database = database

    def add(self, activity: Activity) -> Activity:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO activities
                (id, customer_id, project_id, title, details, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(activity.id),
                    str(activity.customer_id) if activity.customer_id else None,
                    str(activity.project_id) if activity.project_id else None,
                    activity.title.strip(), activity.details.strip(),
                    activity.occurred_at.isoformat(),
                ),
            )
        return activity

    def list_recent(self, limit: int = 8):
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT title, details, occurred_at
                FROM activities
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
