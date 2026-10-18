import json
from pathlib import Path

from app.engine import load_policies, evaluate_resource

ROOT = Path(__file__).resolve().parent.parent


def load_sample(name):
    with open(ROOT / "samples" / name, encoding="utf-8") as f:
        return json.load(f)


def status_map(result):
    return {r["policy"]: r["status"] for r in result["results"]}


def test_compliant_sample_passes_all_deny_and_audit_policies():
    result = evaluate_resource(load_sample("compliant.json"), load_policies())
    statuses = status_map(result)
    assert statuses["allowedLocations"] == "Compliant"
    assert statuses["requireCostCenterTag"] == "Compliant"
    assert statuses["auditStorageHttps"] == "Compliant"


def test_noncompliant_sample_fails_expected_policies():
    result = evaluate_resource(load_sample("noncompliant.json"), load_policies())
    statuses = status_map(result)
    assert statuses["allowedLocations"] == "NonCompliant"
    assert statuses["requireCostCenterTag"] == "NonCompliant"
    assert statuses["auditStorageHttps"] == "NonCompliant"


def test_modify_policy_adds_missing_tag():
    resource = {"name": "st1", "location": "eastus", "tags": {"costCenter": "CC-1"}}
    result = evaluate_resource(resource, load_policies())
    assert result["resource"]["tags"]["environment"] == "dev"
    assert status_map(result)["modifyAddEnvironmentTag"] == "Modified"


def test_missing_tags_dict_does_not_crash():
    resource = {"name": "st2", "location": "eastus"}
    result = evaluate_resource(resource, load_policies())
    assert status_map(result)["requireCostCenterTag"] == "NonCompliant"