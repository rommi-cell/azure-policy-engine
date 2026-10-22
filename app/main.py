import json
from fastapi import FastAPI, Request
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
)

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
        {
            "policies": load_policies(),
            "result": None,
            "resource_text": "",
            "error": None,
        },
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
        {
            "policies": policies,
            "result": result,
            "error": error,
            "resource_text": resource_text,
        },
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
        {
            "users": tenant["users"],
            "vms": vms,
            "logs": logs,
            "message": None,
        },
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

        record_activity(
            conn, user_id, action, vm_name, result["allowed"], result["message"]
        )

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

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"summary": summary},
    )


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
def access(request: Request, user: str = "", action: str = "read", scope: str = ACCESS_SCOPES[1]["value"]):
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