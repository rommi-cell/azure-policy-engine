# Azure AdminLab: Interactive AZ-104 Cloud Administration Simulator

A local web application that simulates Azure administration concepts covered by the AZ-104 exam. Everything runs on your computer. **Nothing connects to, logs into, or deploys to Microsoft Azure.**

## Features

- **Dashboard:** counts of VMs by power state, storage accounts, containers, files, and recent activity.
- **Policy Engine:** a list of simulated policies (Deny, Audit, Modify) and an evaluator that shows pass/fail per policy and the resource after Modify changes.
- **Identity and Access:** an access check that uses group membership and scope inheritance to allow or deny an action, with the role assignment that applied.
- **VM and Access Lab:** start, stop, and deallocate simulated VMs. Each action is checked by policy, then RBAC, then power-state rules. Results are saved in SQLite and survive restarts.
- **Activity log:** every allowed and denied action is recorded.
- **Storage (backend only):** storage accounts, containers, and validated file uploads stored in SQLite and on disk. There is no storage page yet.
- **Reset Demo Data:** restores the original sample state after a confirmation dialog.

## Public demo notice

This is a shared demonstration environment. All visitors see and change the same data. Do not enter real or sensitive information. Data can reset at any time, and it resets when the server restarts on a free host.

## Setup (Windows, PowerShell)

```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Run the app

```
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 in your browser. The database `data/azure_adminlab.db` is created automatically with sample data.

## Run the tests

```
python -m pytest -v
```

Expected: 11 tests pass.

## Project structure

```
azure-policy-engine/
├── app/
│   ├── main.py            # FastAPI routes
│   ├── engine.py          # policy evaluation
│   ├── rbac.py            # role and scope access checks
│   ├── vm.py              # VM actions (policy, RBAC, power state)
│   ├── activity_log.py    # older JSON activity helper (unused; replaced by storage.py)
│   ├── storage.py         # SQLite persistence and storage functions
│   └── templates/         # HTML pages sharing base.html
├── data/
│   ├── tenant.json        # seed users, groups, roles, VMs
│   └── azure_adminlab.db  # created at runtime (not committed)
├── policies/policies.json # policy definitions
├── samples/               # compliant and non-compliant templates
└── tests/                 # pytest tests
```

## Simulated vs real Azure

| Concept | This project | Real Azure |
|---|---|---|
| Azure Policy | Simplified rules with Deny, Audit, Modify | Full policy language, assignments, remediation |
| Entra ID users and groups | JSON seed data | Identity platform with real authentication |
| RBAC | Three roles, two-level inheritance | Built-in and custom roles across many scopes |
| Virtual machines | Power state changes only | Real compute, networking, and billing |
| Storage | Local files and SQLite metadata | Blob service with SAS and tier management |
| Activity log | Local database table | Azure Activity Log |

## Limitations

- No authentication: anyone with the URL can act as any simulated user.
- Networking, monitoring, cost management, and lifecycle rules are not implemented yet.
- The storage module has no web page; uploads are available through code only.
- Data is local SQLite and resets when the server restarts on free hosting.
- The policy language is a small subset of Azure Policy.

## Future improvements

- Storage page with upload, download, and tier changes
- Virtual networks, subnets, and NSG connectivity checks
- Metrics, alerts, budgets, and cost tables
- Hosted database and deployment to a public host

## Author

Rohan Aditya (B.Tech CSE)