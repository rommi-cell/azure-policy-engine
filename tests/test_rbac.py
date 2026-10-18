import copy

from app.rbac import load_tenant, check_access
from app.vm import perform_action

RG_WEB_VM = "/subscriptions/sub-prod/resourceGroups/rg-web/providers/vm-web-01"
RG_DATA_VM = "/subscriptions/sub-prod/resourceGroups/rg-data/providers/vm-db-01"


def fresh_tenant():
    # Copy so that VM state changes in one test do not affect others.
    return copy.deepcopy(load_tenant())


def test_owner_inherits_access_to_all_resource_groups():
    t = fresh_tenant()
    assert check_access(t, "u-alice", "stop", RG_WEB_VM)[0] is True
    assert check_access(t, "u-alice", "stop", RG_DATA_VM)[0] is True


def test_group_membership_grants_contributor_on_rg_web():
    t = fresh_tenant()
    assert check_access(t, "u-bob", "stop", RG_WEB_VM)[0] is True
    assert check_access(t, "u-bob", "assignRoles", RG_WEB_VM)[0] is False


def test_contributor_has_no_access_outside_its_scope():
    t = fresh_tenant()
    assert check_access(t, "u-bob", "stop", RG_DATA_VM)[0] is False


def test_reader_can_read_but_not_change():
    t = fresh_tenant()
    assert check_access(t, "u-carol", "read", RG_WEB_VM)[0] is True
    assert check_access(t, "u-carol", "stop", RG_WEB_VM)[0] is False


def test_unknown_user_is_denied_by_default():
    t = fresh_tenant()
    assert check_access(t, "u-nobody", "read", RG_WEB_VM)[0] is False


def test_perform_action_stops_running_vm():
    t = fresh_tenant()
    result = perform_action(t, "u-bob", "vm-web-01", "stop")
    assert result["allowed"] is True
    assert t["vms"][0]["powerState"] == "stopped"


def test_perform_action_denied_leaves_vm_unchanged():
    t = fresh_tenant()
    result = perform_action(t, "u-carol", "vm-web-01", "stop")
    assert result["allowed"] is False
    assert t["vms"][0]["powerState"] == "running"