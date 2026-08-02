from __future__ import annotations
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from .core.database import Database
from .ui.dashboard import DashboardWindow
from .version import APP_NAME

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("TapeLadyDigitalTransfers")
    try:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        database = Database(data_dir / "TLBS_Main.db")
        database.initialize()
        window = DashboardWindow(database)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, f"{APP_NAME} startup error", f"{type(exc).__name__}: {exc}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
