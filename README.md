
## AZ-104 concepts demonstrated (simulated)

| Concept | Where it appears |
|---|---|
| Azure Policy definitions | `policies/policies.json` |
| Deny effect | `allowedLocations`, `requireCostCenterTag` |
| Audit effect | `auditStorageHttps` |
| Modify effect | `modifyAddEnvironmentTag` |
| Resource governance and tagging | Required `costCenter` tag and `environment` tag |
| Compliance evaluation | `app/engine.py` |

## Limitations

- Simulates a small subset of Azure Policy. It does not implement the full policy language, initiatives, or remediation tasks.
- Does not connect to Azure, Azure Resource Manager, or any subscription.
- Uses a simplified operator set: `exists`, `equals`, `in`, `notIn`.

## Future improvements

- Add policy initiatives and assignments
- Add a compliance summary chart
- Support more operators and nested conditions

## Phase 2: Local Azure Lab (simulated Entra ID, RBAC, and VMs)

Everything in this section is simulated with local JSON and Python. The app does not authenticate to or call Azure.

### Features

- **Entra ID (simulated):** users and groups in `data/tenant.json`. Bob is a member of the `Ops-Team` group.
- **RBAC:** role definitions (Owner, Contributor, Reader) and role assignments at subscription and resource group scopes. Access is inherited by child scopes. Unknown users are denied by default.
- **Virtual machines:** start, stop, and deallocate actions, with power-state checks.
- **Governance:** the Phase 1 policy engine runs before RBAC. A VM that violates a policy is denied.
- **Activity log:** every allowed and denied action is recorded in `data/activity.json`, like the Azure Activity Log.
- **Cost estimate:** only running VMs incur a compute charge in the simulation.

### AZ-104 mapping (simulated)

| Concept | Where it appears |
|---|---|
| Entra ID users and groups | `data/tenant.json`, `expand_principals` in `app/rbac.py` |
| RBAC role definitions | `roleDefinitions` in `data/tenant.json` |
| Role assignments and scope inheritance | `scope_applies` and `check_access` in `app/rbac.py` |
| Least privilege and deny by default | `check_access` returns False unless an assignment grants the action |
| Azure Policy before action | `check_vm_policies` in `app/vm.py` |
| VM power management | `perform_action` in `app/vm.py` |
| Activity log and monitoring | `app/activity_log.py` |
| Cost management | `monthly_cost` in `app/vm.py` |

### Run the tests

```
python -m pytest -v
```

Expected result: 11 tests pass.

### Viva questions (Phase 2)

- **Why does a group member get access?** The assignment is made to the group, and `expand_principals` adds the user's groups when checking access.
- **Why is Bob denied on `vm-db-01`?** His Contributor role is scoped to `rg-web`, so it does not inherit down to `rg-data`.
- **Why run policy before RBAC?** Governance rules apply regardless of who asks, as in Azure.
- **Why is the VM state reset after a page reload?** The tenant file is read on each request and changes are kept in memory only. A real system would store state in a database.

## Author

Rohan Aditya (B.Tech CSE)