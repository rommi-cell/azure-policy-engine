import json
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# Local Module Imports
from app.engine import load_policies, evaluate_resource
from app.rbac import load_tenant, check_access, expand_principals
from app.vm import perform_action
from app.storage import (
    initialize_database,
    get_connection,
    load_vms,
    save_vm_power_state,
    record_activity,
    list_activity,
    dashboard_summary,
    reset_demo_data,
    list_storage_accounts,
    list_blobs,
    create_storage_account,
    create_container,
    upload_blob,
    record_metric_sample,
    set_cpu_threshold,
)
from app.network import NsgRule, evaluate_nsg

app = FastAPI(title="Azure Policy Engine (Local Simulation)")
templates = Jinja2Templates(directory="app/templates")

# Ensure database schema is created and seeded on startup
initialize_database()


# -----------------------------------------------------------------------------
# Policy Engine Routes (Phase 1)
# -----------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"policies": load_policies(), "result": None, "resource_text": "", "error": None},
    )


@app.post("/evaluate", response_class=HTMLResponse)
async def evaluate(request: Request):
    form = await request.form()
    resource_text = form.get("resource", "")
    policies = load_policies()

    try:
        resource = json.loads(resource_text)
        result = evaluate_resource(resource, policies)
        error = None
    except json.JSONDecodeError as exc:
        result = None
        error = f"Invalid JSON: {exc}"

    return templates.TemplateResponse(
        request,
        "index.html",
        {"policies": policies, "result": result, "error": error, "resource_text": resource_text},
    )


# -----------------------------------------------------------------------------
# RBAC & VM Lab Simulation Routes (Database-backed)
# -----------------------------------------------------------------------------

@app.get("/lab", response_class=HTMLResponse)
def lab(request: Request):
    tenant = load_tenant()
    conn = get_connection()
    try:
        vms = load_vms(conn)
        logs = list_activity(conn, limit=10)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "lab.html",
        {"users": tenant["users"], "vms": vms, "logs": logs, "message": None},
    )


@app.post("/lab/action", response_class=HTMLResponse)
async def lab_action(request: Request):
    form = await request.form()
    user_id = form.get("user")
    vm_name = form.get("vm")
    action = form.get("action")

    conn = get_connection()
    try:
        tenant = load_tenant()
        tenant["vms"] = load_vms(conn)

        result = perform_action(tenant, user_id, vm_name, action)

        if result["allowed"]:
            updated_vm = next((v for v in tenant["vms"] if v["name"] == vm_name), None)
            if updated_vm:
                save_vm_power_state(conn, vm_name, updated_vm["powerState"])

        record_activity(conn, user_id, action, vm_name, result["allowed"], result["message"])

        vms = load_vms(conn)
        logs = list_activity(conn, limit=10)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "lab.html",
        {
            "users": tenant["users"],
            "vms": vms,
            "logs": logs,
            "message": result["message"],
            "allowed": result["allowed"],
        },
    )


# -----------------------------------------------------------------------------
# Dashboard Route
# -----------------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = get_connection()
    try:
        summary = dashboard_summary(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "dashboard.html", {"summary": summary})


# -----------------------------------------------------------------------------
# Identity and Access Route
# -----------------------------------------------------------------------------

ACCESS_ACTIONS = ["read", "start", "stop", "deallocate", "assignRoles"]
ACCESS_SCOPES = [
    {"value": "/subscriptions/sub-prod", "label": "Subscription sub-prod"},
    {"value": "/subscriptions/sub-prod/resourceGroups/rg-web", "label": "Resource group rg-web"},
    {"value": "/subscriptions/sub-prod/resourceGroups/rg-data", "label": "Resource group rg-data"},
]


@app.get("/access", response_class=HTMLResponse)
def access(
    request: Request,
    user: str = "",
    action: str = "read",
    scope: str = ACCESS_SCOPES[1]["value"],
):
    tenant = load_tenant()
    decision = None
    if user:
        allowed, reasons = check_access(tenant, user, action, scope)
        groups = sorted(expand_principals(tenant, user) - {user})
        if allowed:
            explanation = f"{user} may perform '{action}' at this scope."
        else:
            explanation = f"{user} may not perform '{action}' at this scope."
        if groups:
            explanation += f" Group memberships considered: {', '.join(groups)}."
        decision = {"allowed": allowed, "reasons": reasons, "explanation": explanation}

    return templates.TemplateResponse(
        request,
        "access.html",
        {
            "users": tenant["users"],
            "roles": tenant["roleDefinitions"],
            "actions": ACCESS_ACTIONS,
            "scopes": ACCESS_SCOPES,
            "selected_user": user or tenant["users"][0]["id"],
            "selected_action": action,
            "selected_scope": scope,
            "decision": decision,
        },
    )


# -----------------------------------------------------------------------------
# Reset Demo Data
# -----------------------------------------------------------------------------

@app.post("/reset")
def reset(request: Request):
    conn = get_connection()
    try:
        reset_demo_data(conn)
    finally:
        conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)


# -----------------------------------------------------------------------------
# Networking (simulated VNets, subnets, and NSG connectivity check)
# -----------------------------------------------------------------------------

