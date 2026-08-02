from __future__ import annotations

import re
from pathlib import Path

from .models import Customer, Project, ProjectType


_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_name(value: str, fallback: str = "Untitled") -> str:
    cleaned = _INVALID.sub("-", value).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:100] or fallback


class ProjectFolderService:
    def __init__(self, root: Path):
        self.root = Path(root)

    def create(self, customer: Customer, project: Project) -> Path:
        customer_name = safe_name(customer.name)
        project_name = safe_name(project.name)
        folder = self.root / customer_name / project_name

        subfolders = [
            "01 Intake",
            "02 Working Files",
            "03 Review",
            "04 Deliverables",
            "05 Reports",
        ]

        if project.project_type == ProjectType.RECEIPTS:
            subfolders += ["Receipts - Original", "Receipts - Renamed", "Accountant Package"]
        elif project.project_type == ProjectType.MEDIA:
            subfolders += ["Source Media", "Captures", "Edited", "Customer Delivery"]
        elif project.project_type == ProjectType.DOCUMENTS:
            subfolders += ["Original Documents", "OCR Output", "Searchable PDFs"]
        elif project.project_type == ProjectType.RELATIONSHIPS:
            subfolders += ["Business Card Images", "Contact Exports"]

        folder.mkdir(parents=True, exist_ok=True)
        for name in subfolders:
            (folder / name).mkdir(exist_ok=True)

        readme = folder / "PROJECT_INFO.txt"
        if not readme.exists():
            readme.write_text(
                "\n".join(
                    [
                        "Tape Lady Business Suite Project",
                        f"Customer: {customer.name}",
                        f"Project: {project.name}",
                        f"Type: {project.project_type.value}",
                        f"Status: {project.status.value}",
                        f"Project ID: {project.id}",
                        "",
                        "This file was created automatically by TLBS.",
                    ]
                ),
                encoding="utf-8",
            )

        return folder
