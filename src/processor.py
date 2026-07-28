from __future__ import annotations

import base64, csv, hashlib, json, mimetypes, os, re, shutil, time, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from tempfile import NamedTemporaryFile
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
from openai import OpenAI

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}
CATEGORIES = [
    "Advertising & Marketing", "Automobile Expense", "Bank Charges & Fees",
    "Computer & Internet Expenses", "Contract Labor", "Dues & Subscriptions",
    "Equipment", "Insurance", "Meals", "Office Supplies",
    "Postage & Shipping", "Professional Fees", "Repairs & Maintenance",
    "Software & Subscriptions", "Supplies", "Telephone", "Travel",
    "Utilities", "Uncategorized Expense"
]
CSV_FIELDS = [
    "Original File", "Suggested File Name", "Date", "Date Confidence",
    "Vendor", "Vendor Confidence", "Subtotal", "Tax", "Tip", "Total",
    "Total Confidence", "Category", "Payment Method", "Last 4",
    "Math Check", "Date Check", "Possible Duplicate", "Overall Confidence",
    "Best Image Variant", "Verification Result", "Transaction Type",
    "Confidence Breakdown", "Review Reason",
    "Approval Status", "Approved File Name", "Source Path", "Image SHA256"
]

def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def normalize_money(value: Any) -> str:
    if value in (None, ""):
        return ""
    m = re.search(r"-?\d+(?:,\d{3})*(?:\.\d{1,2})?", str(value).replace("$", ""))
    if not m:
        return ""
    return f"{float(m.group().replace(',', '')):.2f}"

def normalize_date(value: str) -> str:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime((value or "").strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""

def normalize_vendor(value: str) -> str:
    """Clean merchant names without collapsing all word spacing."""
    value = re.sub(r"[^A-Za-z0-9 &'.-]", " ", value or "")
    value = re.sub(r"\s+", " ", value).strip(" .-")
    # Remove common OCR/legal suffix noise only when it appears at the end.
    value = re.sub(r"\s+(?:LLC|INC|CORP|LTD)\.?$", "", value, flags=re.I).strip()
    return value[:60]

def safe_vendor(value: str) -> str:
    value = normalize_vendor(value)
    value = re.sub(r"[^A-Za-z0-9&'-]", "", value)
    return value[:40] or "UnknownVendor"

def normalize_last_four(value: Any) -> str:
    """Return exactly four card digits, or blank. Never infer missing digits."""
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-4:] if len(digits) >= 4 else ""

def transaction_type(vendor: str, total: str, text_hints: str = "") -> str:
    combined = f"{vendor} {text_hints}".lower()
    if total.startswith("-") or any(word in combined for word in ("refund", "return", "credit issued")):
        return "REFUND"
    if any(word in combined for word in ("void", "voided")):
        return "VOID"
    return "PURCHASE"

def weighted_confidence(vc: float, dc: float, tc: float, ac: float, *,
                        math_result: str, date_result: str, duplicate: str,
                        vendor: str, date: str, total: str, verification: str,
                        txn_type: str) -> tuple[float, list[str]]:
    """Calculate a 0..1 bookkeeping confidence score with explainable adjustments."""
    components = [
        ("Vendor", max(0.0, min(1.0, vc)), 0.25),
        ("Date", max(0.0, min(1.0, dc)), 0.20),
        ("Total", max(0.0, min(1.0, tc)), 0.35),
        ("Independent verification", max(0.0, min(1.0, ac)), 0.20),
    ]
    score = sum(value * weight for _, value, weight in components)
    notes = [f"{label}: {value:.0%} × {weight:.0%}" for label, value, weight in components]

    if not vendor:
        score -= 0.25
        notes.append("Vendor missing: -25%")
    if not date:
        score -= 0.20
        notes.append("Date missing: -20%")
    if not total:
        score -= 0.35
        notes.append("Total missing: -35%")
    if math_result == "FAIL":
        score -= 0.15
        notes.append("Math validation failed: -15%")
    elif math_result == "PASS":
        score += 0.03
        notes.append("Math validation passed: +3%")
    if date_result != "PASS":
        score -= 0.10
        notes.append(f"Date check {date_result}: -10%")
    if duplicate == "YES":
        score -= 0.20
        notes.append("Possible duplicate: -20%")
    if verification == "FAIL":
        score -= 0.25
        notes.append("Independent verification failed: -25%")
    elif verification == "PASS":
        score += 0.03
        notes.append("Independent verification passed: +3%")
    if txn_type == "REFUND":
        notes.append("Refund recognized; negative totals are valid")

    return max(0.0, min(1.0, score)), notes

