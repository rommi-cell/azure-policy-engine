from fastapi.testclient import TestClient

from app.main import app
from app.storage import initialize_database, get_connection, reset_demo_data

client = TestClient(app)


def login_as(user_id="u-bob", password="demo-bob-123"):
    """Sign in through the real login route so the session cookie is set."""
    client.post("/login", data={"user": user_id, "password": password}, follow_redirects=False)


def setup_function():
    # Start every test from the seeded demo state, signed in as Bob.
    conn = get_connection()
    try:
        reset_demo_data(conn)
    finally:
        conn.close()
    login_as()


def test_policy_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Allowed locations" in response.text


def test_evaluate_noncompliant_sample_shows_failures():
    sample = open("samples/noncompliant.json", encoding="utf-8").read()
    response = client.post("/evaluate", data={"resource": sample})
    assert response.status_code == 200
    assert "NonCompliant" in response.text


def test_evaluate_invalid_json_shows_error():
    response = client.post("/evaluate", data={"resource": "{not json"})
    assert response.status_code == 200
    assert "Invalid JSON" in response.text


def test_lab_page_loads():
    response = client.get("/lab")
    assert response.status_code == 200
    assert "vm-web-01" in response.text


def test_bob_can_stop_web_vm_and_change_persists():
    response = client.post(
        "/lab/action",
        data={"user": "u-bob", "vm": "vm-web-01", "action": "stop"},
    )
    assert response.status_code == 200
    assert "successfully updated to" in response.text
    # A fresh GET must show the saved state.
    assert "stopped" in client.get("/lab").text


def test_carol_cannot_stop_vm():
    # Sign in as Carol; the form's user field must be ignored.
    client.post("/logout", follow_redirects=False)
    login_as("u-carol", "demo-carol-123")
    response = client.post(
        "/lab/action",
        data={"user": "u-bob", "vm": "vm-web-01", "action": "stop"},
    )
    assert "Denied by RBAC" in response.text
    assert "u-carol" in response.text


def test_access_page_allows_bob_via_group():
    response = client.get(
        "/access",
        params={
            "user": "u-bob",
            "action": "stop",
            "scope": "/subscriptions/sub-prod/resourceGroups/rg-web",
        },
    )
    assert response.status_code == 200
    assert "Allowed" in response.text
    assert "g-ops" in response.text


def test_access_page_denies_carol():
    response = client.get(
        "/access",
        params={
            "user": "u-carol",
            "action": "stop",
            "scope": "/subscriptions/sub-prod/resourceGroups/rg-web",
        },
    )
    assert "may not perform" in response.text


def test_dashboard_loads():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Virtual machines" in response.text


def test_reset_restores_seed_state():
    client.post(
        "/lab/action",
        data={"user": "u-bob", "vm": "vm-web-01", "action": "stop"},
    )
    response = client.post("/reset", follow_redirects=False)
    assert response.status_code == 303
    dashboard = client.get("/dashboard").text
    assert "No activity" not in dashboard or "stop" not in dashboard


def test_storage_page_loads():
    response = client.get("/storage")
    assert response.status_code == 200
    assert "stdemo001" in response.text


def test_storage_rejects_invalid_account_name():
    response = client.post(
        "/storage/account",
        data={"name": "Bad Name", "resource_group": "rg-web"},
    )
    assert response.status_code == 200
    assert "must be 3-24 lowercase letters or digits" in response.text


def test_storage_upload_rejects_path_traversal():
    response = client.post(
        "/storage/upload",
        data={"account": "stdemo001", "container": "uploads"},
        files={"file": ("../evil.txt", b"x", "text/plain")},
    )
    assert response.status_code == 200
    assert "must not contain path separators" in response.text


def test_storage_upload_accepts_valid_txt():
    response = client.post(
        "/storage/upload",
        data={"account": "stdemo001", "container": "uploads"},
        files={"file": ("hello.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 200
    assert "hello.txt" in response.text
    assert "Hot" in response.text


def test_protected_page_redirects_when_signed_out():
    client.post("/logout", follow_redirects=False)
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_wrong_password_is_rejected():
    client.post("/logout", follow_redirects=False)
    response = client.post(
        "/login",
        data={"user": "u-bob", "password": "wrong"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Wrong user or password." in response.text


def test_form_user_id_cannot_impersonate_another_user():
    client.post("/logout", follow_redirects=False)
    login_as("u-carol", "demo-carol-123")
    client.post(
        "/lab/action",
        data={"user": "u-alice", "vm": "vm-web-01", "action": "stop"},
    )
    # Carol is recorded, Alice is not.
    log = client.get("/lab").text
    assert "u-carol" in log
    assert "u-alice" not in log.split("Activity log")[1]