from __future__ import annotations

import csv
import os
import re
import shutil
from datetime import datetime
from tempfile import NamedTemporaryFile
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence, QMouseEvent, QPixmap, QTransform, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from database import Database
from window_geometry import restore_or_center, save_window_geometry

APP_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = APP_ROOT / "data" / "tapelady_receipts.db"
APP_ICON = APP_ROOT / "assets" / "TapeLadySuite8.ico"

CATEGORIES = [
    "Advertising & Marketing",
    "Automobile Expense",
    "Bank Charges & Fees",
    "Computer & Internet Expenses",
    "Contract Labor",
    "Dues & Subscriptions",
    "Equipment",
    "Insurance",
    "Meals",
    "Office Supplies",
    "Postage & Shipping",
    "Professional Fees",
    "Repairs & Maintenance",
    "Software & Subscriptions",
    "Supplies",
    "Telephone",
    "Travel",
    "Utilities",
    "Uncategorized Expense",
]


class ZoomScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.owner = None

    def wheelEvent(self, event: QWheelEvent):
        if self.owner:
            if event.angleDelta().y() > 0:
                self.owner.zoom_in()
            else:
                self.owner.zoom_out()
            event.accept()
            return

        super().wheelEvent(event)


class ZoomableImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.owner = None
        self.dragging = False
        self.last_mouse_position = QPoint()
        self.setCursor(Qt.OpenHandCursor)

    def wheelEvent(self, event: QWheelEvent):
        if not self.owner:
            return

        if event.angleDelta().y() > 0:
            self.owner.zoom_in()
        else:
            self.owner.zoom_out()

        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.owner:
            self.owner.fit_image()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_mouse_position = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.dragging and self.owner:
            current_position = event.position().toPoint()
            delta = current_position - self.last_mouse_position
            self.last_mouse_position = current_position

            horizontal = self.owner.scroll.horizontalScrollBar()
            vertical = self.owner.scroll.verticalScrollBar()

            horizontal.setValue(horizontal.value() - delta.x())
            vertical.setValue(vertical.value() - delta.y())

        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.OpenHandCursor)
        event.accept()


