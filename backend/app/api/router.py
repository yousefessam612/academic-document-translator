from fastapi import APIRouter

from app.api import dashboard, documents, memory, settings, terminology, translation, worker

api_router = APIRouter(prefix="/api")
api_router.include_router(documents.router)
api_router.include_router(translation.router)
api_router.include_router(terminology.router)
api_router.include_router(memory.router)
api_router.include_router(settings.router)
api_router.include_router(dashboard.router)
api_router.include_router(worker.router)
