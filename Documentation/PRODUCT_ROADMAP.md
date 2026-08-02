# TLBS Product Roadmap

## Milestone 1 — Foundation
- Product identity and versioning
- Shared SQLite database
- Customer and project models
- Activity timeline
- Module registry
- Working dashboard shell

## Milestone 2 — Receipt Manager Migration
- Launch existing Receipt Manager from TLBS
- Link receipt jobs to TLBS customers/projects using a reference-only mapping table
- Preserve existing OCR and review behavior
- Add accountant export package

## Milestone 2.5 — Sprint 3 Bridge
- Add a `ReceiptProjectBridgeService` in TLBS
- Launch Receipt Manager with selected customer and project context
- Create Receipt Manager job folders inside the TLBS project folder
- Record receipt-bridge lifecycle events in the TLBS activity timeline
- Expose dashboard metrics for active/waiting/completed receipt jobs

## Milestone 3 — Relationship Manager
- Business-card image import
- OCR and contact extraction
- Tags, meeting notes, follow-up tasks
- Google Contacts/CSV export

## Milestone 4 — Media Capture Bridge
- Keep TLCS separate initially
- Launch it from TLBS with customer/project context
- Later share data and UI libraries

## Milestone 5 — Document Center and Client Vault
- General document OCR and search
- Secure delivery and archive workflows
