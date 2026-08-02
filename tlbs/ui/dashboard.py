from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from ..core.database import Database
from ..core.folders import ProjectFolderService
from ..core.receipt_bridge import ReceiptProjectBridgeService
from ..core.services import ActivityService, CustomerService, ProjectService, ReceiptJobService
from ..core.workflows import CustomerProjectWorkflow
from ..modules.registry import MODULES
from ..version import APP_NAME, VERSION
from .theme import DARK_THEME
from .wizard import CustomerProjectWizard


class DashboardWindow(QMainWindow):
    def __init__(self, database: Database):
        super().__init__()
        self.database = database
        self.customers = CustomerService(database)
        self.projects = ProjectService(database)
        self.activities = ActivityService(database)
        self.receipt_jobs = ReceiptJobService(database)

        app_root = Path(__file__).resolve().parents[2]
        self.projects_root = app_root / "TLBS Projects"
        self.receipt_bridge = ReceiptProjectBridgeService(database, self.activities)
        self.workflow = CustomerProjectWorkflow(
            self.customers,
            self.projects,
            self.activities,
            ProjectFolderService(self.projects_root),
            self.receipt_bridge,
        )

        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1320, 840)
        self.setMinimumSize(1040, 700)
        self.setStyleSheet(DARK_THEME)
        self._build()
        self.refresh()

    def _build(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(28, 24, 28, 24)
        self.content_layout.setSpacing(18)

        header = QHBoxLayout()
        greeting = QVBoxLayout()
        title = QLabel(self._greeting())
        title.setObjectName("pageTitle")
        subtitle = QLabel("Create customers, projects, folders, and activity in one workflow.")
        subtitle.setObjectName("muted")
        greeting.addWidget(title)
        greeting.addWidget(subtitle)
        header.addLayout(greeting)
        header.addStretch()

        new_project = QPushButton("+ New Customer / Project")
        new_project.setObjectName("primary")
        new_project.clicked.connect(self.create_customer_project)
        header.addWidget(new_project)
        self.content_layout.addLayout(header)

        metrics = QHBoxLayout()
        self.receipt_active_metric = self._metric_card("Active Receipt Jobs", "0")
        self.receipt_waiting_metric = self._metric_card("Waiting Review", "0")
        self.receipt_completed_metric = self._metric_card("Completed Jobs", "0")
        metrics.addWidget(self.receipt_active_metric)
        metrics.addWidget(self.receipt_waiting_metric)
        metrics.addWidget(self.receipt_completed_metric)
        self.content_layout.addLayout(metrics)

        section = QLabel("TAPE LADY BUSINESS SUITE MODULES")
        section.setObjectName("sectionTitle")
        self.content_layout.addWidget(section)

        modules_grid = QGridLayout()
        modules_grid.setSpacing(14)
        for index, module in enumerate(MODULES):
            modules_grid.addWidget(self._module_card(module), index // 3, index % 3)
        self.content_layout.addLayout(modules_grid)

        lower = QHBoxLayout()
        lower.setSpacing(14)
        lower.addWidget(self._recent_projects_card(), 3)
        lower.addWidget(self._activity_card(), 2)
        self.content_layout.addLayout(lower)
        self.content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.setCentralWidget(central)

    def _sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(235)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 22, 16, 18)

        brand = QLabel("Tape Lady\nBusiness Suite")
        brand.setObjectName("brandTitle")
        sub = QLabel("Business command center")
        sub.setObjectName("brandSubtitle")
        layout.addWidget(brand)
        layout.addWidget(sub)
        layout.addSpacing(22)

        for label in (
            "Dashboard", "Receipt Manager", "Media Capture",
            "Relationship Manager", "Document Center",
            "Client Vault", "Reports & Analytics", "Settings"
        ):
            button = QPushButton(label)
            button.setObjectName("nav")
            button.clicked.connect(lambda checked=False, text=label: self.open_module(text))
            layout.addWidget(button)

        layout.addStretch()
        version = QLabel(f"{APP_NAME}\nVersion {VERSION}\nSprint 2")
        version.setObjectName("muted")
        layout.addWidget(version)
        return sidebar

    def _metric_card(self, label, value):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        metric = QLabel(value)
        metric.setObjectName("metric")
        caption = QLabel(label)
        caption.setObjectName("muted")
        layout.addWidget(metric)
        layout.addWidget(caption)
        return card

    def _set_metric(self, card, value):
        labels = card.findChildren(QLabel)
        if labels:
            labels[0].setText(str(value))

    def _module_card(self, module):
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(150)
        layout = QVBoxLayout(card)
        title = QLabel(module.title)
        title.setObjectName("moduleTitle")
        description = QLabel(module.description)
        description.setObjectName("muted")
        description.setWordWrap(True)
        status = QLabel(module.status)
        status.setObjectName("muted")
        button = QPushButton("Open")
        button.clicked.connect(lambda checked=False, text=module.title: self.open_module(text))
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch()
        layout.addWidget(status)
        layout.addWidget(button)
        return card

    def _recent_projects_card(self):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        title_row = QHBoxLayout()
        title = QLabel("RECENT PROJECTS")
        title.setObjectName("sectionTitle")
        open_folder = QPushButton("Open Projects Folder")
        open_folder.clicked.connect(self.open_projects_folder)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(open_folder)

        self.project_table = QTableWidget(0, 4)
        self.project_table.setHorizontalHeaderLabels(
            ["Customer", "Project", "Type", "Status"]
        )
        self.project_table.horizontalHeader().setStretchLastSection(True)
        self.project_table.verticalHeader().setVisible(False)
        self.project_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.project_table.doubleClicked.connect(self.open_selected_project_folder)

        layout.addLayout(title_row)
        layout.addWidget(self.project_table)
        return card

    def _activity_card(self):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        title = QLabel("RECENT ACTIVITY")
        title.setObjectName("sectionTitle")
        self.activity_layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addLayout(self.activity_layout)
        layout.addStretch()
        return card

    def create_customer_project(self):
        wizard = CustomerProjectWizard(
            self.customers,
            self.projects_root,
            self,
        )
        if wizard.exec() != wizard.DialogCode.Accepted:
            return

        existing, customer, project = wizard.values()
        try:
            if existing:
                result = self.workflow.create_project_for_existing_customer(
                    customer, project
                )
            else:
                result = self.workflow.create_new_customer_project(
                    customer, project
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Could not create project",
                f"{type(exc).__name__}: {exc}",
            )
            return

        self.refresh()
        QMessageBox.information(
            self,
            "Project created",
            f"{result.project.name} is ready.\n\n"
            f"Folder:\n{result.folder}",
        )

    def open_module(self, name):
        if name == "Dashboard":
            return
        if name == "Receipt Manager":
            self.launch_receipt_manager_from_selection()
            return
        QMessageBox.information(
            self,
            name,
            f"{name} is registered in TLBS.\n\n"
            "This module can be connected incrementally without changing the legacy Receipt Manager schema."
        )

    def open_projects_folder(self):
        self.projects_root.mkdir(parents=True, exist_ok=True)
        os.startfile(self.projects_root)

    def open_selected_project_folder(self):
        row = self.project_table.currentRow()
        if row < 0:
            return
        item = self.project_table.item(row, 0)
        payload = item.data(Qt.ItemDataRole.UserRole) if item else None
        path = payload.get("folder_path") if isinstance(payload, dict) else payload
        if path and Path(path).exists():
            os.startfile(path)

    def launch_receipt_manager_from_selection(self):
        row = self.project_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select a project", "Select a TLBS project first.")
            return
        item = self.project_table.item(row, 0)
        payload = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(payload, dict):
            QMessageBox.information(self, "Select a project", "Select a TLBS project first.")
            return
        project_row = self.projects.get(payload["project_id"])
        customer_row = self.customers.get(payload["customer_id"])
        if not project_row or not customer_row:
            QMessageBox.warning(self, "Could not resolve project", "The selected TLBS project could not be loaded.")
            return

        from ..core.models import Customer, Project, ProjectType, ProjectStatus
        from datetime import datetime

        customer = Customer(
            id=project_row["customer_id"],
            name=customer_row["name"],
            company=customer_row["company"],
            email=customer_row["email"],
            phone=customer_row["phone"],
            address=customer_row["address"],
            notes=customer_row["notes"],
            created_at=datetime.fromisoformat(customer_row["created_at"]),
            updated_at=datetime.fromisoformat(customer_row["updated_at"]),
        )
        project = Project(
            id=project_row["id"],
            customer_id=project_row["customer_id"],
            name=project_row["name"],
            project_type=ProjectType(project_row["project_type"]),
            status=ProjectStatus(project_row["status"]),
            description=project_row["description"],
            due_date=datetime.fromisoformat(project_row["due_date"]) if project_row["due_date"] else None,
            folder_path=project_row["folder_path"],
            created_at=datetime.fromisoformat(project_row["created_at"]),
            updated_at=datetime.fromisoformat(project_row["updated_at"]),
        )

        job_path, _ = self.receipt_bridge.ensure_receipt_job(customer, project)
        self.receipt_bridge.launch_receipt_manager(customer, project, job_path)
        self.refresh()
        QMessageBox.information(self, "Receipt Manager launched", f"Receipt Manager job created for {customer.name} / {project.name}.")

    def refresh(self):
        self._set_metric(self.receipt_active_metric, self.receipt_jobs.count_by_status("active"))
        self._set_metric(self.receipt_waiting_metric, self.receipt_jobs.count_by_status("waiting_review"))
        self._set_metric(self.receipt_completed_metric, self.receipt_jobs.count_by_status("completed"))

        rows = self.projects.list_recent(10)
        self.project_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row["customer_name"],
                row["name"],
                row["project_type"],
                row["status"],
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value or "")
                if col == 0:
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        {
                            "folder_path": row["folder_path"],
                            "project_id": row["id"],
                            "customer_id": row["customer_id"],
                        },
                    )
                self.project_table.setItem(row_index, col, item)

        while self.activity_layout.count():
            item = self.activity_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        activities = self.activities.list_recent(7)
        if not activities:
            empty = QLabel(
                "No activity yet. Create the first customer and project to begin."
            )
            empty.setObjectName("muted")
            self.activity_layout.addWidget(empty)
        else:
            for activity in activities:
                timestamp = datetime.fromisoformat(activity["occurred_at"])
                text = QLabel(
                    f"<b>{activity['title']}</b><br>"
                    f"{activity['details'] or ''} "
                    f"<span style='color:#8f9aa3'>• {timestamp:%b %d, %I:%M %p}</span>"
                )
                text.setWordWrap(True)
                self.activity_layout.addWidget(text)

    @staticmethod
    def _greeting():
        hour = datetime.now().hour
        if hour < 12:
            part = "morning"
        elif hour < 18:
            part = "afternoon"
        else:
            part = "evening"
        return f"Good {part}, Sara!"
