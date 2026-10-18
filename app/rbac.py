"""Local RBAC engine (simulated Azure RBAC and Entra ID group membership)."""

import json
from pathlib import Path

TENANT_PATH = Path(__file__).resolve().parent.parent / "data" / "tenant.json"


def load_tenant(path=TENANT_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def expand_principals(tenant, user_id):
    """Return the user's own ID plus every group they belong to."""
    principals = {user_id}
    for group in tenant["groups"]:
        if user_id in group["members"]:
            principals.add(group["id"])
    return principals


def scope_applies(assignment_scope, resource_scope):
    """An assignment applies to its own scope and everything beneath it (inheritance)."""
    return resource_scope == assignment_scope or resource_scope.startswith(assignment_scope + "/")


def get_permissions(tenant, user_id, resource_scope):
    """Return the set of actions the user may perform on a resource, and which assignments granted them."""
    principals = expand_principals(tenant, user_id)
    actions = set()
    reasons = []

    for assignment in tenant["roleAssignments"]:
        if assignment["principal"] not in principals:
            continue
        if not scope_applies(assignment["scope"], resource_scope):
            continue
        role_actions = tenant["roleDefinitions"][assignment["role"]]
        actions.update(role_actions)
        reasons.append(f"{assignment['role']} via {assignment['principal']} at {assignment['scope']}")

    return {"actions": actions, "reasons": reasons}


def check_access(tenant, user_id, action, resource_scope):
    """Return (allowed, reasons) for a single action. Deny by default."""
    perms = get_permissions(tenant, user_id, resource_scope)
    allowed = action in perms["actions"]
    return allowed, perms["reasons"]