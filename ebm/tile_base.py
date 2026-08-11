from __future__ import annotations

import re
from types import ModuleType

from .tile_api import TileBuilder


TILE_API_VERSION = 1


class TileBase:
    """Contributor-facing flow tile interface."""

    author = "unknown"

    def build(self, builder: TileBuilder) -> None:  # pragma: no cover - interface
        """Create this instance's physical and visual resources with a TileBuilder."""
        raise NotImplementedError

    def update(self, builder: TileBuilder, dt: float) -> None:
        """Advance optional tile state; dt is elapsed simulation time in seconds."""
        pass


def tile_class_from_module(module: ModuleType) -> type[TileBase]:
    """Return the one TileBase subclass defined by a tile module."""
    candidates = [
        value
        for value in module.__dict__.values()
        if (
            isinstance(value, type)
            and value is not TileBase
            and issubclass(value, TileBase)
            and value.__module__ == module.__name__
        )
    ]
    if not candidates:
        raise TypeError("Tile source must define exactly one TileBase subclass; found none")
    if len(candidates) > 1:
        names = ", ".join(candidate.__name__ for candidate in candidates)
        raise TypeError(f"Tile source must define exactly one TileBase subclass; found: {names}")
    return candidates[0]


def tile_display_name(tile_class: type[TileBase]) -> str:
    """Turn a Python class name into the contributor-facing display name."""
    name = tile_class.__name__
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    name = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", name)
    name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return name
