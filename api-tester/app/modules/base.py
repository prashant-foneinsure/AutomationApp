"""The extension point for new test types.

A test type is a self-describing object. The side navigation is rendered from
GET /api/modules, so registering a module is what puts it in the nav -- there
is no nav code to edit.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import APIRouter


@dataclass(frozen=True)
class ModuleInfo:
    slug: str          # URL + frontend key, e.g. "api-testing"
    title: str         # side-nav label
    description: str = ""
    icon: str = "beaker"


class TestModule(ABC):
    info: ModuleInfo

    @abstractmethod
    def router(self) -> APIRouter:
        """Return this module's routes. Prefix them under
        /api/modules/<slug> to keep the surface namespaced."""
