from __future__ import annotations

from .tile_api import TileBuilder


class TileBase:
    """Contributor-facing flow tile interface."""

    id = "unknown.untitled"
    api_version = 2
    author = "unknown"
    title = "Untitled"

    def build(self, builder: TileBuilder) -> None:  # pragma: no cover - interface
        """Create this instance's physical and visual resources with a TileBuilder."""
        raise NotImplementedError

    def update(self, builder: TileBuilder, dt: float) -> None:
        """Advance optional tile state; dt is elapsed simulation time in seconds."""
        pass
