from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .folders import ProjectFolderService
from .models import Activity, Customer, Project, ProjectType
from .receipt_bridge import ReceiptProjectBridgeService
from .services import ActivityService, CustomerService, ProjectService


@dataclass(slots=True)
class ProjectCreationResult:
    customer: Customer
    project: Project
    folder: Path


class CustomerProjectWorkflow:
    def __init__(
        self,
        customers: CustomerService,
        projects: ProjectService,
        activities: ActivityService,
        folders: ProjectFolderService,
        receipt_bridge: ReceiptProjectBridgeService | None = None,
    ):
        self.customers = customers
        self.projects = projects
        self.activities = activities
        self.folders = folders
        self.receipt_bridge = receipt_bridge

    def create_new_customer_project(
        self,
        customer: Customer,
        project: Project,
    ) -> ProjectCreationResult:
        folder: Path | None = None
        try:
            self.customers.create(customer)
            project.customer_id = customer.id
            folder = self.folders.create(customer, project)
            project.folder_path = str(folder)
            self.projects.create(project)
            if self.receipt_bridge and project.project_type == ProjectType.RECEIPTS:
                self.receipt_bridge.ensure_receipt_job(customer, project)

            self.activities.add(
                Activity(
                    customer_id=customer.id,
                    title=f"Customer created: {customer.name}",
                    details=customer.company,
                )
            )
            self.activities.add(
                Activity(
                    customer_id=customer.id,
                    project_id=project.id,
                    title=f"Project created: {project.name}",
                    details=f"{project.project_type.value} • {project.status.value}",
                )
            )
            return ProjectCreationResult(customer, project, folder)
        except Exception:
            if folder and folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
            raise

    def create_project_for_existing_customer(
        self,
        customer: Customer,
        project: Project,
    ) -> ProjectCreationResult:
        project.customer_id = customer.id
        folder = self.folders.create(customer, project)
        project.folder_path = str(folder)
        self.projects.create(project)
        if self.receipt_bridge and project.project_type == ProjectType.RECEIPTS:
            self.receipt_bridge.ensure_receipt_job(customer, project)
        self.activities.add(
            Activity(
                customer_id=customer.id,
                project_id=project.id,
                title=f"Project created: {project.name}",
                details=f"{project.project_type.value} • {project.status.value}",
            )
        )
        return ProjectCreationResult(customer, project, folder)
