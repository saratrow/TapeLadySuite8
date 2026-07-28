from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) != 4:
        return 2
    db_path = Path(sys.argv[1])
    old_root = str(Path(sys.argv[2]).resolve())
    new_root = str(Path(sys.argv[3]).resolve())
    if not db_path.exists():
        return 0
    old_clients = str(Path(old_root) / "clients")
    new_clients = str(Path(new_root) / "clients")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT id, root_path FROM jobs").fetchall()
        for job_id, root_path in rows:
            if not root_path:
                continue
            updated = root_path
            for old_prefix, new_prefix in ((old_clients, new_clients), (old_root, new_root)):
                if updated.lower().startswith(old_prefix.lower()):
                    updated = new_prefix + updated[len(old_prefix):]
                    break
            if updated != root_path:
                conn.execute("UPDATE jobs SET root_path=? WHERE id=?", (updated, job_id))
        conn.commit()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
