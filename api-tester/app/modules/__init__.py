"""Module registry.

Adding a test type:
  1. create app/modules/<name>/ with a TestModule subclass
  2. import it below and add it to REGISTRY

That is all the backend change. The side navigation is rendered from
GET /api/modules, so the new entry appears there automatically.
"""
from fastapi import APIRouter

from .api_testing import ApiTestingModule
from .base import ModuleInfo, TestModule

REGISTRY: list[TestModule] = [
    ApiTestingModule(),
]


def describe() -> list[dict]:
    return [
        {"slug": m.info.slug, "title": m.info.title,
         "description": m.info.description, "icon": m.info.icon}
        for m in REGISTRY
    ]


def install(app) -> None:
    """Include every module router. Call before the static mount."""
    for module in REGISTRY:
        app.include_router(module.router())
    app.include_router(_build_meta_router())


def _build_meta_router() -> APIRouter:
    meta = APIRouter(prefix="/api", tags=["meta"])

    @meta.get("/modules")
    def modules():
        return describe()

    @meta.get("/health")
    def health():
        return {"ok": True, "modules": len(REGISTRY)}

    return meta
