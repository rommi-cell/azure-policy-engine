import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Local Module Imports
from app.engine import load_policies, evaluate_resource
from app.rbac import load_tenant, check_access
from app.vm import perform_action
from app.activity_log import record, list_recent

app = FastAPI(title="Azure Policy Engine (Local Simulation)")
templates = Jinja2Templates(directory="app/templates")


# -----------------------------------------------------------------------------
# Policy Engine Routes
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
# RBAC & VM Lab Simulation Routes
# -----------------------------------------------------------------------------

@app.get("/lab", response_class=HTMLResponse)
def lab(request: Request):
    tenant = load_tenant()
    return templates.TemplateResponse(
        request,
        "lab.html",
        {
            "users": tenant["users"],
            "vms": tenant["vms"],
            "logs": list_recent(10),
            "message": None,
        },
    )


@app.post("/lab/action", response_class=HTMLResponse)
async def lab_action(request: Request):
    form = await request.form()
    user_id = form.get("user")
    vm_name = form.get("vm")
    action = form.get("action")

    tenant = load_tenant()
    result = perform_action(tenant, user_id, vm_name, action)
    record(user_id, action, vm_name, result["allowed"], result["message"])

    return templates.TemplateResponse(
        request,
        "lab.html",
        {
            "users": tenant["users"],
            "vms": tenant["vms"],
            "logs": list_recent(10),
            "message": result["message"],
            "allowed": result["allowed"],
        },
    )