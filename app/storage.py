"""Persistence layer. The only module that talks to the SQLite database.

Swapping to a hosted database later means changing this file only.
"""

from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "azure_adminlab.db"
SEED_PATH = BASE_DIR / "data" / "tenant.json"


def get_connection(db_path=DB_PATH):
    """Establish connection to SQLite database and configure foreign keys."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn):
    """Create the core database tables if they do not exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vms (
            name TEXT PRIMARY KEY,
            subscription TEXT NOT NULL,
            resource_group TEXT NOT NULL,
            size TEXT NOT NULL,
            power_state TEXT NOT NULL,
            hourly_rate REAL NOT NULL,
            tags_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT NOT NULL,
            result TEXT NOT NULL,
            message TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS storage_accounts (
            name TEXT PRIMARY KEY,
            resource_group TEXT NOT NULL,
            public_access INTEGER NOT NULL DEFAULT 0,
            https_only INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS containers (
            name TEXT NOT NULL,
            account_name TEXT NOT NULL,
            PRIMARY KEY (account_name, name),
            FOREIGN KEY (account_name) REFERENCES storage_accounts(name) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS blobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            container_name TEXT NOT NULL,
            file_name TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            tier TEXT NOT NULL DEFAULT 'Hot',
            stored_path TEXT NOT NULL,
            FOREIGN KEY (account_name, container_name) REFERENCES containers(account_name, name) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS vnets (
            name TEXT PRIMARY KEY,
            resource_group TEXT NOT NULL,
            address_space TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subnets (
            name TEXT NOT NULL,
            vnet_name TEXT NOT NULL,
            address_prefix TEXT NOT NULL,
            nsg_name TEXT,
            PRIMARY KEY (vnet_name, name),
            FOREIGN KEY (vnet_name) REFERENCES vnets(name) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS nsg_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nsg_name TEXT NOT NULL,
            priority INTEGER NOT NULL,
            direction TEXT NOT NULL,
            protocol TEXT NOT NULL,
            port TEXT NOT NULL,
            access TEXT NOT NULL,
            UNIQUE (nsg_name, priority, direction)
        );
        CREATE TABLE IF NOT EXISTS vm_alerts (
            vm_name TEXT PRIMARY KEY,
            cpu_threshold INTEGER NOT NULL DEFAULT 80
        );
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            vm_name TEXT NOT NULL,
            cpu_percent INTEGER NOT NULL,
            threshold INTEGER NOT NULL,
            severity TEXT NOT NULL
        );
        """
    )
    conn.commit()


def load_seed_vms(path=SEED_PATH):
    """Load baseline VM objects directly from tenant.json."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["vms"]


def seed_database(conn, path=SEED_PATH):
    """Replace all VM and activity rows with sample data from tenant.json."""
    with open(path, encoding="utf-8") as f:
        seed = json.load(f)

    conn.execute("DELETE FROM vms")
    conn.execute("DELETE FROM activity")

    for vm in seed["vms"]:
        conn.execute(
            "INSERT INTO vms (name, subscription, resource_group, size, power_state, hourly_rate, tags_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                vm["name"],
                vm["subscription"],
                vm["resourceGroup"],
                vm["size"],
                vm["powerState"],
                vm["hourlyRate"],
                json.dumps(vm["tags"]),
            ),
        )
    conn.commit()


def initialize_database(db_path=DB_PATH):
    """Create the schema and seed sample data if the database is empty."""
    conn = get_connection(db_path)
    try:
        create_schema(conn)
        count = conn.execute("SELECT COUNT(*) FROM vms").fetchone()[0]
        if count == 0:
            seed_database(conn)
    finally:
        conn.close()


def create_storage_account(conn, name, resource_group, public_access=False, https_only=True):
    """Create a simulated storage account. Names must be 3-24 lowercase letters or digits."""
    if not (3 <= len(name) <= 24 and name.isalnum() and name == name.lower()):
        raise ValueError("Storage account name must be 3-24 lowercase letters or digits")
    conn.execute(
        "INSERT INTO storage_accounts (name, resource_group, public_access, https_only) VALUES (?, ?, ?, ?)",
        (name, resource_group, int(public_access), int(https_only)),
    )
    conn.commit()


def create_container(conn, account_name, container_name):
    """Create a container inside an existing storage account."""
    if not (
        3 <= len(container_name) <= 63
        and container_name.replace("-", "").isalnum()
        and container_name == container_name.lower()
    ):
        raise ValueError("Container name must be 3-63 lowercase letters, digits, or hyphens")
    exists = conn.execute("SELECT 1 FROM storage_accounts WHERE name = ?", (account_name,)).fetchone()
    if exists is None:
        raise ValueError(f"Storage account '{account_name}' does not exist")
    conn.execute(
        "INSERT INTO containers (name, account_name) VALUES (?, ?)",
        (container_name, account_name),
    )
    conn.commit()


def list_storage_accounts(conn):
    """Return all storage accounts with their container counts."""
    rows = conn.execute(
        """
        SELECT s.name, s.resource_group, s.public_access, s.https_only,
               (SELECT COUNT(*) FROM containers c WHERE c.account_name = s.name) AS container_count
        FROM storage_accounts s ORDER BY s.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


UPLOAD_DIR = BASE_DIR / "data" / "uploads"
MAX_UPLOAD_BYTES = 1024 * 1024  # 1 MB limit for simulated uploads
ALLOWED_EXTENSIONS = {".txt", ".csv", ".json", ".log"}
VALID_TIERS = {"Hot", "Cool", "Archive"}


def upload_blob(conn, account_name, container_name, file_name, content: bytes, upload_dir=UPLOAD_DIR):
    """Save a file to disk and record its metadata. Rejects unsafe names, bad types, and oversized files."""
    if "/" in file_name or "\\" in file_name or file_name in ("", ".", ".."):
        raise ValueError("File name must not contain path separators")
    extension = Path(file_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type '{extension}' is not allowed")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("File is larger than the 1 MB limit")

    exists = conn.execute(
        "SELECT 1 FROM containers WHERE account_name = ? AND name = ?",
        (account_name, container_name),
    ).fetchone()
    if exists is None:
        raise ValueError(f"Container '{container_name}' does not exist in '{account_name}'")

    target_dir = upload_dir / account_name / container_name
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_path = target_dir / file_name
    stored_path.write_bytes(content)

    conn.execute(
        "DELETE FROM blobs WHERE account_name = ? AND container_name = ? AND file_name = ?",
        (account_name, container_name, file_name),
    )
    conn.execute(
        "INSERT INTO blobs (account_name, container_name, file_name, size_bytes, tier, stored_path) "
        "VALUES (?, ?, ?, ?, 'Hot', ?)",
        (account_name, container_name, file_name, len(content), str(stored_path)),
    )
    conn.commit()
    return {"file_name": file_name, "size_bytes": len(content), "tier": "Hot"}


def list_blobs(conn, account_name, container_name):
    """Return the metadata for every file in a container."""
    rows = conn.execute(
        "SELECT file_name, size_bytes, tier FROM blobs WHERE account_name = ? AND container_name = ? ORDER BY file_name",
        (account_name, container_name),
    ).fetchall()
    return [dict(r) for r in rows]


def load_vms(conn):
    """Return VMs in the same shape that vm.py and tenant.json use."""
    rows = conn.execute(
        "SELECT name, subscription, resource_group, size, power_state, hourly_rate, tags_json FROM vms ORDER BY name"
    ).fetchall()
    return [
        {
            "name": r["name"],
            "subscription": r["subscription"],
            "resourceGroup": r["resource_group"],
            "size": r["size"],
            "powerState": r["power_state"],
            "hourlyRate": r["hourly_rate"],
            "tags": json.loads(r["tags_json"]),
        }
        for r in rows
    ]


def save_vm_power_state(conn, vm_name, power_state):
    """Persist a VM's power state so it survives page reloads and restarts."""
    conn.execute("UPDATE vms SET power_state = ? WHERE name = ?", (power_state, vm_name))
    conn.commit()


def record_activity(conn, user_id, action, target, allowed, message):
    """Save one allowed or denied action to the activity table."""
    conn.execute(
        "INSERT INTO activity (time, user_id, action, target, result, message) VALUES (?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            user_id,
            action,
            target,
            "Allowed" if allowed else "Denied",
            message,
        ),
    )
    conn.commit()


def list_activity(conn, limit=10):
    """Return the newest activity rows, using the keys the lab page expects."""
    rows = conn.execute(
        "SELECT time, user_id AS user, action, target, result, message "
        "FROM activity ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def dashboard_summary(conn):
    """Collect counts for the dashboard from the database."""
    vm_rows = conn.execute(
        "SELECT power_state, COUNT(*) AS n FROM vms GROUP BY power_state"
    ).fetchall()
    vms_by_state = {r["power_state"]: r["n"] for r in vm_rows}
    total_vms = sum(vms_by_state.values())
    storage_accounts = conn.execute("SELECT COUNT(*) FROM storage_accounts").fetchone()[0]
    containers = conn.execute("SELECT COUNT(*) FROM containers").fetchone()[0]
    files = conn.execute("SELECT COUNT(*) FROM blobs").fetchone()[0]
    return {
        "total_vms": total_vms,
        "vms_by_state": vms_by_state,
        "storage_accounts": storage_accounts,
        "containers": containers,
        "files": files,
        "recent_activity": list_activity(conn, 5),
    }


def reset_demo_data(conn, upload_dir=UPLOAD_DIR):
    """Restore the public demo to its original sample state.

    Clears runtime data (uploads, container and file metadata, activity, and
    alert settings) and reloads VM states from tenant.json. Storage accounts
    created by visitors are removed; the demo storage account is recreated.
    """
    conn.execute("DELETE FROM blobs")
    conn.execute("DELETE FROM containers")
    conn.execute("DELETE FROM storage_accounts")
    conn.execute("DELETE FROM alert_history")
    conn.execute("DELETE FROM vm_alerts")
    conn.commit()

    # Remove uploaded files from disk so metadata and files stay in sync.
    if upload_dir.exists():
        for path in sorted(upload_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

    # Restore the seed VMs and clear the activity log.
    seed_database(conn)

    # Recreate the demo storage account and container.
    create_storage_account(conn, "stdemo001", "rg-web")
    create_container(conn, "stdemo001", "uploads")


def validate_subnet(vnet_range, subnet_range, existing_prefixes):
    """Check a subnet prefix is inside the VNet and does not overlap existing subnets.

    Returns a list of error messages; an empty list means the subnet is valid.
    """
    import ipaddress

    errors = []
    try:
        vnet = ipaddress.ip_network(vnet_range, strict=True)
        subnet = ipaddress.ip_network(subnet_range, strict=True)
    except ValueError as exc:
        return [f"Invalid address range: {exc}"]

    if not subnet.subnet_of(vnet):
        errors.append(f"{subnet} is not inside the VNet range {vnet}")

    for prefix in existing_prefixes:
        if subnet.overlaps(ipaddress.ip_network(prefix)):
            errors.append(f"{subnet} overlaps existing subnet {prefix}")

    return errors


def create_vnet(conn, name, resource_group, address_space):
    """Create a virtual network. The address space must be a valid CIDR block."""
    import ipaddress

    if not (2 <= len(name) <= 64):
        raise ValueError("VNet name must be 2-64 characters")

    try:
        ipaddress.ip_network(address_space, strict=True)
    except ValueError as exc:
        raise ValueError(f"Invalid address space: {exc}") from exc

    conn.execute(
        "INSERT INTO vnets (name, resource_group, address_space) VALUES (?, ?, ?)",
        (name, resource_group, address_space),
    )
    conn.commit()


def create_subnet(conn, vnet_name, name, address_prefix, nsg_name=None):
    """Create a subnet inside a VNet after validating its range."""
    row = conn.execute("SELECT address_space FROM vnets WHERE name = ?", (vnet_name,)).fetchone()
    if row is None:
        raise ValueError(f"VNet '{vnet_name}' does not exist")

    existing = [
        r["address_prefix"]
        for r in conn.execute(
            "SELECT address_prefix FROM subnets WHERE vnet_name = ?", (vnet_name,)
        ).fetchall()
    ]

    errors = validate_subnet(row["address_space"], address_prefix, existing)
    if errors:
        raise ValueError("; ".join(errors))

    conn.execute(
        "INSERT INTO subnets (name, vnet_name, address_prefix, nsg_name) VALUES (?, ?, ?, ?)",
        (name, vnet_name, address_prefix, nsg_name),
    )
    conn.commit()


def generate_cpu_sample(vm_name, tick):
    """Deterministic simulated CPU percentage (0-100) for a VM at a given tick.

    Not real telemetry: the value is derived from the VM name and tick so the
    demo is repeatable.
    """
    seed = sum(ord(ch) for ch in vm_name) + tick * 17
    return (seed * 37) % 101


def record_metric_sample(conn, vm_name, tick):
    """Compute a sample, store it if it crosses the VM's threshold, and return it."""
    row = conn.execute("SELECT cpu_threshold FROM vm_alerts WHERE vm_name = ?", (vm_name,)).fetchone()
    threshold = row["cpu_threshold"] if row else 80
    cpu = generate_cpu_sample(vm_name, tick)
    severity = "Critical" if cpu >= 90 else ("Warning" if cpu >= threshold else None)
    if severity:
        conn.execute(
            "INSERT INTO alert_history (time, vm_name, cpu_percent, threshold, severity) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), vm_name, cpu, threshold, severity),
        )
        conn.commit()
    return {"vm": vm_name, "cpu": cpu, "threshold": threshold, "severity": severity}


def set_cpu_threshold(conn, vm_name, threshold):
    """Set the CPU alert threshold for one VM (1-100)."""
    if not (1 <= int(threshold) <= 100):
        raise ValueError("Threshold must be between 1 and 100")
    conn.execute(
        "INSERT INTO vm_alerts (vm_name, cpu_threshold) VALUES (?, ?) "
        "ON CONFLICT(vm_name) DO UPDATE SET cpu_threshold = excluded.cpu_threshold",
        (vm_name, int(threshold)),
    )
    conn.commit()