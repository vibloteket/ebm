from __future__ import annotations

from .ports import RoutePermutation


class TileBase:
    """Contributor-facing tile interface."""

    id = "unknown.untitled"
    api_version = 1
    author = "unknown"
    title = "Untitled"
    routes: tuple[RoutePermutation, ...] = ()

    def build(self, builder):  # pragma: no cover - interface
        """Create this instance's physical and visual resources with a TileBuilder."""
        raise NotImplementedError

    def update(self, builder, dt: float) -> None:
        """Advance optional tile state; dt is elapsed simulation time in seconds."""
        pass
