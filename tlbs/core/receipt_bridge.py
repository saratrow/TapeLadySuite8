from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from ctypes import wintypes

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

    def _focus_existing_window(self) -> bool:
        if os.name != "nt":
            return False

        try:
            found: list[wintypes.HWND] = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def enum_handler(hwnd: wintypes.HWND, _lparam: wintypes.LPARAM) -> bool:
                title_length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if title_length:
                    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
                    if "TapeLadySuite8 Receipt Manager" in title_buffer.value:
                        found.append(hwnd)
                return True

            ctypes.windll.user32.EnumWindows(enum_handler, 0)
            if not found:
                return False

            hwnd = found[0]
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False

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

    def launch_receipt_manager(self, customer: Customer, project: Project, job_root: Path) -> tuple[subprocess.Popen[str] | None, str | None, bool]:
        if self._focus_existing_window():
            return None, None, True

        env = os.environ.copy()
        env["TLBS_RECEIPT_CONTEXT_CUSTOMER_ID"] = str(customer.id)
        env["TLBS_RECEIPT_CONTEXT_PROJECT_ID"] = str(project.id)
        env["TLBS_RECEIPT_CONTEXT_CUSTOMER"] = customer.name
        env["TLBS_RECEIPT_CONTEXT_PROJECT"] = project.name
        env["TLBS_RECEIPT_CONTEXT_JOB_ROOT"] = str(job_root)
        env["TLBS_RECEIPT_CONTEXT_FOLDER_PATH"] = str(project.folder_path or job_root)

        app_root = Path(__file__).resolve().parents[2]
        src_app = app_root / "src" / "app.py"

        try:
            process = subprocess.Popen(
                [sys.executable, str(src_app)],
                cwd=app_root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=0,
            )
            time.sleep(0.25)
            if process.poll() is not None:
                stderr = process.stderr.read().decode("utf-8", errors="ignore").strip() if process.stderr else ""
                return None, stderr or f"Receipt Manager exited immediately with code {process.returncode}.", False
            return process, None, False
        except Exception as exc:
            return None, f"Failed to start Receipt Manager: {exc}", False

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
