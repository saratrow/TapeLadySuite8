# TLBS Architecture

Customer → Project → Assets → Processing → Deliverables

Rules:
- The current Receipt Manager remains operational during migration.
- Existing customer data and receipt files must never be overwritten.
- New TLBS data is stored in `data/TLBS_Main.db`.
- Legacy Receipt Manager data remains in `data/tapelady_receipts.db`.
- TLBS stores only reference links to Receipt Manager jobs, never duplicated customer or receipt data.
- Modules depend on shared Core services, not on each other.
- Every meaningful action can create an Activity record.
- UI code does not issue raw SQL.
- No hardcoded customer-data paths.
