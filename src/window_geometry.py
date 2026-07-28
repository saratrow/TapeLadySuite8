from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMainWindow

ORG_NAME = "TapeLadyDigitalTransfers"
APP_SETTINGS_NAME = "TapeLadySuite8"


def _settings() -> QSettings:
    return QSettings(ORG_NAME, APP_SETTINGS_NAME)


def _available_screens():
    return [screen.availableGeometry() for screen in QGuiApplication.screens()]


def _geometry_is_safe(window: QMainWindow) -> bool:
    frame = window.frameGeometry()
    if frame.width() <= 0 or frame.height() <= 0:
        return False

    frame_area = frame.width() * frame.height()
    best_visible_area = 0
    title_bar_safe = False

    for available in _available_screens():
        intersection = frame.intersected(available)
        best_visible_area = max(
            best_visible_area,
            max(0, intersection.width()) * max(0, intersection.height()),
        )

        # Keep a generous strip of the title bar visible so the window can
        # always be grabbed and moved by the user.
        title_bar = frame.adjusted(0, 0, 0, -(max(frame.height() - 48, 0)))
        if title_bar.intersects(available):
            title_bar_safe = True

    return title_bar_safe and best_visible_area >= frame_area * 0.80


def center_window(window: QMainWindow, width_ratio: float = 0.85, height_ratio: float = 0.85) -> None:
    screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        return

    available = screen.availableGeometry()
    width = max(window.minimumWidth(), int(available.width() * width_ratio))
    height = max(window.minimumHeight(), int(available.height() * height_ratio))
    width = min(width, available.width())
    height = min(height, available.height())

    x = available.x() + (available.width() - width) // 2
    y = available.y() + (available.height() - height) // 2
    window.setGeometry(x, y, width, height)


def restore_or_center(window: QMainWindow, settings_key: str) -> None:
    settings = _settings()
    reset_requested = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
    restored = False

    if not reset_requested:
        geometry = settings.value(f"windows/{settings_key}/geometry")
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            restored = window.restoreGeometry(geometry)

    if not restored or not _geometry_is_safe(window):
        center_window(window)


def save_window_geometry(window: QMainWindow, settings_key: str) -> None:
    # Do not save minimized geometry; preserve the last useful position.
    if window.isMinimized():
        return
    _settings().setValue(f"windows/{settings_key}/geometry", window.saveGeometry())
