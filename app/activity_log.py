"""Local activity log (simulated Azure Activity Log)."""

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "activity.json"


def _read_all(path=LOG_PATH):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def record(user_id, action, target, allowed, message, path=LOG_PATH):
    """Append one entry. Both allowed and denied attempts are recorded."""
    entries = _read_all(path)
    entries.append({
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user": user_id,
        "action": action,
        "target": target,
        "result": "Allowed" if allowed else "Denied",
        "message": message,
    })
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def list_recent(limit=20, path=LOG_PATH):
    """Return the most recent entries, newest first."""
    return list(reversed(_read_all(path)))[:limit]