DEMO_NSG_RULES = [
    NsgRule("allow-https", 100, "Inbound", "TCP", "443", "Allow"),
    NsgRule("deny-all-inbound", 200, "Inbound", "*", "*", "Deny"),
]


def ensure_demo_network(conn):
    """Create the demo VNet, subnets, and NSG rules if they are missing."""
    from app.storage import create_vnet, create_subnet

    exists = conn.execute("SELECT 1 FROM vnets WHERE name = 'vnet-demo'").fetchone()
    if exists is None:
        create_vnet(conn, "vnet-demo", "rg-web", "10.0.0.0/16")
        create_subnet(conn, "vnet-demo", "subnet-web", "10.0.1.0/24", "nsg-web")
        create_subnet(conn, "vnet-demo", "subnet-data", "10.0.2.0/24", "nsg-data")
        for rule in DEMO_NSG_RULES:
            conn.execute(
                "INSERT OR IGNORE INTO nsg_rules (nsg_name, priority, direction, protocol, port, access) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("nsg-web", rule.priority, rule.direction, rule.protocol, rule.port, rule.access),
            )
        conn.commit()


@app.get("/network", response_class=HTMLResponse)
def network(
    request: Request,
    port: int = 443,
    direction: str = "Inbound",
    protocol: str = "TCP",
):
    conn = get_connection()
    try:
        ensure_demo_network(conn)
        vnets = [dict(r) for r in conn.execute("SELECT * FROM vnets").fetchall()]
        subnets = [dict(r) for r in conn.execute("SELECT * FROM subnets").fetchall()]
        rule_rows = conn.execute(
            "SELECT * FROM nsg_rules WHERE nsg_name = 'nsg-web' ORDER BY priority"
        ).fetchall()
        rules = [
            NsgRule(
                f"rule-{r['priority']}",
                r["priority"],
                r["direction"],
                r["protocol"],
                r["port"],
                r["access"],
            )
            for r in rule_rows
        ]
    finally:
        conn.close()

    decision = evaluate_nsg(rules, direction, protocol, port)

    return templates.TemplateResponse(
        request,
        "network.html",
        {
            "vnets": vnets,
            "subnets": subnets,
            "rules": rules,
            "decision": decision,
            "port": port,
            "direction": direction,
            "protocol": protocol,
        },
    )


# -----------------------------------------------------------------------------
# Storage (simulated accounts, containers, and file uploads)
# -----------------------------------------------------------------------------

def storage_context(conn, account="", container=""):
    accounts = list_storage_accounts(conn)
    containers = []
    files = []
    if account:
        containers = [
            dict(r)
            for r in conn.execute(
                "SELECT name FROM containers WHERE account_name = ? ORDER BY name",
                (account,),
            ).fetchall()
        ]
    if account and container:
        files = list_blobs(conn, account, container)
    return {
        "accounts": accounts,
        "containers": containers,
        "files": files,
        "account": account,
        "container": container,
    }


@app.get("/storage", response_class=HTMLResponse)
def storage_page(request: Request, account: str = "stdemo001", container: str = "uploads"):
    conn = get_connection()
    try:
        ctx = storage_context(conn, account, container)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "storage.html", {"ctx": ctx, "message": None, "ok": True}
    )


@app.post("/storage/account", response_class=HTMLResponse)
async def storage_create_account(request: Request):
    form = await request.form()
    conn = get_connection()
    try:
        try:
            create_storage_account(conn, form.get("name", ""), form.get("resource_group", "rg-web"))
            message, ok = f"Storage account '{form.get('name')}' created.", True
        except ValueError as exc:
            message, ok = str(exc), False
        ctx = storage_context(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "storage.html", {"ctx": ctx, "message": message, "ok": ok}
    )


@app.post("/storage/upload", response_class=HTMLResponse)
async def storage_upload(request: Request, file: UploadFile = File(...)):
    form = await request.form()
    account = form.get("account", "")
    container = form.get("container", "")
    content = await file.read()
    conn = get_connection()
    try:
        try:
            info = upload_blob(conn, account, container, file.filename, content)
            message, ok = (
                f"Uploaded '{info['file_name']}' ({info['size_bytes']} bytes, tier {info['tier']}).",
                True,
            )
        except ValueError as exc:
            message, ok = str(exc), False
        ctx = storage_context(conn, account, container)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "storage.html", {"ctx": ctx, "message": message, "ok": ok}
    )


# -----------------------------------------------------------------------------
# Monitoring (simulated CPU metrics and alerts)
# -----------------------------------------------------------------------------

@app.get("/monitor", response_class=HTMLResponse)
def monitor(request: Request, vm: str = "vm-web-01", threshold: int = 80, samples: int = 0):
    conn = get_connection()
    try:
        message = None
        ok = True
        try:
            set_cpu_threshold(conn, vm, threshold)
        except ValueError as exc:
            message, ok = str(exc), False

        results = [record_metric_sample(conn, vm, t) for t in range(samples)]
        history = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM alert_history ORDER BY id DESC LIMIT 10"
            ).fetchall()
        ]
        vm_names = [v["name"] for v in load_vms(conn)]
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "monitor.html",
        {
            "vm": vm,
            "threshold": threshold,
            "samples": samples,
            "results": results,
            "history": history,
            "vm_names": vm_names,
            "message": message,
            "ok": ok,
        },
    )