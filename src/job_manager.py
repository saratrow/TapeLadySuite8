from pathlib import Path

JOB_FOLDERS = [
    "Originals", "Incoming", "Enhanced", "Awaiting_Approval",
    "Approved", "Rejected", "Problem_Receipts", "Exports", "Logs"
]

def safe_name(value: str) -> str:
    forbidden = '<>:"/\\|?*'
    cleaned = "".join(ch for ch in value.strip() if ch not in forbidden)
    return cleaned.strip().rstrip(".") or "Untitled"

def create_job_structure(base_dir: Path, client_name: str, job_name: str) -> Path:
    job_dir = base_dir / safe_name(client_name) / safe_name(job_name)
    for folder in JOB_FOLDERS:
        (job_dir / folder).mkdir(parents=True, exist_ok=True)
    return job_dir
