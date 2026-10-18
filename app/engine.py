"""Local policy evaluation engine (simulated Azure Policy behavior)."""

import json
from pathlib import Path

POLICIES_PATH = Path(__file__).resolve().parent.parent / "policies" / "policies.json"


def load_policies(path=POLICIES_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["policies"]


def get_field(resource, field):
    """Read a dotted field path such as 'tags.costCenter' from a resource dict."""
    value = resource
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def evaluate_rule(resource, rule):
    """Return True if the resource satisfies the rule condition."""
    actual = get_field(resource, rule["field"])
    operator = rule["operator"]
    values = rule.get("values", [])

    if operator == "exists":
        return actual is not None
    if operator == "equals":
        return actual == values[0]
    if operator == "in":
        return actual in values
    if operator == "notIn":
        return actual not in values
    raise ValueError(f"Unsupported operator: {operator}")


def evaluate_resource(resource, policies):
    """Check a resource against every policy and return a result per policy."""
    results = []
    modified = dict(resource)

    for policy in policies:
        compliant = evaluate_rule(modified, policy["rule"])
        status = "Compliant" if compliant else "NonCompliant"

        # Modify effect: add the missing tag instead of failing.
        if policy["effect"] == "Modify" and not compliant:
            tag_name = policy["rule"]["field"].split(".")[-1]
            modified.setdefault("tags", {})[tag_name] = policy["modifyValue"]
            status = "Modified"

        results.append({
            "policy": policy["name"],
            "displayName": policy["displayName"],
            "effect": policy["effect"],
            "status": status,
        })

    return {"results": results, "resource": modified}