def expected_date_check(date_text: str, start: str, end: str) -> str:
    if not date_text:
        return "MISSING"
    try:
        d = datetime.strptime(date_text, "%Y-%m-%d").date()
        if start and d < datetime.strptime(start, "%Y-%m-%d").date():
            return "OUTSIDE RANGE"
        if end and d > datetime.strptime(end, "%Y-%m-%d").date():
            return "OUTSIDE RANGE"
        return "PASS"
    except ValueError:
        return "INVALID"

def math_check(subtotal: str, tax: str, tip: str, total: str, txn_type: str = "PURCHASE") -> str:
    if not subtotal or not total:
        return "NOT AVAILABLE"
    try:
        sub = float(subtotal)
        tx = float(tax or 0)
        gratuity = float(tip or 0)
        tot = float(total)
        # Refund receipts are printed inconsistently: line items may be positive while
        # the final credited amount is negative. Compare magnitudes as a fallback.
        expected = sub + tx + gratuity
        direct_match = abs(expected - tot) <= 0.03
        refund_match = txn_type == "REFUND" and abs(abs(expected) - abs(tot)) <= 0.03
        return "PASS" if direct_match or refund_match else "FAIL"
    except ValueError:
        return "NOT AVAILABLE"

def enhance_variants(path: Path) -> dict[str, np.ndarray]:
    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError("Could not open image")
    h, w = image.shape[:2]
    # 1800px is ample for receipt text while cutting upload size and preprocessing time.
    scale = min(1.0, 1800 / max(h, w))
    if scale < 1:
        image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    gray = cv2.normalize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), None, 0, 255, cv2.NORM_MINMAX)
    clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(12, 12)).apply(gray)
    background = cv2.medianBlur(cv2.dilate(gray, np.ones((7, 7), np.uint8)), 41)
    shadow = cv2.normalize(255 - cv2.absdiff(gray, background), None, 0, 255, cv2.NORM_MINMAX)
    shadow_clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(12, 12)).apply(shadow)
    blur = cv2.GaussianBlur(clahe, (0, 0), 2.0)
    sharpened = cv2.addWeighted(clahe, 2.6, blur, -1.6, 0)
    bw = cv2.adaptiveThreshold(
        cv2.bilateralFilter(shadow_clahe, 9, 45, 45),
        255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 11
    )
    return {"original": image, "clahe": clahe, "shadow_clahe": shadow_clahe,
            "sharpened": sharpened, "adaptive_bw": bw}

def score_variant(arr: np.ndarray) -> float:
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY) if arr.ndim == 3 else arr
    edges = cv2.Canny(gray, 60, 160)
    return float(np.mean(edges > 0)) * 1.8 + float(np.std(gray) / 128.0) * 0.8

def save_best_variant(job_root: Path, source: Path) -> tuple[str, Path]:
    """Score variants in memory and save only the winner.

    Older builds wrote five large JPEGs per receipt. That added substantial disk I/O
    without improving extraction because only one variant is sent to the model.
    """
    variants = enhance_variants(source)
    best = max(variants, key=lambda name: score_variant(variants[name]))
    folder = job_root / "Enhanced" / source.stem
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{source.stem}_{best}.jpg"
    cv2.imwrite(str(out), variants[best], [cv2.IMWRITE_JPEG_QUALITY, 88])
    return best, out

