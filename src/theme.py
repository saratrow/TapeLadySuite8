from __future__ import annotations

WARM_CLASSIC_STYLESHEET = r'''
QWidget {
    background: #15130f;
    color: #eee7d8;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QMainWindow, QDialog { background: #15130f; }
QMenuBar { background: #11100d; color: #e8dcc4; padding: 4px; }
QMenuBar::item:selected, QMenu::item:selected { background: #3b3221; }
QMenu { background: #1c1914; border: 1px solid #5a4a2c; }
QFrame#headerCard {
    background: #000000;
    border: 1px solid #4c4029;
    border-radius: 12px;
}
QFrame#panelCard, QFrame#smartReviewDashboard {
    background: #201c16;
    border: 1px solid #4c4029;
    border-radius: 12px;
}
QFrame#sectionCard, QFrame#accentCard {
    background: #272116;
    border: 1px solid #765f34;
    border-radius: 12px;
}
QLabel#brandLogo { background: transparent; border: none; padding: 0px; }
QFrame#headerBadges { background: transparent; border: none; }
QLabel#statusBadge, QLabel#statusBadgeGreen, QLabel#statusBadgeGold, QLabel#statusBadgeTeal {
    background: #10100e;
    border: 1px solid #4b412f;
    border-radius: 9px;
    padding: 6px 10px;
    font-size: 9.5pt;
    font-weight: 650;
}
QLabel#statusBadge { color: #c9baa0; }
QLabel#statusBadgeGreen { color: #8bcf76; border-color: #48663f; }
QLabel#statusBadgeGold { color: #edc36b; border-color: #6f5730; }
QLabel#statusBadgeTeal { color: #72c4ad; border-color: #315e52; }
QLabel#emptyState {
    color: #b8ad98;
    background: #1a1712;
    border: 1px dashed #55472f;
    border-radius: 10px;
    padding: 28px;
    font-size: 11pt;
}
QLabel#brandTitle { color: #d8ad62; font-family: "Segoe Script"; font-size: 26pt; font-weight: 600; }
QLabel#brandEight { color: #4fae91; font-size: 28pt; font-weight: 700; }
QLabel#pageTitle { color: #f5eedf; font-size: 20pt; font-weight: 650; }
QLabel#sectionTitle { color: #e7c885; font-size: 11.5pt; font-weight: 650; padding-bottom: 2px; }
QLabel#mutedText { color: #aca28e; }
QLabel#statusGood { color: #83bd6b; font-weight: 700; }
QListWidget, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QScrollArea {
    background: #1b1813;
    border: 1px solid #4b412f;
    border-radius: 7px;
    padding: 6px;
    selection-background-color: #5d4a27;
    selection-color: #ffffff;
}
QListWidget::item { padding: 9px; border-radius: 5px; }
QListWidget::item:selected { background: #554525; color: #fff4d6; }
QPushButton {
    background: #2a251d;
    border: 1px solid #67563a;
    border-radius: 9px;
    min-height: 20px;
    padding: 9px 14px;
    color: #eee5d2;
    font-weight: 600;
}
QPushButton:hover { background: #403526; border-color: #c29b55; }
QPushButton:focus { border: 1px solid #d0a85e; }
QPushButton:pressed { background: #1c1914; padding-top: 10px; padding-bottom: 8px; }
QPushButton:disabled { color: #6f695d; border-color: #3b352a; }
QPushButton#primaryButton { background: #4c744b; border-color: #71976c; color: white; }
QPushButton#primaryButton:hover { background: #5a8657; }
QPushButton#accentButton { background: #b68a43; border-color: #d0a85e; color: #18130d; }
QPushButton#accentButton:hover { background: #c79b52; }
QPushButton#dangerButton { background: #7d2f2f; border-color: #b75a50; color: white; }
QPushButton#dangerButton:hover { background: #963b35; border-color: #d27468; }
QProgressBar {
    background: #26221b;
    border: 1px solid #4b412f;
    border-radius: 7px;
    min-height: 14px;
    text-align: center;
    color: #f5eedf;
}
QProgressBar::chunk { background: #668b55; border-radius: 6px; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QSplitter::handle { background: #2e281e; width: 3px; }
QFormLayout QLabel { color: #c8bda8; }
QStatusBar { background: #11100d; color: #a99f8c; border-top: 1px solid #332b20; }
QToolTip { background: #f3e7ca; color: #1b1710; border: 1px solid #a28146; }
QScrollBar:vertical { background: #17140f; width: 12px; }
QScrollBar::handle:vertical { background: #66583e; border-radius: 5px; min-height: 25px; }
QScrollBar:horizontal { background: #17140f; height: 12px; }
QScrollBar::handle:horizontal { background: #66583e; border-radius: 5px; min-width: 25px; }
'''


def apply_warm_classic(app):
    app.setStyleSheet(WARM_CLASSIC_STYLESHEET)
