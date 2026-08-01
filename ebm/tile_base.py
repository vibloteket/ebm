from __future__ import annotations

from .ports import RoutePermutation


class TileBase:
    """Contributor-facing tile interface."""

    id = "unknown.untitled"
    api_version = 1
    author = "unknown"
    title = "Untitled"
    routes: tuple[RoutePermutation, ...] = ()

    def build(self, tile):  # pragma: no cover - interface
        raise NotImplementedError

    def update(self, tile, dt: float) -> None:
        pass
