# app/main.py
from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse



from app.api.health import router as health_router
from app.api.tasks import router as tasks_router
from app.api.allocations import router as allocations_router
from app.api.deliverables import router as deliverables_router
from app.core.config import settings

# Contract v2 (B3): OpenAPI must reflect headers-only auth context.
app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description=settings.api_description,
)

OPEN_PATHS = {"/docs", "/openapi.json", "/redoc", "/favicon.ico", "/health"}

@app.middleware("http")
async def require_x_role(request: Request, call_next):
    if request.url.path in OPEN_PATHS:
        return await call_next(request)

    x_role = request.headers.get("X-Role")
    if not x_role or not x_role.strip():
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing X-Role header"},
        )

    return await call_next(request)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Headers-only auth context: document required headers via apiKey schemes.
    schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schemes = schema["components"]["securitySchemes"]

    schemes["XRole"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Role",
        "description": "MVP RBAC: set actor role (e.g. system, lead, qc, internal_controller, supervisor, executor).",
    }

    schemes["XOrgId"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Org-Id",
        "description": "Organization context (UUID). Required for protected endpoints.",
    }

    schemes["XActorUserId"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Actor-User-Id",
        "description": "Actor user id (UUID). Required for protected endpoints.",
    }

    # Apply globally (AND): all three headers are required for protected endpoints.
    schema["security"] = [{"XRole": [], "XOrgId": [], "XActorUserId": []}]

    # Public endpoints: remove security requirement explicitly.
    for path in ["/health"]:
        if path in schema.get("paths", {}):
            for _method, op in schema["paths"][path].items():
                if isinstance(op, dict):
                    op.pop("security", None)

    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi

app.include_router(health_router, tags=["health"])
app.include_router(tasks_router, tags=["tasks"])
app.include_router(allocations_router, tags=["allocations"])
app.include_router(deliverables_router, tags=["deliverables"])