# app/main.py
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.tasks import router as tasks_router
from app.api.allocations import router as allocations_router
from app.api.deliverables import router as deliverables_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(health_router, tags=["health"])
app.include_router(tasks_router, tags=["tasks"])
app.include_router(allocations_router, tags=["allocations"])
app.include_router(deliverables_router, tags=["deliverables"])
