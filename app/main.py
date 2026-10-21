import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Local Module Imports
from app.engine import load_policies, evaluate_resource
from app.rbac import load_tenant
from app.vm import perform_action
from app.storage import (
    initialize_database,
    get_connection,
    load_vms,
    save_vm_power_state,
    record_activity,
    list_activity,
    dashboard_summary,
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
        {"result": None, "resource_text": ""}
    )


@app.post("/evaluate", response_class=HTMLResponse)
async def evaluate(request: Request):
    form = await request.form()
    resource_text = form.get("resource", "")
    
    try:
        resource = json.loads(resource_text)
        result = evaluate_resource(resource, load_policies())
        error = None
    except json.JSONDecodeError as exc:
        result = None
        error = f"Invalid JSON: {exc}"

    return templates.TemplateResponse(
        request,
        "index.html",
        {"result": result, "error": error, "resource_text": resource_text},
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

    return templates.TemplateResponse(
        request, 
        "dashboard.html", 
        {"summary": summary}
    )