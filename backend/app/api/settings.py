"""Application settings + provider status endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.db.database import get_db
from app.models.settings import AppSettings
from app.schemas.common import ProviderStatusOut
from app.schemas.settings import AppSettingsIn, AppSettingsOut

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_singleton(db: Session) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=AppSettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return _get_singleton(db)


@router.put("", response_model=AppSettingsOut)
def update_settings(payload: AppSettingsIn, db: Session = Depends(get_db)):
    row = _get_singleton(db)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.get("/provider", response_model=ProviderStatusOut)
async def provider_status(request: Request):
    """Report whether the translation provider is configured and reachable.

    Never exposes the API key — only booleans and non-secret config.
    """
    provider = request.app.state.jobs.provider
    configured = app_settings.provider_configured
    if not configured:
        return ProviderStatusOut(
            configured=False,
            model=None,
            base_url=None,
            connected=False,
            detail=(
                "AGENTROUTER_API_KEY and/or AGENTROUTER_MODEL are missing. "
                "Copy .env.example to .env and fill them in."
            ),
        )
    ok, detail = await provider.validate_connection()
    return ProviderStatusOut(
        configured=True,
        model=provider.get_model(),
        base_url=app_settings.agentrouter_base_url,
        connected=ok,
        detail=detail,
    )


@router.get("/config")
def public_config():
    """Non-secret runtime configuration for the frontend."""
    return {
        "max_file_size_mb": app_settings.max_file_size_mb,
        "max_concurrent_translations": app_settings.max_concurrent_translations,
        "max_retries": app_settings.max_retries,
        "chunk_target_chars": app_settings.chunk_target_chars,
        "supported_types": ["pdf", "docx", "txt"],
        "ocr_engines": [
            {"name": e["name"], "available": e["available"]}
            for e in request_ocr_status()
        ],
    }


def request_ocr_status():
    from app.services.ocr import OCRManager

    return OCRManager().engine_status()
