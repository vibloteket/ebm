from __future__ import annotations

from dataclasses import dataclass
import math

from ebm import DEFAULT_ROUTES, Port, RoutePermutation, TileBase


@dataclass
class PoweredChannelTile(TileBase):
    """Built-in powered guide: balls visibly follow each route centerline."""

    route: RoutePermutation

    id = "ebm.powered-channel"
    title = "Physical Channel"
    author = "EBM"
    api_version = 1
    routes = DEFAULT_ROUTES

    def __post_init__(self) -> None:
        if self.route not in self.routes:
            raise ValueError(f"unsupported route: {self.route}")

    def build(self, tile) -> None:
        # Entry sensor records route ownership. The guide then keeps each ball
        # on the centerline belonging to the route through this tile.
        entry_sensor = tile.sensor_box(7.75, 7.75, 192.25, 192.25)
        origin = tile.origin
        route_points = {
            entry: _route_points(entry, output, index)
            for index, (entry, output) in enumerate(zip(self.route.entries, self.route.exits))
        }

        def classify_and_steer(event):
            _follow_channel(event.ball_body, origin, self.route, route_points)

        tile.on_ball_contact(entry_sensor, classify_and_steer)
        for index, (entry, output) in enumerate(zip(self.route.entries, self.route.exits)):
            points = _route_points(entry, output, index)
            for a, b in zip(points, points[1:]):
                tile.visual_segment(a, b, 3)

    def update(self, _tile, _dt):
        pass


def _route_points(entry: Port, output: Port, _index: int):
    return [_inside(entry), _inside(output)]


def _follow_channel(body, origin, route, route_points):
    ox, oy = origin
    x, y = float(body.position.x - ox), float(body.position.y - oy)
    if getattr(body, "ebm_route_origin", None) != origin:
        body.ebm_route_origin = origin
        body.ebm_route_entry = None
    entry = getattr(body, "ebm_route_entry", None)
    if entry is None:
        if x <= 34:
            entry = Port.L0
        elif x >= 166:
            entry = Port.R0
        elif y <= 34:
            entry = Port.T0
        else:
            return
        body.ebm_route_entry = entry
    a, b = route_points[entry][0], route_points[entry][-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    denominator = dx * dx + dy * dy
    progress = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / denominator))
    cx, cy = a[0] + dx * progress, a[1] + dy * progress
    body.position = (ox + cx, oy + cy)
    remaining = math.hypot(b[0] - cx, b[1] - cy)
    if remaining < 36:
        _steer(body, origin, route)
        return
    length = math.sqrt(denominator)
    body.velocity = (dx / length * 165, dy / length * 165)


def _inside(port: Port):
    x, y = port.point
    if port == Port.T0:
        return x, y + 10
    if port == Port.B0:
        return x, y - 10
    if port in (Port.L0, Port.L1):
        return x + 10, y
    return x - 10, y


def _steer(body, origin, route):
    ox, oy = origin
    x, y = float(body.position.x - ox), float(body.position.y - oy)
    entry = getattr(body, "ebm_route_entry", None)
    if getattr(body, "ebm_route_origin", None) != origin:
        entry = None
        body.ebm_route_origin = origin
    if entry is None:
        if x <= 34:
            entry = Port.L0
        elif x >= 166:
            entry = Port.R0
        elif y <= 34:
            entry = Port.T0
        else:
            return
        body.ebm_route_entry = entry
    output = route.exit_for(entry)
    if output == Port.B0:
        error = 100 - x
        body.velocity = (
            max(-220, min(220, error * 5)),
            45 if abs(error) > 24 else max(140, min(280, float(body.velocity.y) + 14)),
        )
    elif output == Port.L1:
        error = 150 - y
        body.velocity = (
            max(-120, min(120, (100 - x) * 4)) if abs(error) > 24 else min(-140, max(-280, float(body.velocity.x) - 14)),
            max(-220, min(220, error * 5)),
        )
    else:
        error = 50 - y
        body.velocity = (
            max(-120, min(120, (100 - x) * 4)) if abs(error) > 24 else max(140, min(280, float(body.velocity.x) + 14)),
            max(-220, min(220, error * 5)),
        )


TILE_CLASS = PoweredChannelTile
