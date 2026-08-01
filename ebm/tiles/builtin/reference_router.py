from __future__ import annotations

from dataclasses import dataclass

from ebm import ALL_ROUTES, RoutePermutation, TileBase
from ebm.tiles.builtin.powered_channel import _inside, _steer


@dataclass
class ReferenceRouterTile(TileBase):
    """Invisible steering fallback retained for non-production experiments."""

    route: RoutePermutation

    id = "ebm.reference-router"
    title = "Reference Router"
    author = "EBM"
    api_version = 1
    routes = ALL_ROUTES

    def __post_init__(self) -> None:
        if self.route not in self.routes:
            raise ValueError(f"unsupported route: {self.route}")

    def build(self, tile):
        sensor = tile.sensor_box(7.75, 7.75, 192.25, 192.25)
        origin = tile.origin
        for entry, output in zip(self.route.entries, self.route.exits):
            tile.visual_segment(_inside(entry), _inside(output), 4)
        tile.on_ball_contact(sensor, lambda event: _steer(event.ball_body, origin, self.route))

    def update(self, _tile, _dt):
        pass


TILE_CLASS = ReferenceRouterTile