class ReviewWindow(QMainWindow):
    def __init__(self, job_root: Path, ready_threshold: float = 0.92, auto_approve_threshold: float = 0.95):
        super().__init__()

        self.job_root = job_root
        self.ready_threshold = ready_threshold
        self.auto_approve_threshold = auto_approve_threshold
        self.csv_path = job_root / "Exports" / "receipt_review_accuracy.csv"
        self.approved_dir = job_root / "Approved"
        self.rejected_dir = job_root / "Rejected"
        self.approved_dir.mkdir(parents=True, exist_ok=True)
        self.rejected_dir.mkdir(parents=True, exist_ok=True)

        self.db = Database(DB_PATH)
        self.rows: list[dict[str, str]] = []
        self.filtered_indexes: list[int] = []
        self.position = 0
        self.loading_row = False
        self.original_pixmap = QPixmap()
        self.rotation = 0
        self.zoom_factor = 1.0
        self.summary_labels: dict[str, QLabel] = {}

        self.setWindowTitle("Review Receipts")
        if APP_ICON.exists():
            self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1450, 880)

        self.build_ui()
        self.build_shortcuts()
        self.load_csv()
        restore_or_center(self, "review_window")

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(10)

        dashboard = QFrame()
        dashboard.setObjectName("smartReviewDashboard")
        dashboard_layout = QGridLayout(dashboard)
        dashboard_layout.setContentsMargins(12, 8, 12, 8)
        dashboard_layout.setHorizontalSpacing(8)
        dashboard_layout.setVerticalSpacing(5)
        dashboard_title = QLabel("Smart Review Dashboard")
        dashboard_title.setObjectName("pageTitle")
        dashboard_layout.addWidget(dashboard_title, 0, 0, 1, 5)
        cards = [
            ("processed", "Total Receipts"),
            ("ready", "Ready"),
            ("review", "Needs Review"),
            ("refunds", "Refunds"),
            ("duplicates", "Duplicates"),
        ]
        for column, (key, caption) in enumerate(cards):
            card = QFrame()
            card.setObjectName("accentCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 6, 10, 6)
            card_layout.setSpacing(2)
            value = QLabel("0")
            value.setAlignment(Qt.AlignCenter)
            value.setStyleSheet("font-size: 20px; font-weight: bold; color: #e7c885;")
            label = QLabel(caption)
            label.setAlignment(Qt.AlignCenter)
            label.setObjectName("mutedText")
            card_layout.addWidget(value)
            card_layout.addWidget(label)
            dashboard_layout.addWidget(card, 1, column)
            self.summary_labels[key] = value
        self.average_confidence = QLabel("Average confidence: —")
        self.average_confidence.setStyleSheet("font-weight: bold; color: #83bd6b;")
        dashboard_layout.addWidget(self.average_confidence, 2, 0, 1, 5)
        outer.addWidget(dashboard)

        filter_row = QHBoxLayout()
        self.progress = QProgressBar()
        filter_row.addWidget(self.progress, 1)

        self.show_ready = QCheckBox("Ready")
        self.show_ready.setChecked(False)
        self.show_review = QCheckBox("Review")
        self.show_review.setChecked(True)
        self.show_problem = QCheckBox("Problem")
        self.show_problem.setChecked(True)

        for checkbox in (
            self.show_ready,
            self.show_review,
            self.show_problem,
        ):
            checkbox.stateChanged.connect(self.apply_filter)
            filter_row.addWidget(checkbox)

        outer.addLayout(filter_row)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)

        self.title = QLabel("Receipt")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setObjectName("pageTitle")
        left_layout.addWidget(self.title)

        image_tools = QHBoxLayout()
        for label, callback in [
            ('Zoom In', self.zoom_in),
            ('Zoom Out', self.zoom_out),
            ('Fit', self.fit_image),
            ('Rotate Left', self.rotate_left),
            ('Rotate Right', self.rotate_right),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            image_tools.addWidget(button)
        left_layout.addLayout(image_tools)

        self.scroll = ZoomScrollArea()
        self.scroll.owner = self
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignCenter)

        self.image = ZoomableImageLabel()
        self.image.owner = self
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(480, 420)
        self.image.setMouseTracking(True)

        self.scroll.setWidget(self.image)
        left_layout.addWidget(self.scroll, 1)
        splitter.addWidget(left)

        # The extracted-information side can be taller than smaller displays.
        # Keep the title and action buttons visible while allowing the form cards
        # to scroll independently instead of disappearing below the screen.
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        panel_title = QLabel("Extracted Information")
        panel_title.setObjectName("pageTitle")
        right_layout.addWidget(panel_title)

        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setFrameShape(QFrame.NoFrame)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        details_scroll.setObjectName("detailsScroll")

        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 4, 0)
        details_layout.setSpacing(8)
        details_scroll.setWidget(details_widget)
        right_layout.addWidget(details_scroll, 1)

        self.vendor = QLineEdit()
        self.vendor.editingFinished.connect(self.apply_vendor_memory)

        self.date = QLineEdit()
        self.subtotal = QLineEdit()
        self.tax = QLineEdit()
        self.tip = QLineEdit()
        self.total = QLineEdit()

        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(CATEGORIES)

        self.payment = QLineEdit()
        self.last4 = QLineEdit()
        self.last4.setMaxLength(4)

        self.receipt_health = QLabel()
        self.status = QLabel()
        self.confidence = QLabel()
        self.transaction_type = QLabel()
        self.confidence_breakdown = QLabel()
        self.confidence_breakdown.setWordWrap(True)
        self.vendor_memory = QLabel()
        self.vendor_memory.setWordWrap(True)
        self.merchant_profile = QLabel()
        self.merchant_profile.setWordWrap(True)
        self.extraction_checks = QLabel()
        self.extraction_checks.setWordWrap(True)
        self.reason = QLabel()
        self.reason.setWordWrap(True)

        def add_section(title, rows):
            card = QFrame()
            card.setObjectName("panelCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(8)
            heading = QLabel(title)
            heading.setObjectName("sectionTitle")
            layout.addWidget(heading)
            form = QFormLayout()
            form.setContentsMargins(0, 0, 0, 0)
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(8)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            form.setFormAlignment(Qt.AlignTop)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for label, widget in rows:
                form.addRow(label, widget)
            layout.addLayout(form)
            details_layout.addWidget(card)

        add_section("Receipt Details", [
            ("Vendor", self.vendor),
            ("Date", self.date),
            ("Transaction", self.transaction_type),
            ("Payment", self.payment),
            ("Last 4", self.last4),
        ])
        add_section("Financials", [
            ("Subtotal", self.subtotal),
            ("Tax", self.tax),
            ("Tip", self.tip),
            ("Total", self.total),
            ("Category", self.category),
        ])
        add_section("Verification", [
            ("Receipt Health", self.receipt_health),
            ("Status", self.status),
            ("Confidence", self.confidence),
            ("Confidence Details", self.confidence_breakdown),
            ("Extraction Checks", self.extraction_checks),
            ("Decision Details", self.reason),
        ])
        add_section("Merchant Memory", [
            ("Vendor Memory", self.vendor_memory),
            ("Merchant Profile", self.merchant_profile),
        ])

        details_layout.addStretch(1)

        export_button = QPushButton("Export Final CSV")
        export_button.setObjectName("accentButton")
        export_button.clicked.connect(self.export_final_csv)
        right_layout.addWidget(export_button)

        self.dry_run = QCheckBox("Dry Run (don't move files)")
        self.dry_run.setChecked(True)
        right_layout.addWidget(self.dry_run)

        buttons = QHBoxLayout()

        for text, callback in [
            ("Previous", self.previous),
            ("Needs Review", lambda: self.mark_status("NEEDS REVIEW")),
            ("Flag", lambda: self.mark_status("FLAGGED")),
            ("Reject", self.reject_current),
            ("Approve", self.approve_current),
            ("⭐ Auto Approve", self.auto_approve),
            ("Next", self.next),
        ]:
            button = QPushButton(text)
            if text in ("Approve", "⭐ Auto Approve"): button.setObjectName("primaryButton")
            if text == "Reject": button.setObjectName("dangerButton")
            button.clicked.connect(callback)
            buttons.addWidget(button)

        right_layout.addLayout(buttons)
        splitter.addWidget(right)
        splitter.setSizes([900, 550])

        self.statusBar().showMessage(
            "Enter=Approve | X=Reject | R=Needs Review | F=Flag | "
            "Space/Right=Next | Left=Previous | Wheel=Zoom | Double-click=Fit | Drag=Pan"
        )

    def build_shortcuts(self):
        shortcuts = [
            ("Approve", "Return", self.approve_current),
            ("Approve2", "Enter", self.approve_current),
            ("Needs Review", "R", lambda: self.mark_status("NEEDS REVIEW")),
            ("Flag", "F", lambda: self.mark_status("FLAGGED")),
            ("Reject", "X", self.reject_current),
            ("Export Final CSV", "Ctrl+E", self.export_final_csv),
            ("Next", "Space", self.next),
            ("Next2", "Right", self.next),
            ("Previous", "Left", self.previous),
            ("Zoom In", "+", self.zoom_in),
            ("Zoom Out", "-", self.zoom_out),
            ("Fit Image", "0", self.fit_image),
            ("Rotate Left", "Ctrl+Left", self.rotate_left),
            ("Rotate Right", "Ctrl+Right", self.rotate_right),
            ("Save", "Ctrl+S", self.save),
        ]

        for name, key, callback in shortcuts:
            action = QAction(name, self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(callback)
            self.addAction(action)

    def load_csv(self):
        if not self.csv_path.exists():
            QMessageBox.information(self, "No receipts", "No review file found.")
            self.close()
            return

        with self.csv_path.open(
            "r",
            newline="",
            encoding="utf-8-sig",
        ) as file:
            self.rows = list(csv.DictReader(file))

        for row in self.rows:
            row.setdefault("Rejection Reason", "")
            row.setdefault("Tip", "")

        if not self.rows:
            QMessageBox.information(self, "No receipts", "No receipt rows found.")
            self.close()
            return

        self.detect_near_duplicates()
        self.update_dashboard()
        self.apply_filter()

    def allowed_statuses(self) -> set[str]:
        allowed: set[str] = set()

        if self.show_ready.isChecked():
            allowed.update({"READY", "APPROVE", "COMPLETED"})
        if self.show_review.isChecked():
            allowed.update({"REVIEW", "NEEDS REVIEW", "FLAGGED"})
        if self.show_problem.isChecked():
            allowed.add("PROBLEM")

        return allowed

    def apply_filter(self):
        if not self.rows:
            return

        self.update_dashboard()
        allowed = self.allowed_statuses()
        self.filtered_indexes = [
            index
            for index, row in enumerate(self.rows)
            if row.get("Approval Status", "").strip().upper() in allowed
        ]
        self.position = 0

        if not self.filtered_indexes:
            self.image.clear()
            self.title.setText("No receipts match the selected filters.")
            self.progress.setMaximum(1)
            self.progress.setValue(0)
            return

        self.show_row()

    def current_global_index(self) -> int:
        return self.filtered_indexes[self.position]

    def current_row(self) -> dict[str, str]:
        return self.rows[self.current_global_index()]

    def save_fields(self):
        if not self.filtered_indexes:
            return

        row = self.current_row()
        row["Vendor"] = self.vendor.text().strip()
        row["Date"] = self.date.text().strip()
        row["Subtotal"] = self.subtotal.text().strip()
        row["Tax"] = self.tax.text().strip()
        row["Tip"] = self.tip.text().strip()
        row["Total"] = self.total.text().strip()
        row["Category"] = self.category.currentText().strip()
        row["Payment Method"] = self.payment.text().strip()
        row["Last 4"] = self.last4.text().strip()

    def backup_csv(self, label: str) -> Path | None:
        if not self.csv_path.exists():
            return None
        folder = self.csv_path.parent / "Backups"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destination = folder / f"{self.csv_path.stem}_{label}_{stamp}{self.csv_path.suffix}"
        shutil.copy2(self.csv_path, destination)
        return destination

    def write_csv(self):
        if not self.rows:
            return
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(dict.fromkeys(
            key for row in self.rows for key in row.keys()
        ))
        with NamedTemporaryFile("w", delete=False, dir=self.csv_path.parent, newline="", encoding="utf-8-sig", suffix=".tmp") as file:
            temp_path = Path(file.name)
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.rows)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(self.csv_path)

    def save(self):
        if not self.rows:
            return

        self.save_fields()
        self.write_csv()
        self.statusBar().showMessage("Saved", 1500)

    def show_row(self):
        if not self.filtered_indexes:
            return

        self.loading_row = True
        row = self.current_row()

        self.vendor.setText(row.get("Vendor", ""))
        self.date.setText(row.get("Date", ""))
        self.subtotal.setText(row.get("Subtotal", ""))
        self.tax.setText(row.get("Tax", ""))
        self.tip.setText(row.get("Tip", ""))
        self.total.setText(row.get("Total", ""))
        self.category.setCurrentText(row.get("Category", ""))
        self.payment.setText(row.get("Payment Method", ""))
        self.last4.setText(row.get("Last 4", ""))

        status = row.get("Approval Status", "").strip().upper()
        status_labels = {
            "READY": "READY — Ready for Approval",
            "APPROVE": "APPROVE — Eligible for Auto Approval",
            "REVIEW": "REVIEW — Manual Review Required",
            "NEEDS REVIEW": "NEEDS REVIEW — Manual Review Required",
            "FLAGGED": "FLAGGED — Attention Required",
            "PROBLEM": "PROBLEM — Processing Issue",
            "COMPLETED": "COMPLETED",
            "REJECTED": "REJECTED — Excluded from Final CSV",
        }
        self.status.setText(status_labels.get(status, status or "UNKNOWN"))

        confidence_text = row.get("Overall Confidence", "")
        try:
            confidence_value = float(confidence_text)
        except ValueError:
            confidence_value = 0.0

        self.confidence.setText(f"{confidence_value:.0%}")
        health, health_color = self.receipt_health_for(row, confidence_value)
        self.receipt_health.setText(health)
        self.receipt_health.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {health_color};"
        )
        transaction = row.get("Transaction Type", "PURCHASE").strip().upper() or "PURCHASE"
        self.transaction_type.setText(transaction)
        self.transaction_type.setStyleSheet(
            "font-weight: bold; color: #6a1b9a;" if transaction == "REFUND"
            else "font-weight: bold; color: #444444;"
        )
        breakdown = row.get("Confidence Breakdown", "").strip()
        self.confidence_breakdown.setText(
            breakdown.replace(" | ", "\n") if breakdown else "Not available for older records"
        )
        self.confidence_breakdown.setStyleSheet("color: #555555;")

        if confidence_value >= self.auto_approve_threshold:
            confidence_color = "#2e7d32"
        elif confidence_value >= 0.75:
            confidence_color = "#b26a00"
        else:
            confidence_color = "#b71c1c"

        status_colors = {
            "READY": "#b26a00",
            "APPROVE": "#2e7d32",
            "REVIEW": "#b26a00",
            "NEEDS REVIEW": "#b26a00",
            "FLAGGED": "#b71c1c",
            "PROBLEM": "#b71c1c",
            "COMPLETED": "#2e7d32",
            "REJECTED": "#b71c1c",
        }
        status_color = status_colors.get(status, "#444444")

        self.confidence.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {confidence_color};"
        )
        self.status.setStyleSheet(
            f"font-weight: bold; color: {status_color};"
        )
        self.extraction_checks.setText(self.build_extraction_checks(row))
        self.extraction_checks.setStyleSheet("line-height: 1.3;")
        self.reason.setText(self.build_decision_details(row, confidence_value))
        self.merchant_profile.setText(self.build_merchant_profile(row.get("Vendor", "")))
        self.merchant_profile.setStyleSheet("color: #44515c;")

        self.progress.setMaximum(len(self.filtered_indexes))
        self.progress.setValue(self.position + 1)

        self.title.setText(
            f"{self.position + 1} / {len(self.filtered_indexes)} — "
            f"{row.get('Original File', '')}"
        )

        self.load_image(row)
        self.loading_row = False
        self.apply_vendor_memory()

    def detect_near_duplicates(self) -> None:
        groups: dict[tuple[str, str, str], list[dict[str, str]]] = {}
        for row in self.rows:
            key = (
                row.get("Vendor", "").strip().casefold(),
                row.get("Date", "").strip(),
                row.get("Total", "").strip().replace("$", "").replace(",", ""),
            )
            if all(key):
                groups.setdefault(key, []).append(row)
        for matches in groups.values():
            if len(matches) > 1:
                for row in matches:
                    if not row.get("Possible Duplicate", "").strip():
                        row["Possible Duplicate"] = "YES"

    def update_dashboard(self) -> None:
        if not self.rows or not self.summary_labels:
            return
        statuses = [row.get("Approval Status", "").strip().upper() for row in self.rows]
        ready = sum(status in {"READY", "APPROVE", "COMPLETED"} for status in statuses)
        review = sum(status in {"REVIEW", "NEEDS REVIEW", "FLAGGED", "PROBLEM"} for status in statuses)
        refunds = sum(row.get("Transaction Type", "").strip().upper() == "REFUND" for row in self.rows)
        duplicates = sum(row.get("Possible Duplicate", "").strip().upper() == "YES" for row in self.rows)
        self.summary_labels["processed"].setText(str(len(self.rows)))
        self.summary_labels["ready"].setText(str(ready))
        self.summary_labels["review"].setText(str(review))
        self.summary_labels["refunds"].setText(str(refunds))
        self.summary_labels["duplicates"].setText(str(duplicates))
        confidences = []
        for row in self.rows:
            try:
                confidences.append(float(row.get("Overall Confidence", "")))
            except (TypeError, ValueError):
                pass
        self.average_confidence.setText(
            f"Average confidence: {sum(confidences) / len(confidences):.1%}"
            if confidences else "Average confidence: —"
        )

    def receipt_health_for(self, row: dict[str, str], confidence: float) -> tuple[str, str]:
        status = row.get("Approval Status", "").strip().upper()
        duplicate = row.get("Possible Duplicate", "").strip().upper() == "YES"
        math_failed = row.get("Math Check", "").strip().upper() == "FAIL"
        missing_required = any(not row.get(key, "").strip() for key in ("Vendor", "Date", "Total"))
        if status == "PROBLEM" or confidence < 0.60:
            return "Critical — Manual Review", "#b71c1c"
        if duplicate or math_failed or missing_required or status == "FLAGGED":
            return "Needs Attention", "#c45100"
        if confidence >= self.auto_approve_threshold and status in {"READY", "APPROVE", "COMPLETED"}:
            return "Excellent — Ready to Export", "#2e7d32"
        if confidence >= self.ready_threshold:
            return "Good — Quick Review", "#657000"
        return "Review Recommended", "#b26a00"

    def build_merchant_profile(self, vendor: str) -> str:
        vendor_key = vendor.strip().casefold()
        if not vendor_key:
            return "Vendor not identified"
        matches = [row for row in self.rows if row.get("Vendor", "").strip().casefold() == vendor_key]
        if not matches:
            return "New vendor"
        confidences = []
        categories: dict[str, int] = {}
        payments: dict[str, int] = {}
        for row in matches:
            try:
                confidences.append(float(row.get("Overall Confidence", "")))
            except (TypeError, ValueError):
                pass
            category = row.get("Category", "").strip()
            payment = row.get("Payment Method", "").strip()
            if category:
                categories[category] = categories.get(category, 0) + 1
            if payment:
                payments[payment] = payments.get(payment, 0) + 1
        typical_category = max(categories, key=categories.get) if categories else "Not learned yet"
        typical_payment = max(payments, key=payments.get) if payments else "Not learned yet"
        average = f"{sum(confidences) / len(confidences):.1%}" if confidences else "—"
        return (
            f"Seen in this batch: {len(matches)}\n"
            f"Average confidence: {average}\n"
            f"Typical category: {typical_category}\n"
            f"Typical payment: {typical_payment}"
        )

    def build_extraction_checks(self, row: dict[str, str]) -> str:
        checks: list[str] = []

        def field_check(label: str, key: str, optional: bool = False):
            value = row.get(key, "").strip()
            if value:
                checks.append(f"✅ {label} captured")
            elif optional:
                checks.append(f"⚪ {label} not shown or not captured")
            else:
                checks.append(f"❌ {label} missing")

        field_check("Vendor", "Vendor")
        field_check("Date", "Date")
        field_check("Subtotal", "Subtotal", optional=True)
        field_check("Tax", "Tax", optional=True)
        field_check("Tip", "Tip", optional=True)
        field_check("Total", "Total")

        math_result = row.get("Math Check", "").strip().upper()
        if math_result == "PASS":
            checks.append("✅ Math verified")
        elif math_result == "FAIL":
            checks.append("❌ Subtotal + tax does not match total")
        else:
            checks.append("⚪ Math check not available")

        date_result = row.get("Date Check", "").strip().upper()
        if date_result == "PASS":
            checks.append("✅ Date is within the expected range")
        elif date_result:
            checks.append(f"⚠ Date check: {date_result}")

        duplicate = row.get("Possible Duplicate", "").strip().upper()
        if duplicate == "YES":
            checks.append("⚠ Possible duplicate")
        elif duplicate == "NO":
            checks.append("✅ No duplicate detected")

        verification = row.get("Verification Result", "").strip().upper()
        if verification == "PASS":
            checks.append("✅ Independent verification passed")
        elif verification == "REVIEW":
            checks.append("⚠ Independent verification requested review")
        elif verification == "FAIL":
            checks.append("❌ Independent verification failed")

        return "\n".join(checks)

    def build_decision_details(
        self,
        row: dict[str, str],
        confidence_value: float,
    ) -> str:
        status = row.get("Approval Status", "").strip().upper()
        details: list[str] = []

        if status in {"REVIEW", "NEEDS REVIEW"}:
            if confidence_value < self.auto_approve_threshold:
                details.append(
                    f"Overall confidence is {confidence_value:.0%}, below the "
                    f"{self.auto_approve_threshold:.0%} Auto Approve threshold."
                )
            else:
                details.append(
                    "Confidence meets the Auto Approve threshold, but another "
                    "validation rule requires review."
                )
        elif status == "READY":
            if confidence_value >= self.auto_approve_threshold:
                details.append(
                    "All required fields passed validation and this receipt is "
                    "eligible for Auto Approve."
                )
            else:
                details.append(
                    f"All required fields passed validation. Confidence is "
                    f"{confidence_value:.0%}, below the configured Auto Approve threshold, "
                    "so one-click approval is required."
                )
        elif status == "APPROVE":
            details.append(
                "All required fields passed validation and confidence meets the "
                f"{self.auto_approve_threshold:.0%} Auto Approve threshold."
            )
        elif status == "FLAGGED":
            details.append("This receipt was manually flagged for attention.")
        elif status == "PROBLEM":
            stored_reason = row.get("Review Reason", "").strip()
            if stored_reason:
                details.extend(
                    part.strip()
                    for part in stored_reason.split(";")
                    if part.strip()
                )
            else:
                details.append("The receipt could not be processed reliably.")
        elif status == "COMPLETED":
            details.append("This receipt has been approved and moved to Completed.")
        elif status == "REJECTED":
            reason = row.get("Rejection Reason", "").strip() or "Excluded from bookkeeping export."
            details.append(f"Rejected: {reason}")

        if not row.get("Vendor", "").strip():
            details.append("Vendor is missing.")
        if not row.get("Date", "").strip():
            details.append("Date is missing.")
        if not row.get("Total", "").strip():
            details.append("Total is missing.")
        if row.get("Math Check", "").strip().upper() == "FAIL":
            details.append("Subtotal plus tax does not match the total.")
        date_check = row.get("Date Check", "").strip().upper()
        if date_check and date_check != "PASS":
            details.append(f"Date check requires attention: {date_check}.")
        if row.get("Possible Duplicate", "").strip().upper() == "YES":
            details.append("A possible duplicate was detected.")
        if row.get("Verification Result", "").strip().upper() == "REVIEW":
            details.append("Independent verification requested manual review.")
        if row.get("Verification Result", "").strip().upper() == "FAIL":
            details.append("Independent verification failed.")

        if not details:
            details.append("No review concerns were detected.")

        # Preserve order while removing duplicate messages.
        unique_details = list(dict.fromkeys(details))
        return "\n".join(f"• {detail}" for detail in unique_details)

    def apply_vendor_memory(self):
        if self.loading_row:
            return

        vendor = self.vendor.text().strip()
        defaults = self.db.get_vendor_default(vendor)

        if not defaults:
            self.vendor_memory.setText("New vendor")
            self.vendor_memory.setStyleSheet("color: #666666;")
            return

        applied = []

        if defaults["category"]:
            self.category.setCurrentText(defaults["category"])
            applied.append(f"Category: {defaults['category']}")

        if defaults["payment_method"]:
            self.payment.setText(defaults["payment_method"])
            applied.append(f"Payment: {defaults['payment_method']}")


        self.vendor_memory.setText(
            "Applied remembered defaults"
            + (":\n" + "\n".join(applied) if applied else "")
        )
        self.vendor_memory.setStyleSheet(
            "font-weight: bold; color: #2e7d32;"
        )

    def load_image(self, row: dict[str, str]):
        candidates: list[Path] = []

        source_path = row.get("Source Path", "").strip()
        if source_path:
            candidates.append(self.job_root / source_path)

        original_name = row.get("Original File", "").strip()
        variant = row.get("Best Image Variant", "").strip()

        if original_name and variant:
            stem = Path(original_name).stem
            candidates.insert(
                0,
                self.job_root / "Enhanced" / stem / f"{stem}_{variant}.jpg",
            )

        if original_name:
            candidates.append(self.job_root / "Originals" / original_name)

        image_path = next((path for path in candidates if path.exists()), None)

        if not image_path:
            self.original_pixmap = QPixmap()
            self.image.setText("Image not found")
            return

        self.original_pixmap = QPixmap(str(image_path))

        if self.original_pixmap.isNull():
            self.image.setText("Could not load image")
            return

        self.rotation = (
            90
            if self.original_pixmap.width() > self.original_pixmap.height() * 1.15
            else 0
        )
        self.fit_image()

    def rotated_pixmap(self) -> QPixmap:
        if self.original_pixmap.isNull():
            return QPixmap()

        return self.original_pixmap.transformed(
            QTransform().rotate(self.rotation),
            Qt.SmoothTransformation,
        )

    def render_image(self):
        pixmap = self.rotated_pixmap()
        if pixmap.isNull():
            return

        width = max(100, int(pixmap.width() * self.zoom_factor))
        height = max(100, int(pixmap.height() * self.zoom_factor))

        scaled = pixmap.scaled(
            width,
            height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        self.image.setPixmap(scaled)
        self.image.resize(scaled.size())

    def fit_image(self):
        pixmap = self.rotated_pixmap()
        if pixmap.isNull():
            return

        viewport = self.scroll.viewport().size()
        available_width = max(100, viewport.width() - 30)
        available_height = max(100, viewport.height() - 30)

        self.zoom_factor = min(
            available_width / max(pixmap.width(), 1),
            available_height / max(pixmap.height(), 1),
        )
        self.render_image()

        horizontal = self.scroll.horizontalScrollBar()
        vertical = self.scroll.verticalScrollBar()
        horizontal.setValue(horizontal.maximum() // 2)
        vertical.setValue(vertical.maximum() // 2)

    def zoom_in(self):
        self.zoom_factor = min(self.zoom_factor * 1.20, 6.0)
        self.render_image()

    def zoom_out(self):
        self.zoom_factor = max(self.zoom_factor / 1.20, 0.05)
        self.render_image()

    def rotate_left(self):
        self.rotation = (self.rotation - 90) % 360
        self.fit_image()

    def rotate_right(self):
        self.rotation = (self.rotation + 90) % 360
        self.fit_image()

    def clean_filename(self, filename: str) -> str:
        filename = re.sub(r'[<>:"/\\|?*]', "", filename.strip())
        return filename or "ApprovedReceipt.jpg"

    def unique_destination(self, filename: str) -> Path:
        destination = self.approved_dir / filename
        counter = 2

        while destination.exists():
            destination = (
                self.approved_dir
                / f"{destination.stem}_{counter}{destination.suffix}"
            )
            counter += 1

        return destination

    def row_qualifies_for_auto_approval(self, row: dict[str, str]) -> bool:
        status = row.get("Approval Status", "").strip().upper()

        try:
            confidence = float(row.get("Overall Confidence", "0"))
        except ValueError:
            confidence = 0.0

        return (
            status in {"READY", "APPROVE"}
            and confidence >= self.auto_approve_threshold
            and bool(row.get("Vendor", "").strip())
            and bool(row.get("Date", "").strip())
            and bool(row.get("Total", "").strip())
        )

    def approve_row(self, row: dict[str, str]) -> tuple[bool, str]:
        vendor = row.get("Vendor", "").strip()
        if vendor:
            self.db.save_vendor_default(
                vendor_name=vendor,
                category=row.get("Category", ""),
                payment_method=row.get("Payment Method", ""),
                last_four=row.get("Last 4", ""),
            )

        source_text = row.get("Source Path", "").strip()
        if not source_text:
            return False, "Source Path is blank."

        source_path = self.job_root / source_text
        suggested_name = (
            row.get("Approved File Name", "").strip()
            or row.get("Suggested File Name", "").strip()
            or row.get("Original File", "").strip()
        )
        destination = self.unique_destination(
            self.clean_filename(suggested_name)
        )

        try:
            if not source_path.exists():
                return False, f"Could not find: {source_path}"

            shutil.move(str(source_path), str(destination))

            row["Approval Status"] = "COMPLETED"
            row["Approved File Name"] = destination.name
            row["Source Path"] = str(destination.relative_to(self.job_root))
            return True, ""

        except Exception as exc:
            return False, str(exc)

    def approve_current(self):
        if not self.filtered_indexes:
            return

        self.save_fields()
        self.backup_csv("before_manual_approval")
        row = self.current_row()
        success, error = self.approve_row(row)

        if not success:
            QMessageBox.critical(
                self,
                "Could not approve receipt",
                error,
            )
            return

        self.write_csv()
        self.export_final_csv(show_message=False)
        self.statusBar().showMessage("Receipt approved", 1500)
        self.remove_current_from_queue()


    def reject_current(self):
        if not self.filtered_indexes:
            return

        reasons = [
            "ATM receipt",
            "Duplicate",
            "Not a business receipt",
            "Unreadable / unusable",
            "Other",
        ]
        reason, accepted = QInputDialog.getItem(
            self,
            "Reject Receipt",
            "Why should this item be excluded from the final CSV?",
            reasons,
            0,
            False,
        )
        if not accepted:
            return

        if reason == "Other":
            reason, accepted = QInputDialog.getText(
                self,
                "Reject Receipt",
                "Enter the rejection reason:",
            )
            reason = reason.strip()
            if not accepted or not reason:
                return

        answer = QMessageBox.question(
            self,
            "Confirm Rejection",
            f"Reject this item as: {reason}?\n\n"
            "It will be excluded from the final CSV and moved to the Rejected folder.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self.save_fields()
        self.backup_csv("before_rejection")
        row = self.current_row()
        source_text = row.get("Source Path", "").strip()
        source_path = self.job_root / source_text if source_text else None

        try:
            if source_path and source_path.exists():
                destination = self.rejected_dir / source_path.name
                counter = 2
                while destination.exists():
                    destination = self.rejected_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
                    counter += 1
                shutil.move(str(source_path), str(destination))
                row["Source Path"] = str(destination.relative_to(self.job_root))

            row["Approval Status"] = "REJECTED"
            row["Rejection Reason"] = reason
            self.write_csv()
            self.export_final_csv(show_message=False)
            self.statusBar().showMessage(f"Receipt rejected: {reason}", 2500)
            self.remove_current_from_queue()
        except Exception as exc:
            QMessageBox.critical(self, "Could not reject receipt", str(exc))

    def export_final_csv(self, show_message: bool = True):
        if not self.rows:
            return

        self.save_fields()
        included = [
            row for row in self.rows
            if row.get("Approval Status", "").strip().upper() == "COMPLETED"
        ]
        export_path = self.job_root / "Exports" / "final_bookkeeping_export.csv"
        export_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "Date", "Vendor", "Subtotal", "Tax", "Tip", "Total",
            "Category", "Payment Method", "Last 4",
            "Transaction Type", "Approved File Name", "Original File",
        ]
        with NamedTemporaryFile(
            "w", delete=False, dir=export_path.parent, newline="",
            encoding="utf-8-sig", suffix=".tmp"
        ) as file:
            temp_path = Path(file.name)
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(included)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(export_path)

        if show_message:
            rejected = sum(
                row.get("Approval Status", "").strip().upper() == "REJECTED"
                for row in self.rows
            )
            QMessageBox.information(
                self,
                "Final CSV Created",
                f"Exported {len(included)} approved receipts.\n"
                f"Excluded {rejected} rejected items.\n\n"
                f"Saved to:\n{export_path}",
            )

    def mark_status(self, status: str):
        if not self.filtered_indexes:
            return

        self.save_fields()
        self.current_row()["Approval Status"] = status
        self.save()

        if status not in self.allowed_statuses():
            self.remove_current_from_queue()
        else:
            self.next()

    def remove_current_from_queue(self):
        if not self.filtered_indexes:
            return

        removed_global_index = self.current_global_index()
        self.filtered_indexes.remove(removed_global_index)

        if not self.filtered_indexes:
            self.image.clear()
            self.title.setText("Review queue complete.")
            self.progress.setMaximum(1)
            self.progress.setValue(1)
            self.statusBar().showMessage("Review queue complete")
            return

        self.position = min(self.position, len(self.filtered_indexes) - 1)
        self.show_row()

    def next(self):
        if not self.filtered_indexes:
            return

        self.save_fields()

        if self.position < len(self.filtered_indexes) - 1:
            self.position += 1
            self.show_row()

    def previous(self):
        if not self.filtered_indexes:
            return

        self.save_fields()

        if self.position > 0:
            self.position -= 1
            self.show_row()

    def auto_approve(self):
        if not self.rows:
            return

        self.save_fields()

        qualifying_rows = [
            row for row in self.rows
            if self.row_qualifies_for_auto_approval(row)
        ]
        skipped = len(self.rows) - len(qualifying_rows)

        if self.dry_run.isChecked():
            QMessageBox.information(
                self,
                "Dry Run Complete",
                f"{len(qualifying_rows)} receipts would be approved.\n"
                f"{skipped} receipts would remain for review.",
            )
            return

        if not qualifying_rows:
            QMessageBox.information(
                self,
                "Auto Approve",
                "No receipts meet the auto-approval rules.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Confirm Auto Approve",
            f"Approve and move {len(qualifying_rows)} receipts?\n\n"
            "This will mark them COMPLETED and move their files "
            "to the Approved folder.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self.backup_csv("before_auto_approve")
        approved = 0
        errors: list[str] = []

        for row in qualifying_rows:
            success, error = self.approve_row(row)
            if success:
                approved += 1
            else:
                original_file = row.get("Original File", "Unknown receipt")
                errors.append(f"{original_file}: {error}")

        self.write_csv()
        self.apply_filter()

        message = (
            f"Approved: {approved}\n"
            f"Skipped: {skipped}\n"
            f"Errors: {len(errors)}"
        )

        if errors:
            preview = "\n".join(errors[:5])
            if len(errors) > 5:
                preview += f"\n...and {len(errors) - 5} more."
            message += f"\n\nCould not approve:\n{preview}"

        QMessageBox.information(
            self,
            "Auto Approve Complete",
            message,
        )

    def closeEvent(self, event):
        if self.rows:
            self.save()
        save_window_geometry(self, "review_window")
        event.accept()
