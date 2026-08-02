from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .database import Database
from .folders import safe_name
from .models import Activity, Customer, Project
from .services import ActivityService

LEGACY_JOB_FOLDERS = [
    "Originals",
    "Incoming",
    "Enhanced",
    "Awaiting_Approval",
    "Approved",
    "Rejected",
    "Problem_Receipts",
    "Exports",
    "Logs",
]


class ReceiptProjectBridgeService:
    def __init__(self, database: Database, activity_service: ActivityService):
        self.database = database
        self.activity_service = activity_service

    def ensure_receipt_job(self, customer: Customer, project: Project) -> tuple[Path, str]:
        project_root = Path(project.folder_path) if project.folder_path else Path.home()
        if not project_root.exists():
            project_root.mkdir(parents=True, exist_ok=True)

        receipt_root = project_root / "Receipt Manager Jobs"
        receipt_root.mkdir(parents=True, exist_ok=True)

        job_name = safe_name(project.name, fallback="Receipt Job")
        job_path = receipt_root / safe_name(customer.name) / job_name
        job_path.mkdir(parents=True, exist_ok=True)

        for folder in LEGACY_JOB_FOLDERS:
            (job_path / folder).mkdir(parents=True, exist_ok=True)

        self._ensure_mapping(customer, project, job_name, job_path)
        self.activity_service.add(
            Activity(
                customer_id=customer.id,
                project_id=project.id,
                title=f"Receipt Manager bridge ready: {project.name}",
                details=f"Job root: {job_path}",
            )
        )
        return job_path, job_name

    def launch_receipt_manager(self, customer: Customer, project: Project, job_root: Path) -> subprocess.Popen[str]:
        env = os.environ.copy()
        env["TLBS_RECEIPT_CONTEXT_CUSTOMER"] = customer.name
        env["TLBS_RECEIPT_CONTEXT_PROJECT"] = project.name
        env["TLBS_RECEIPT_CONTEXT_JOB_ROOT"] = str(job_root)

        app_root = Path(__file__).resolve().parents[2]
        src_app = app_root / "src" / "app.py"
        return subprocess.Popen(
            [sys.executable, str(src_app)],
            cwd=app_root,
            env=env,
            creationflags=0,
        )

    def _ensure_mapping(self, customer: Customer, project: Project, job_name: str, job_root: Path) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO receipt_manager_jobs
                (id, project_id, customer_id, job_name, root_path, client_name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    customer_id=excluded.customer_id,
                    job_name=excluded.job_name,
                    root_path=excluded.root_path,
                    client_name=excluded.client_name,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    str(project.id),
                    str(project.id),
                    str(customer.id),
                    job_name,
                    str(job_root),
                    customer.name,
                    "active",
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
