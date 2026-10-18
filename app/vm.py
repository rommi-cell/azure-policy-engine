"""Local VM management (simulated Azure Virtual Machines) with RBAC and Policy enforcement."""

from app.rbac import check_access

POWER_TRANSITIONS = {
    "start": ("deallocated", "running"),
    "stop": ("running", "stopped"),
    "deallocate": ("running", "deallocated"),
}


def check_vm_policies(vm):
    """Run the Phase 1 policy engine against a VM's tags before it is changed."""
    from app.engine import load_policies, evaluate_resource

    resource = {
        "name": vm["name"],
        "location": "eastus",
        "tags": dict(vm.get("tags", {})),
        "properties": {"supportsHttpsTrafficOnly": True},
    }
    result = evaluate_resource(resource, load_policies())
    failed = [r["displayName"] for r in result["results"] if r["status"] == "NonCompliant"]
    return {"compliant": not failed, "failedPolicies": failed}


def find_vm(tenant, vm_name):
    """Find a VM in the tenant dictionary by its name."""
    for vm in tenant.get("vms", []):
        if vm["name"] == vm_name:
            return vm
    return None


def vm_scope(vm):
    """Generate the Azure Resource ID scope for a VM."""
    return (
        f"/subscriptions/{vm['subscription']}"
        f"/resourceGroups/{vm['resourceGroup']}"
        f"/providers/Microsoft.Compute/virtualMachines/{vm['name']}"
    )


def perform_action(tenant, user_id, vm_name, action):
    """Apply a power action to a VM if RBAC and Policy checks allow it. Returns a result dict."""
    vm = find_vm(tenant, vm_name)
    if vm is None:
        return {"allowed": False, "message": f"VM '{vm_name}' not found"}

    # 1. Check Policy Compliance
    policy_check = check_vm_policies(vm)
    if not policy_check["compliant"]:
        policies_str = ", ".join(policy_check["failedPolicies"])
        return {
            "allowed": False,
            "message": f"Denied by Policy: VM '{vm_name}' violates [{policies_str}]",
        }

    # 2. Check RBAC Access
    allowed, reasons = check_access(tenant, user_id, action, vm_scope(vm))
    if not allowed:
        return {
            "allowed": False,
            "message": f"Denied by RBAC: User '{user_id}' lacks permission for '{action}' on {vm_name}",
        }

    # 3. Validate Power State Transition
    if action not in POWER_TRANSITIONS:
        return {"allowed": False, "message": f"Unsupported action: '{action}'"}

    required_state, new_state = POWER_TRANSITIONS[action]
    if vm["powerState"] != required_state:
        return {
            "allowed": False,
            "message": f"Cannot {action} {vm_name}: current state is '{vm['powerState']}'",
        }

    # 4. Apply State Change
    vm["powerState"] = new_state
    return {
        "allowed": True,
        "message": f"{vm_name} successfully updated to '{new_state}'",
        "reasons": reasons,
    }


def monthly_cost(vm, hours=730):
    """Compute-only cost estimate. Deallocated/Stopped VMs incur no compute charge."""
    if vm.get("powerState") != "running":
        return 0.0
    return round(vm.get("hourlyRate", 0.0) * hours, 2)