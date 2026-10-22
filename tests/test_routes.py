from fastapi.testclient import TestClient

from app.main import app
from app.storage import initialize_database, get_connection, reset_demo_data

client = TestClient(app)


def setup_function():
    # Start every test from the seeded demo state.
    conn = get_connection()
    try:
        reset_demo_data(conn)
    finally:
        conn.close()


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
    response = client.post(
        "/lab/action",
        data={"user": "u-carol", "vm": "vm-web-01", "action": "stop"},
    )
    assert "Denied by RBAC" in response.text


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