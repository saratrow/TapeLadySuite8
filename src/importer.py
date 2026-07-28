from __future__ import annotations

import csv
import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".pdf"}
MANIFEST_FIELDS = [
    "Imported File",
    "Original Path",
    "Relative Folder",
    "Import Mode",
    "Imported At",
    "SHA256",
]


@dataclass(frozen=True)
class ImportResult:
    discovered: int
    imported: int
    skipped_duplicates: int
    failed: int
    manifest_path: Path


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_component(value: str) -> str:
    forbidden = '<>:"/\\|?*'
    cleaned = "".join(ch for ch in value if ch not in forbidden).strip().rstrip(".")
    return cleaned or "Receipt"


def unique_destination(folder: Path, preferred_name: str) -> Path:
    preferred = Path(preferred_name)
    stem = safe_component(preferred.stem)
    suffix = preferred.suffix.lower()
    candidate = folder / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def load_manifest(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def discover_files(source_folder: Path, recursive: bool) -> list[Path]:
    iterator = source_folder.rglob("*") if recursive else source_folder.iterdir()
    return sorted(
        (
            path
            for path in iterator
            if path.is_file() and path.suffix.lower() in SUPPORTED
        ),
        key=lambda path: str(path).lower(),
    )


def import_receipt_folder(
    job_root: Path,
    source_folder: Path,
    mode: str,
    progress=None,
) -> ImportResult:
    """Copy receipts into Incoming while leaving all source files untouched.

    mode must be ``organized`` (recursive) or ``unsorted`` (top-level only).
    A manifest records the original location of every imported file.
    """
    if mode not in {"organized", "unsorted"}:
        raise ValueError("Import mode must be 'organized' or 'unsorted'.")
    if not source_folder.is_dir():
        raise FileNotFoundError(f"Source folder does not exist: {source_folder}")

    incoming = job_root / "Incoming"
    exports = job_root / "Exports"
    incoming.mkdir(parents=True, exist_ok=True)
    exports.mkdir(parents=True, exist_ok=True)

    manifest_path = exports / "import_manifest.csv"
    rows = load_manifest(manifest_path)
    known_hashes = {row.get("SHA256", "") for row in rows if row.get("SHA256")}
    files = discover_files(source_folder, recursive=(mode == "organized"))

    imported = skipped = failed = 0
    timestamp = datetime.now().isoformat(timespec="seconds")

    for index, source in enumerate(files, start=1):
        if progress:
            progress(index - 1, len(files), f"Importing {source.name}")
        try:
            digest = file_hash(source)
            if digest in known_hashes:
                skipped += 1
                continue

            relative_parent = source.parent.relative_to(source_folder)
            # Prefix organized imports with their folder name so identical scan names
            # from different months remain recognizable after flattening into Incoming.
            if mode == "organized" and relative_parent != Path("."):
                prefix = safe_component("__".join(relative_parent.parts))
                preferred_name = f"{prefix}__{source.name}"
            else:
                preferred_name = source.name

            destination = unique_destination(incoming, preferred_name)
            shutil.copy2(source, destination)
            rows.append(
                {
                    "Imported File": destination.name,
                    "Original Path": str(source.resolve()),
                    "Relative Folder": "" if relative_parent == Path(".") else str(relative_parent),
                    "Import Mode": mode,
                    "Imported At": timestamp,
                    "SHA256": digest,
                }
            )
            known_hashes.add(digest)
            imported += 1
        except Exception:
            failed += 1
        finally:
            if progress:
                progress(index, len(files), f"Finished {source.name}")

    write_manifest(manifest_path, rows)
    return ImportResult(
        discovered=len(files),
        imported=imported,
        skipped_duplicates=skipped,
        failed=failed,
        manifest_path=manifest_path,
    )
