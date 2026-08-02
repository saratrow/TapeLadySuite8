# Changelog

## 0.3.0-dev — Sprint 3

- Added a Receipt Project Bridge service for reference-only Receipt Manager linkage.
- Added a TLBS mapping table for Receipt Manager jobs without changing the legacy database schema.
- Added automatic creation of Receipt Manager working folders inside the TLBS project folder.
- Added dashboard metrics for Active Receipt Jobs, Waiting Review, and Completed Jobs.
- Added TLBS activity timeline entries for Receipt Manager bridge events.
- Added a safe dashboard launch path for the existing Receipt Manager with selected TLBS customer/project context.
- Preserved separation between `TLBS_Main.db` and `tapelady_receipts.db`.

## 0.2.0-dev — Sprint 2

- Added Customer and Project Wizard.
- Added existing-customer project creation.
- Added safe SQLite schema migrations.
- Added automatic project-folder creation.
- Added project-specific subfolders.
- Added customer and project activity entries.
- Added Recent Projects dashboard.
- Added project-folder opening from the dashboard.
- Added `RUN_TLBS.bat`.
