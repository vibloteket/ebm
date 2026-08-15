from __future__ import annotations

from ebm import TileBase, TileBuilder


RAIL = (49, 90, 168, 255)
BOX = (115, 76, 168, 255)


class TeleportCollector(TileBase):
    """T0 falls through a pipe while L0 collects and teleports to R0."""

    author = "Pi"

    def build(self, b: TileBuilder) -> None:
        # A real physical pipe carries T0 straight down to B0.
        _rail(b, (140, -20), (140, 420))
        _rail(b, (260, -20), (260, 420))

        # L0 opens into a collection box. Its floor and back wall are physical;
        # the sensor covers the inside without changing their collisions.
        _rail(b, (-20, 180), (120, 180), color=BOX)
        _rail(b, (120, 35), (120, 180), color=BOX)
        # Keep the sensor more than one ball radius inside L0. In a repeated
        # grid, the previous tile retains ownership until the complete ball has
        # crossed the shared edge; triggering earlier would reject the handoff.
        collector = b.sensor_box(31, 40, 115, 175)

        # Teleported balls appear above this passive ramp and roll through R0
        # under gravity. No velocity is assigned to them.
        _rail(b, (270, 320), (420, 355), color=BOX)
        _rail(b, (270, 225), (420, 255), color=BOX)

        def teleport(event):
            ball = event.ball
            ball.set_position((300, 275))
            ball.set_velocity((0, 0))
            return False

        b.on_ball_contact(collector, begin=teleport)


def _rail(b: TileBuilder, a, end, *, color=RAIL) -> None:
    b.static_segment(a, end, 6, friction=0.2, elasticity=0.05, fill_color=color)
