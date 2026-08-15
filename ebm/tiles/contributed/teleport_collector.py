from __future__ import annotations

from ebm import TileBase, TileBuilder


RAIL = (49, 90, 168, 255)
BOX = (115, 76, 168, 255)
MAGIC = (113, 72, 255, 128)
MAGIC_OFF = (113, 72, 255, 0)
BUMPER_COLORS = (
    (245, 196, 35, 255),   # yellow
    (34, 170, 92, 255),    # green
    (220, 55, 55, 255),    # red
)


class TeleportCollector(TileBase):
    """T0 falls through a pipe while L0 collects and teleports to R0."""

    author = "Pi"

    def build(self, b: TileBuilder) -> None:
        self.magic_time = 0.0

        # A real physical pipe carries T0 straight down to B0.
        _rail(b, (140, -20), (140, 420))
        _rail(b, (260, -20), (260, 420))

        # Three alternating bumpers make the fall through the pipe visible.
        # Each bumper physically deflects the ball and dyes it on contact.
        for center, color in zip(
            ((158, 105), (242, 215), (158, 325)),
            BUMPER_COLORS,
        ):
            bumper = b.static_circle(
                center,
                18,
                friction=0.15,
                elasticity=0.9,
                fill_color=color,
                stroke_color=(70, 55, 35, 255),
            )

            def dye_ball(event, bumper_color=color):
                event.ball.set_fill_color(bumper_color)

            b.on_ball_contact(bumper, begin=dye_ball)

        # L0 opens into a collection box. Its floor leads to the right wall,
        # which is also the teleport trigger.
        # A short funnel lip catches upward-angled L0 arrivals and directs
        # them into the wall without itself triggering teleportation.
        _rail(b, (-20, 180), (70, 180), color=BOX)
        _rail(b, (25, 35), (70, 35), color=BOX)
        # The physical right wall itself is the trigger: proximity alone does
        # nothing; Pymunk must report actual ball/wall contact.
        portal = _rail(b, (35, 35), (35, 180), color=BOX)

        # Teleported balls appear above this passive ramp and roll through R0.
        _rail(b, (270, 320), (420, 355), color=BOX)
        _rail(b, (270, 225), (420, 255), color=BOX)

        # The broad translucent beam is visual only. It flashes together with
        # the portal wall, making the ball's otherwise instantaneous journey
        # visible without blocking the machinery underneath.
        beam = b.visual_segment(
            (35, 108),
            (300, 275),
            20,
            fill_color=MAGIC_OFF,
        )
        self.portal = portal
        self.beam = beam

        def teleport(event):
            source = event.ball.position
            beam.set_segment_points(source, (300, 275))
            event.ball.set_position((300, 275))
            event.ball.set_velocity((0, 0))
            portal.set_fill_color(MAGIC)
            beam.set_fill_color(MAGIC)
            self.magic_time = 0.28
            return False

        b.on_ball_contact(portal, pre_solve=teleport)

    def update(self, _b: TileBuilder, dt: float) -> None:
        if self.magic_time <= 0:
            return
        self.magic_time = max(0.0, self.magic_time - dt)
        if self.magic_time == 0:
            self.portal.set_fill_color(BOX)
            self.beam.set_fill_color(MAGIC_OFF)


def _rail(b: TileBuilder, a, end, *, color=RAIL):
    return b.static_segment(
        a,
        end,
        6,
        friction=0.2,
        elasticity=0.05,
        fill_color=color,
    )
