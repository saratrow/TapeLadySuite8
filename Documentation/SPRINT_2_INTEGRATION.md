# Sprint 2 Integration

## Install

1. In GitHub Desktop, confirm the current branch is `dev`.
2. Close TLBS and the Receipt Manager.
3. Make a copy of the project folder as a backup.
4. Extract `TLBS_Sprint2_Pack_v0.2.zip`.
5. Open the extracted folder.
6. Copy all contents into the project root.
7. Choose **Replace the files in the destination** when Windows asks.
8. Double-click `RUN_TLBS.bat`.

## Test checklist

- TLBS opens and shows version `0.2.0-dev`.
- The database migration runs without deleting existing customers.
- `+ New Customer / Project` opens a four-step wizard.
- A new customer and project can be created.
- An existing customer can receive another project.
- A folder appears under `TLBS Projects`.
- The project appears under Recent Projects.
- Two activity entries appear for a new customer/project.
- Double-clicking a project opens its folder.
- Closing and reopening TLBS preserves the records.

## Commit

After the checklist passes, commit on `dev` with:

`Add customer project wizard and automatic project setup`

## Rollback

If Sprint 2 fails:

1. Close TLBS.
2. Restore the backup project folder.
3. Keep `data/TLBS_Main.db`; Sprint 2 migrations are additive.
4. Send the full error or screenshot.
