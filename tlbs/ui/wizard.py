from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QRadioButton,
    QTextEdit, QVBoxLayout, QWizard, QWizardPage
)

from ..core.models import Customer, Project, ProjectStatus, ProjectType
from ..core.services import CustomerService


class CustomerModePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Who is this project for?")
        self.setSubTitle("Create a new customer or add a project to an existing customer.")

        self.new_customer = QRadioButton("Create a new customer")
        self.existing_customer = QRadioButton("Use an existing customer")
        self.new_customer.setChecked(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.new_customer)
        layout.addWidget(self.existing_customer)
        layout.addStretch()


class CustomerDetailsPage(QWizardPage):
    def __init__(self, customer_service: CustomerService):
        super().__init__()
        self.customer_service = customer_service
        self.setTitle("Customer details")
        self.setSubTitle("Enter the main contact information.")

        self.existing_list = QListWidget()
        self.name = QLineEdit()
        self.company = QLineEdit()
        self.email = QLineEdit()
        self.phone = QLineEdit()
        self.address = QLineEdit()
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(80)

        self.existing_group = QGroupBox("Existing customers")
        existing_layout = QVBoxLayout(self.existing_group)
        existing_layout.addWidget(self.existing_list)

        self.new_group = QGroupBox("New customer")
        form = QFormLayout(self.new_group)
        form.addRow("Name *", self.name)
        form.addRow("Company", self.company)
        form.addRow("Email", self.email)
        form.addRow("Phone", self.phone)
        form.addRow("Address", self.address)
        form.addRow("Notes", self.notes)

        layout = QVBoxLayout(self)
        layout.addWidget(self.existing_group)
        layout.addWidget(self.new_group)

    def initializePage(self):
        wizard = self.wizard()
        use_existing = wizard.mode_page.existing_customer.isChecked()
        self.existing_group.setVisible(use_existing)
        self.new_group.setVisible(not use_existing)

        if use_existing:
            self.existing_list.clear()
            for row in self.customer_service.list_all():
                label = row["name"]
                if row["company"]:
                    label += f" — {row['company']}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, dict(row))
                self.existing_list.addItem(item)
            if self.existing_list.count():
                self.existing_list.setCurrentRow(0)

    def validatePage(self):
        wizard = self.wizard()
        if wizard.mode_page.existing_customer.isChecked():
            if not self.existing_list.currentItem():
                QMessageBox.information(
                    self, "Select a customer", "Select an existing customer."
                )
                return False
            return True

        if not self.name.text().strip():
            QMessageBox.information(
                self, "Name required", "Enter the customer's name."
            )
            return False
        return True

    def selected_customer(self) -> Customer:
        row = self.existing_list.currentItem().data(Qt.ItemDataRole.UserRole)
        return Customer(
            id=UUID(row["id"]),
            name=row["name"],
            company=row["company"],
            email=row["email"],
            phone=row["phone"],
            address=row["address"],
            notes=row["notes"],
        )

    def new_customer_value(self) -> Customer:
        return Customer(
            name=self.name.text().strip(),
            company=self.company.text().strip(),
            email=self.email.text().strip(),
            phone=self.phone.text().strip(),
            address=self.address.text().strip(),
            notes=self.notes.toPlainText().strip(),
        )


class ProjectDetailsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Project details")
        self.setSubTitle("Choose the work type and name the project.")

        self.project_type = QComboBox()
        for value in ProjectType:
            self.project_type.addItem(value.value, value)

        self.name = QLineEdit()
        self.status = QComboBox()
        for value in ProjectStatus:
            self.status.addItem(value.value, value)
        self.status.setCurrentText(ProjectStatus.ACTIVE.value)

        self.due_enabled = QCheckBox("Set a due date")
        self.due_date = QDateEdit()
        self.due_date.setCalendarPopup(True)
        self.due_date.setDate(datetime.now().date())
        self.due_date.setEnabled(False)
        self.due_enabled.toggled.connect(self.due_date.setEnabled)

        self.description = QTextEdit()
        self.description.setMaximumHeight(90)

        form = QFormLayout(self)
        form.addRow("Project type *", self.project_type)
        form.addRow("Project name *", self.name)
        form.addRow("Status", self.status)
        form.addRow(self.due_enabled, self.due_date)
        form.addRow("Description", self.description)

        self.project_type.currentIndexChanged.connect(self._suggest_name)

    def initializePage(self):
        if not self.name.text().strip():
            self._suggest_name()

    def _suggest_name(self):
        project_type = self.project_type.currentData()
        if not project_type:
            return
        if self.name.text().strip() and not self.name.property("autoSuggested"):
            return
        self.name.setText(f"{datetime.now():%Y} {project_type.value}")
        self.name.setProperty("autoSuggested", True)

    def validatePage(self):
        if not self.name.text().strip():
            QMessageBox.information(
                self, "Project name required", "Enter a project name."
            )
            return False
        return True

    def project_value(self, customer_id) -> Project:
        due = None
        if self.due_enabled.isChecked():
            qdate = self.due_date.date()
            due = datetime(qdate.year(), qdate.month(), qdate.day())

        return Project(
            customer_id=customer_id,
            name=self.name.text().strip(),
            project_type=self.project_type.currentData(),
            status=self.status.currentData(),
            description=self.description.toPlainText().strip(),
            due_date=due,
        )


class ConfirmationPage(QWizardPage):
    def __init__(self, projects_root: Path):
        super().__init__()
        self.projects_root = projects_root
        self.setTitle("Ready to create")
        self.setSubTitle("Review the summary, then click Finish.")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addStretch()

    def initializePage(self):
        wizard = self.wizard()
        if wizard.mode_page.existing_customer.isChecked():
            customer = wizard.customer_page.selected_customer()
            customer_mode = "Existing customer"
        else:
            customer = wizard.customer_page.new_customer_value()
            customer_mode = "New customer"

        project = wizard.project_page.project_value(customer.id)
        projected_folder = self.projects_root / customer.name / project.name

        self.summary.setText(
            f"<b>{customer_mode}</b><br>"
            f"Customer: {customer.name}<br>"
            f"Company: {customer.company or '—'}<br><br>"
            f"<b>Project</b><br>"
            f"Name: {project.name}<br>"
            f"Type: {project.project_type.value}<br>"
            f"Status: {project.status.value}<br><br>"
            f"<b>Project folder</b><br>{projected_folder}"
        )


class CustomerProjectWizard(QWizard):
    def __init__(
        self,
        customer_service: CustomerService,
        projects_root: Path,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("New Customer / Project")
        self.setMinimumSize(680, 520)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

        self.mode_page = CustomerModePage()
        self.customer_page = CustomerDetailsPage(customer_service)
        self.project_page = ProjectDetailsPage()
        self.confirmation_page = ConfirmationPage(projects_root)

        self.addPage(self.mode_page)
        self.addPage(self.customer_page)
        self.addPage(self.project_page)
        self.addPage(self.confirmation_page)

    def values(self):
        existing = self.mode_page.existing_customer.isChecked()
        customer = (
            self.customer_page.selected_customer()
            if existing
            else self.customer_page.new_customer_value()
        )
        project = self.project_page.project_value(customer.id)
        return existing, customer, project
