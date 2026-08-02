from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
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
        self.show_home()

    def _build(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())

        self.content_stack = QStackedWidget()
        self.home_page = QWidget()
        self.customer_page = QWidget()
        self.project_page = QWidget()

        self.home_layout = QVBoxLayout(self.home_page)
        self.home_layout.setContentsMargins(28, 24, 28, 24)
        self.home_layout.setSpacing(18)
        self._build_home_content()

        self.customer_layout = QVBoxLayout(self.customer_page)
        self.customer_layout.setContentsMargins(28, 24, 28, 24)
        self.customer_layout.setSpacing(18)
        self._build_customer_content()

        self.project_layout = QVBoxLayout(self.project_page)
        self.project_layout.setContentsMargins(28, 24, 28, 24)
        self.project_layout.setSpacing(18)
        self._build_project_content()

        self.content_stack.addWidget(self.home_page)
        self.content_stack.addWidget(self.customer_page)
        self.content_stack.addWidget(self.project_page)
        root.addWidget(self.content_stack, 1)
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
        version = QLabel(f"{APP_NAME}\nVersion {VERSION}\nSprint 4 Phase 1")
        version.setObjectName("muted")
        layout.addWidget(version)
        return sidebar

    def _build_home_content(self):
        header = QHBoxLayout()
        greeting = QVBoxLayout()
        title = QLabel(self._greeting())
        title.setObjectName("pageTitle")
        subtitle = QLabel("Work from customers and projects, then open the right tool for the job.")
        subtitle.setObjectName("muted")
        greeting.addWidget(title)
        greeting.addWidget(subtitle)
        header.addLayout(greeting)
        header.addStretch()

        new_project = QPushButton("+ New Customer")
        new_project.setObjectName("primary")
        new_project.clicked.connect(self.create_customer_project)
        header.addWidget(new_project)
        self.home_layout.addLayout(header)

        summary = QGridLayout()
        summary.setSpacing(14)
        self.recent_customers_table = QTableWidget(0, 3)
        self.recent_customers_table.setHorizontalHeaderLabels(["Customer", "Phone", "Email"])
        self.recent_customers_table.verticalHeader().setVisible(False)
        self.recent_customers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.recent_customers_table.doubleClicked.connect(self.open_selected_customer)
        summary.addWidget(self._section_card("Recent Customers", self.recent_customers_table), 0, 0)

        self.active_projects_table = QTableWidget(0, 3)
        self.active_projects_table.setHorizontalHeaderLabels(["Customer", "Project", "Status"])
        self.active_projects_table.verticalHeader().setVisible(False)
        self.active_projects_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.active_projects_table.doubleClicked.connect(self.open_selected_project)
        summary.addWidget(self._section_card("Active Projects", self.active_projects_table), 0, 1)

        continue_last = QFrame()
        continue_last.setObjectName("card")
        continue_layout = QVBoxLayout(continue_last)
        continue_title = QLabel("Continue Last Project")
        continue_title.setObjectName("sectionTitle")
        self.last_project_label = QLabel("No project yet")
        self.last_project_label.setObjectName("muted")
        self.continue_button = QPushButton("Open Last Project")
        self.continue_button.clicked.connect(self.continue_last_project)
        continue_layout.addWidget(continue_title)
        continue_layout.addWidget(self.last_project_label)
        continue_layout.addWidget(self.continue_button)
        summary.addWidget(continue_last, 1, 0)

        activity = QFrame()
        activity.setObjectName("card")
        activity_layout = QVBoxLayout(activity)
        activity_title = QLabel("Today's Activity")
        activity_title.setObjectName("sectionTitle")
        self.activity_feed = QListWidget()
        activity_layout.addWidget(activity_title)
        activity_layout.addWidget(self.activity_feed)
        summary.addWidget(activity, 1, 1)

        self.home_layout.addLayout(summary)

        tools = QLabel("TOOLS")
        tools.setObjectName("sectionTitle")
        self.home_layout.addWidget(tools)
        modules_grid = QGridLayout()
        modules_grid.setSpacing(14)
        for index, module in enumerate(MODULES):
            modules_grid.addWidget(self._module_card(module), index // 3, index % 3)
        self.home_layout.addLayout(modules_grid)

    def _build_customer_content(self):
        self.customer_details = QLabel("Customer")
        self.customer_details.setWordWrap(True)
        self.customer_details.setObjectName("pageTitle")
        self.customer_layout.addWidget(self.customer_details)

        self.customer_projects = QTableWidget(0, 3)
        self.customer_projects.setHorizontalHeaderLabels(["Project", "Type", "Status"])
        self.customer_projects.verticalHeader().setVisible(False)
        self.customer_projects.doubleClicked.connect(self.open_selected_project)
        self.customer_layout.addWidget(self.customer_projects)

        new_project = QPushButton("+ New Project")
        new_project.setObjectName("primary")
        new_project.clicked.connect(self.create_customer_project)
        self.customer_layout.addWidget(new_project)

    def _build_project_content(self):
        self.project_header = QLabel("Project")
        self.project_header.setObjectName("pageTitle")
        self.project_layout.addWidget(self.project_header)

        self.project_details = QLabel("")
        self.project_details.setWordWrap(True)
        self.project_details.setObjectName("muted")
        self.project_layout.addWidget(self.project_details)

        self.project_tools = QGridLayout()
        self.project_layout.addLayout(self.project_tools)

        self.active_customer_id = None
        self.active_project_id = None
        self.active_project_context = None

    def _section_card(self, title, widget):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        header = QLabel(title)
        header.setObjectName("sectionTitle")
        layout.addWidget(header)
        layout.addWidget(widget)
        return card

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

    def show_home(self):
        self.content_stack.setCurrentWidget(self.home_page)

    def show_customer(self, customer_id):
        self.active_customer_id = customer_id
        self.active_project_id = None
        self.active_project_context = None
        self.customer_details.setText("Loading customer...")
        customer = self.customers.get(customer_id)
        if not customer:
            self.show_home()
            return
        self.customer_details.setText(
            f"<b>{customer['name']}</b><br>"
            f"Phone: {customer['phone'] or '—'}<br>"
            f"Email: {customer['email'] or '—'}<br>"
            f"Notes: {customer['notes'] or '—'}"
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT name, project_type, status, id FROM projects WHERE customer_id = ? ORDER BY updated_at DESC",
                (str(customer_id),),
            ).fetchall()
        self.customer_projects.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col, value in enumerate((row['name'], row['project_type'], row['status'])):
                item = QTableWidgetItem(value or "")
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row['id'])
                self.customer_projects.setItem(row_index, col, item)
        self.content_stack.setCurrentWidget(self.customer_page)

    def show_project(self, project_id):
        project_row = self.projects.get(project_id)
        if not project_row:
            self.show_home()
            return
        customer_row = self.customers.get(project_row['customer_id'])
        project_type = project_row['project_type']
        status = project_row['status']
        self.active_customer_id = project_row['customer_id']
        self.active_project_id = project_row['id']
        self.active_project_context = {
            "customer_id": project_row['customer_id'],
            "project_id": project_row['id'],
            "customer_name": customer_row['name'],
            "project_name": project_row['name'],
            "folder_path": project_row['folder_path'],
        }
        self.project_header.setText(
            f"{customer_row['name']}\n{project_row['name']}\nProject Type: {project_type}\nStatus: {status}"
        )

        while self.project_tools.count():
            item = self.project_tools.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if project_type == "Receipt Processing":
            tool_labels = ["Import Receipts", "Review Queue", "Export", "Upload to QuickBooks", "Archive"]
        elif project_type == "Media Transfer":
            tool_labels = ["Capture Video", "Trim Video", "Export MP4", "Archive"]
        elif project_type in {"Photo Scanning", "Document Scanning"}:
            tool_labels = ["Import Images", "OCR", "Rename", "Export", "Archive"]
        else:
            tool_labels = ["Open Folder", "Archive"]

        for index, tool in enumerate(tool_labels):
            button = QPushButton(tool)
            button.clicked.connect(lambda checked=False, text=tool: self.open_module(text))
            self.project_tools.addWidget(button, index // 3, index % 3)
        self.content_stack.setCurrentWidget(self.project_page)

    def open_module(self, name):
        if name == "Dashboard":
            return
        if name == "Receipt Manager":
            self.launch_receipt_manager_from_active_context()
            return
        if name in {"Import Receipts", "Review Queue", "Export"}:
            self.launch_receipt_manager_from_active_context(name)
            return
        if name in {"Upload to QuickBooks", "Archive", "Capture Video", "Trim Video", "Export MP4", "Import Images", "OCR", "Rename", "Open Folder"}:
            QMessageBox.information(self, name, f"{name} is available through the TLBS workflow layer.")
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

    def open_selected_customer(self):
        row = self.recent_customers_table.currentRow()
        if row < 0:
            return
        customer_item = self.recent_customers_table.item(row, 0)
        customer_id = customer_item.data(Qt.ItemDataRole.UserRole) if customer_item else None
        if customer_id:
            self.show_customer(customer_id)

    def open_selected_project(self):
        table = self.sender()
        row = table.currentRow()
        if row < 0:
            return
        item = table.item(row, 0)
        project_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if project_id:
            self.show_project(project_id)

    def continue_last_project(self):
        rows = self.projects.list_recent(1)
        if not rows:
            QMessageBox.information(self, "No project", "Create a customer and project to continue a workflow.")
            return
        self.show_project(rows[0]["id"])

    def launch_receipt_manager_from_active_context(self, tool_name: str | None = None):
        if not self.active_project_context:
            QMessageBox.information(
                self,
                "Select a Receipt Processing project",
                "Select or create a Receipt Processing project first, then launch the Receipt Manager from that active project context.",
            )
            return

        project_row = self.projects.get(self.active_project_context["project_id"])
        customer_row = self.customers.get(self.active_project_context["customer_id"])
        if not project_row or not customer_row:
            QMessageBox.warning(
                self,
                "Could not resolve project",
                "The active TLBS project could not be loaded.",
            )
            return

        if project_row["project_type"] != "Receipt Processing":
            QMessageBox.information(
                self,
                "Receipt Processing project required",
                "The Receipt Manager launcher requires an active Receipt Processing project. Select or create one from the customer/project workflow.",
            )
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

        if tool_name == "Import Receipts":
            message = "The Receipt Manager is now open with the active receipt job context for this TLBS project. Use the legacy Import Receipts dialog to move files into Incoming."
        elif tool_name == "Review Queue":
            message = "The Receipt Manager is now open with the active receipt job context for this TLBS project. Use the legacy Review Receipts workflow to inspect the queued outputs."
        elif tool_name == "Export":
            message = "The Receipt Manager is now open with the active receipt job context for this TLBS project. Use the existing legacy export flow from the Receipt Manager window."
        else:
            message = f"Receipt Manager job created for {customer.name} / {project.name}."

        QMessageBox.information(self, "Receipt Manager launched", message)

    def refresh(self):
        customer_rows = self.customers.list_recent(5)
        self.recent_customers_table.setRowCount(len(customer_rows))
        for row_index, row in enumerate(customer_rows):
            for col, value in enumerate((row["name"], row["phone"], row["email"])):
                item = QTableWidgetItem(value or "")
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.recent_customers_table.setItem(row_index, col, item)

        active_projects = self.projects.list_recent(10)
        self.active_projects_table.setRowCount(len(active_projects))
        for row_index, row in enumerate(active_projects):
            values = (
                row["customer_name"],
                row["name"],
                row["status"],
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value or "")
                if col == 1:
                    item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.active_projects_table.setItem(row_index, col, item)

        last_project = self.projects.list_recent(1)
        if last_project:
            self.last_project_label.setText(
                f"{last_project[0]['customer_name']} • {last_project[0]['name']}"
            )

        activities = self.activities.list_recent(7)
        self.activity_feed.clear()
        for activity in activities:
            timestamp = datetime.fromisoformat(activity["occurred_at"])
            self.activity_feed.addItem(
                f"{activity['title']}\n{activity['details'] or ''}\n{timestamp:%b %d, %I:%M %p}"
            )

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