def image_data(path: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return mime, base64.b64encode(path.read_bytes()).decode("ascii")

def extract(client: OpenAI, model: str, image_path: Path) -> dict[str, Any]:
    mime, encoded = image_data(image_path)
    schema = {
        "type": "object",
        "properties": {
            "vendor": {"type": "string"},
            "vendor_confidence": {"type": "number"},
            "date": {"type": "string"},
            "date_confidence": {"type": "number"},
            "subtotal": {"type": "string"},
            "tax": {"type": "string"},
            "tip": {"type": "string"},
            "total": {"type": "string"},
            "total_confidence": {"type": "number"},
            "category": {"type": "string", "enum": CATEGORIES},
            "payment_method": {"type": "string"},
            "last_four": {"type": "string"},
            "review_reason": {"type": "string"}
        },
        "required": ["vendor","vendor_confidence","date","date_confidence","subtotal",
                     "tax","tip","total","total_confidence","category","payment_method",
                     "last_four","review_reason"],
        "additionalProperties": False
    }
    response = client.responses.create(
        model=model,
        instructions=(
            "Extract receipt bookkeeping data conservatively. Never guess. "
            "Use YYYY-MM-DD. Total is the final amount paid, not subtotal, tax, "
            "cash tendered, change due, cash back, savings, or balance. Extract an actual "
            "gratuity entered or charged as Tip; ignore suggested tip percentages or amounts. "
            "For refunds, return the credited amount as a negative total. Extract Last 4 "
            "only when four card digits are visibly printed; otherwise return blank."
        ),
        input=[{"role":"user","content":[
            {"type":"input_text","text":"Extract the bookkeeping fields."},
            {"type":"input_image","image_url":f"data:{mime};base64,{encoded}","detail":"high"}
        ]}],
        text={"format":{"type":"json_schema","name":"receipt_extract","schema":schema,"strict":True}}
    )
    return json.loads(response.output_text)

def verify(client: OpenAI, model: str, image_path: Path, proposed: dict) -> dict:
    mime, encoded = image_data(image_path)
    schema = {
        "type": "object",
        "properties": {
            "result": {"type":"string","enum":["PASS","REVIEW","FAIL"]},
            "corrected_vendor":{"type":"string"},
            "corrected_date":{"type":"string"},
            "corrected_subtotal":{"type":"string"},
            "corrected_tax":{"type":"string"},
            "corrected_tip":{"type":"string"},
            "corrected_total":{"type":"string"},
            "confidence":{"type":"number"},
            "reason":{"type":"string"}
        },
        "required":["result","corrected_vendor","corrected_date","corrected_subtotal",
                    "corrected_tax","corrected_tip","corrected_total","confidence","reason"],
        "additionalProperties":False
    }
    response = client.responses.create(
        model=model,
        instructions=(
            "Independently audit the extraction against the receipt. "
            "Pay special attention to faded dates and subtotal-versus-total errors. "
            "Never guess."
        ),
        input=[{"role":"user","content":[
            {"type":"input_text","text":"Audit:\n"+json.dumps(proposed, indent=2)},
            {"type":"input_image","image_url":f"data:{mime};base64,{encoded}","detail":"high"}
        ]}],
        text={"format":{"type":"json_schema","name":"receipt_verify","schema":schema,"strict":True}}
    )
    return json.loads(response.output_text)

def load_rows(csv_path: Path) -> list[dict[str,str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def backup_file(path: Path, label: str = "backup") -> Path | None:
    if not path.exists():
        return None
    folder = path.parent / "Backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = folder / f"{path.stem}_{label}_{stamp}{path.suffix}"
    shutil.copy2(path, destination)
    return destination

def write_rows(csv_path: Path, rows: list[dict[str,str]], retries: int = 8):
    """Atomically save the review CSV, tolerating brief OneDrive/Excel file locks.

    Windows cloud-sync clients and spreadsheet programs can momentarily lock the
    destination during replacement.  Retrying prevents a harmless transient lock
    from aborting an otherwise successful receipt batch.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(max(1, retries)):
        temp_path = None
        try:
            with NamedTemporaryFile("w", delete=False, dir=csv_path.parent, newline="", encoding="utf-8-sig", suffix=".tmp") as f:
                temp_path = Path(f.name)
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
                f.flush()
                os.fsync(f.fileno())
            temp_path.replace(csv_path)
            return
        except (PermissionError, OSError) as exc:
            last_error = exc
            if temp_path and temp_path.exists():
                try: temp_path.unlink()
                except OSError: pass
            if attempt + 1 < retries:
                time.sleep(0.35 * (attempt + 1))
    raise last_error or OSError(f"Could not save {csv_path}")

def unique_path(folder: Path, name: str) -> Path:
    destination = folder / name
    counter = 2
    while destination.exists():
        source = Path(name)
        destination = folder / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    return destination

def _analyze_receipt(job_root: Path, path: Path, api_key: str, model: str,
                     expected_start: str, expected_end: str) -> dict[str, Any]:
    """Perform the expensive image and AI work for one receipt.

    This function does not update the CSV or move the incoming file, which lets it run
    safely in a worker thread. Final bookkeeping changes are committed by process_job.
    """
    originals = job_root / "Originals"
    backup = originals / path.name
    if not backup.exists():
        shutil.copy2(path, backup)

    best_name, best_path = save_best_variant(job_root, path)
    client = OpenAI(api_key=api_key)
    data = extract(client, model, best_path)
    audit = verify(client, model, best_path, data)

    vendor = normalize_vendor(audit.get("corrected_vendor") or data.get("vendor", ""))
    date = normalize_date(audit.get("corrected_date") or data.get("date", ""))
    subtotal = normalize_money(audit.get("corrected_subtotal") or data.get("subtotal", ""))
    tax = normalize_money(audit.get("corrected_tax") or data.get("tax", ""))
    tip = normalize_money(audit.get("corrected_tip") or data.get("tip", ""))
    total = normalize_money(audit.get("corrected_total") or data.get("total", ""))
    last_four = normalize_last_four(data.get("last_four", ""))
    vc = float(data.get("vendor_confidence", 0))
    dc = float(data.get("date_confidence", 0))
    tc = float(data.get("total_confidence", 0))
    ac = float(audit.get("confidence", 0))
    verification = audit.get("result", "REVIEW")
    txn_type = transaction_type(vendor, total, f"{data.get('review_reason', '')} {audit.get('reason', '')}")
    return {
        "path": path, "digest": file_hash(path), "best_name": best_name,
        "data": data, "audit": audit, "vendor": vendor, "date": date,
        "subtotal": subtotal, "tax": tax, "tip": tip, "total": total, "last_four": last_four,
        "vc": vc, "dc": dc, "tc": tc, "ac": ac, "verification": verification,
        "txn_type": txn_type, "mcheck": math_check(subtotal, tax, tip, total, txn_type),
        "dcheck": expected_date_check(date, expected_start, expected_end),
    }


def _write_process_log(job_root: Path, message: str) -> None:
    """Append a timestamped processing event without allowing logging to stop a batch."""
    try:
        logs = job_root / "Logs"
        logs.mkdir(parents=True, exist_ok=True)
        log_path = logs / "process.log"
        # Keep the log useful without allowing it to grow forever.
        if log_path.exists() and log_path.stat().st_size > 2_000_000:
            archived = logs / "process_previous.log"
            if archived.exists():
                archived.unlink()
            log_path.replace(archived)
        with log_path.open("a", encoding="utf-8") as log:
            stamp = datetime.now().isoformat(timespec="seconds")
            log.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def test_openai_connection(api_key: str, model: str) -> None:
    """Fail fast before touching receipt files when API credentials/model are unusable."""
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input="Reply with OK only.",
        max_output_tokens=32,
    )
    if not (getattr(response, "output_text", "") or "").strip():
        raise RuntimeError("OpenAI connection test returned no response")


def process_job(job_root: Path, api_key: str, model: str, min_ready: float,
                expected_start: str, expected_end: str,
                progress: Callable[[int,int,str], None], workers: int = 3) -> dict:
    incoming = job_root / "Incoming"
    originals = job_root / "Originals"
    awaiting = job_root / "Awaiting_Approval"
    problems = job_root / "Problem_Receipts"
    exports = job_root / "Exports"
    for folder in [incoming, originals, awaiting, problems, exports]:
        folder.mkdir(parents=True, exist_ok=True)

    _write_process_log(job_root, f"Running OpenAI preflight with model={model}")
    test_openai_connection(api_key, model)
    _write_process_log(job_root, "OpenAI preflight passed")

    files = sorted((p for p in incoming.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED), key=lambda p: p.name.lower())
    _write_process_log(job_root, f"Batch started: {len(files)} incoming file(s), requested workers={workers}")
    csv_path = exports / "receipt_review_accuracy.csv"
    rows = load_rows(csv_path)
    if files and csv_path.exists():
        backup_file(csv_path, "before_processing")
    hashes = {r.get("Image SHA256", "") for r in rows}
    triples = {(r.get("Date", ""), r.get("Vendor", "").lower(), r.get("Total", ""))
               for r in rows if r.get("Date") and r.get("Vendor") and r.get("Total")}

    # Remove exact duplicates before launching expensive API work.
    candidates: list[Path] = []
    skipped = 0
    for path in files:
        digest = file_hash(path)
        if digest in hashes:
            skipped += 1
        else:
            candidates.append(path)

    processed = failed = completed = 0
    checkpoint_warnings = 0
    first_error = ""
    workers = max(1, min(int(workers or 1), 6, len(candidates) or 1))
    progress(0, len(candidates), f"Starting {workers} processing worker{'s' if workers != 1 else ''}...")

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="receipt") as pool:
        futures = {
            pool.submit(_analyze_receipt, job_root, path, api_key, model, expected_start, expected_end): path
            for path in candidates
        }
        for future in as_completed(futures):
            path = futures[future]
            completed += 1
            try:
                result = future.result()
                vendor, date, total = result["vendor"], result["date"], result["total"]
                triple = (date, vendor.lower().strip(), total)
                duplicate = "YES" if triple in triples and all(triple) else "NO"
                overall, confidence_notes = weighted_confidence(
                    result["vc"], result["dc"], result["tc"], result["ac"],
                    math_result=result["mcheck"], date_result=result["dcheck"],
                    duplicate=duplicate, vendor=vendor, date=date, total=total,
                    verification=result["verification"], txn_type=result["txn_type"],
                )
                status = "REVIEW"
                if (result["verification"] == "PASS" and overall >= min_ready and vendor and date and total
                        and result["mcheck"] != "FAIL" and result["dcheck"] == "PASS" and duplicate == "NO"):
                    status = "READY"
                if result["verification"] == "FAIL" or not (vendor or date or total):
                    status = "PROBLEM"

                reasons = []
                if status == "READY":
                    reasons.append("All required fields passed validation and confidence meets the configured Auto Approve threshold")
                elif status == "REVIEW":
                    if overall < min_ready:
                        reasons.append(f"Overall confidence is {overall:.0%}, below the configured Auto Approve threshold")
                    if result["verification"] == "REVIEW":
                        reasons.append("Independent verification requested manual review")
                else:
                    reasons.append("The receipt could not be processed reliably")
                if not vendor: reasons.append("Vendor missing")
                if not date: reasons.append("Date missing")
                if not total: reasons.append("Total missing")
                if result["mcheck"] == "FAIL": reasons.append("Subtotal plus tax and tip do not match total")
                if result["dcheck"] != "PASS": reasons.append(f"Date check: {result['dcheck']}")
                if duplicate == "YES": reasons.append("Possible duplicate")

                destination_dir = problems if status == "PROBLEM" else awaiting
                destination = unique_path(destination_dir, path.name)
                shutil.move(str(path), str(destination))
                suggested = f"{date or 'UnknownDate'}_{safe_vendor(vendor)}_{('$'+total) if total else 'UnknownAmount'}{path.suffix.lower()}"
                data = result["data"]
                rows.append({
                    "Original File": path.name, "Suggested File Name": suggested,
                    "Date": date, "Date Confidence": f"{result['dc']:.2f}",
                    "Vendor": vendor, "Vendor Confidence": f"{result['vc']:.2f}",
                    "Subtotal": result["subtotal"], "Tax": result["tax"], "Tip": result["tip"], "Total": total,
                    "Total Confidence": f"{result['tc']:.2f}",
                    "Category": data.get("category", "Uncategorized Expense"),
                    "Payment Method": data.get("payment_method", ""), "Last 4": result["last_four"],
                    "Math Check": result["mcheck"], "Date Check": result["dcheck"],
                    "Possible Duplicate": duplicate, "Overall Confidence": f"{overall:.2f}",
                    "Best Image Variant": result["best_name"], "Verification Result": result["verification"],
                    "Transaction Type": result["txn_type"], "Confidence Breakdown": " | ".join(confidence_notes),
                    "Review Reason": "; ".join(dict.fromkeys(x for x in reasons if x)),
                    "Approval Status": status, "Approved File Name": "",
                    "Source Path": str(destination.relative_to(job_root)), "Image SHA256": result["digest"]
                })
                hashes.add(result["digest"])
                if all(triple): triples.add(triple)
                processed += 1
                _write_process_log(job_root, f"Processed {path.name}: status={status}, confidence={overall:.0%}")
            except Exception as exc:
                failed += 1
                if not first_error:
                    first_error = f"{type(exc).__name__}: {exc}"
                _write_process_log(job_root, f"Receipt failed: {path.name}: {type(exc).__name__}: {exc}")
                # Keep the original in Incoming so the user can retry after fixing the issue.
                destination = unique_path(problems, path.name)
                if path.exists():
                    shutil.copy2(str(path), str(destination))
                logs = job_root / "Logs"; logs.mkdir(parents=True, exist_ok=True)
                with (logs / "processing_errors.log").open("a", encoding="utf-8") as log:
                    log.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] {path.name}: {exc}\n")
                    log.write(traceback.format_exc())
                rows.append({
                    "Original File": path.name, "Suggested File Name": "", "Date": "", "Date Confidence": "0.00",
                    "Vendor": "", "Vendor Confidence": "0.00", "Subtotal": "", "Tax": "", "Tip": "", "Total": "",
                    "Total Confidence": "0.00", "Category": "Uncategorized Expense", "Payment Method": "", "Last 4": "",
                    "Math Check": "NOT AVAILABLE", "Date Check": "MISSING", "Possible Duplicate": "NO",
                    "Overall Confidence": "0.00", "Best Image Variant": "", "Verification Result": "FAIL",
                    "Transaction Type": "UNKNOWN", "Confidence Breakdown": "", "Review Reason": f"Processing error: {exc}",
                    "Approval Status": "PROBLEM", "Approved File Name": "",
                    "Source Path": str(destination.relative_to(job_root)), "Image SHA256": ""
                })
            # Checkpoint after every completion so an interruption loses at most one receipt.
            # A brief OneDrive/Excel lock should never kill the entire batch.
            try:
                write_rows(csv_path, rows)
            except (PermissionError, OSError) as exc:
                checkpoint_warnings += 1
                _write_process_log(job_root, f"CSV checkpoint warning: {type(exc).__name__}: {exc}")
                logs = job_root / "Logs"; logs.mkdir(parents=True, exist_ok=True)
                with (logs / "processing_errors.log").open("a", encoding="utf-8") as log:
                    log.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] CSV checkpoint warning: {exc}\n")
            progress(completed, len(candidates), f"Completed {completed}/{len(candidates)} — {path.name}")

    # Make one final durable save. If the normal CSV remains locked, preserve all
    # results in a clearly named recovery file instead of reporting a total failure.
    recovery_csv = ""
    try:
        write_rows(csv_path, rows, retries=12)
    except (PermissionError, OSError):
        recovery_path = exports / "receipt_review_accuracy_RECOVERY.csv"
        write_rows(recovery_path, rows, retries=3)
        recovery_csv = str(recovery_path)

    _write_process_log(
        job_root,
        f"Batch finished: processed={processed}, skipped={skipped}, failed={failed}, "
        f"checkpoint_warnings={checkpoint_warnings}, recovery_csv={bool(recovery_csv)}",
    )
    return {"processed": processed, "skipped": skipped, "failed": failed,
            "workers": workers, "csv": str(csv_path),
            "checkpoint_warnings": checkpoint_warnings, "recovery_csv": recovery_csv,
            "first_error": first_error, "log_path": str(job_root / "Logs" / "processing_errors.log")}
