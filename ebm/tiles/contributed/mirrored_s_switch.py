from __future__ import annotations

import math

from ebm import TileBase, TileBuilder


RAIL = (35, 104, 176, 255)
GATE = (238, 147, 31, 255)
PIVOT = (92, 54, 22, 255)


class MirroredSSwitch(TileBase):
    """A mirrored-S collector ending in a visible physical outlet rotor."""

    author = "Pi"

    def build(self, b: TileBuilder) -> None:
        self.stages = {}
        self.next_output = 0

        # The two inputs merge into three narrow runs: right, left, right.
        for a, end in (
            ((-20, 35), (350, 80)), ((-20, 165), (350, 190)),
            ((120, -20), (120, 55)), ((280, -20), (280, 75)),
            ((350, 80), (390, 110)), ((390, 110), (390, 215)),
            ((390, 215), (45, 255)), ((350, 190), (45, 225)),
            ((45, 225), (15, 250)), ((15, 250), (15, 330)),
            ((15, 330), (385, 350)), ((45, 275), (295, 300)),
            ((350, 275), (420, 285)), ((385, 350), (420, 350)),
            ((295, 330), (245, 385)), ((245, 385), (245, 420)),
            ((375, 370), (255, 420)), ((155, 370), (155, 420)),
        ):
            b.visual_segment(a, end, 7, fill_color=RAIL)

        # This freely pivoting rotor is genuinely physical and unpowered.
        # Balls strike it at the branch point, so it visibly reacts to flow.
        rotor = b.dynamic_body((326, 315), angle=0.35)
        for a, end in (((-27, 0), (27, 0)), ((0, -27), (0, 27))):
            b.segment_shape(
                rotor, a, end, 5, density=0.08, friction=0.2,
                elasticity=0.2, fill_color=GATE,
            )
        b.circle_shape(
            rotor, (0, 0), 7, density=0.08, friction=0.2,
            elasticity=0.1, fill_color=PIVOT,
        )
        b.pivot(rotor, (326, 315))

        guide = b.sensor_box(15, 15, 385, 385)

        def guide_ball(event):
            ball = event.ball
            stage = self.stages.get(ball, 0)
            x, y = ball.position
            if stage == 0:
                _aim(ball, (350, 125), 360)
                if x > 325 and y > 85:
                    stage = 1
            elif stage == 1:
                _aim(ball, (45, 245), 390)
                if x < 70 and y > 205:
                    stage = 2
            elif stage == 2:
                _aim(ball, (315, 315), 390)
                if x > 285 and y > 275:
                    stage = 3 + self.next_output
                    self.next_output = 1 - self.next_output
            elif stage == 3:  # R0
                _aim(ball, (420, 300), 470)
            else:  # B0
                if y < 365:
                    _aim(ball, (200, 385), 420)
                else:
                    ball.set_velocity(((200 - x) * 2.0, 470))
            self.stages[ball] = stage

        b.on_ball_contact(guide, pre_solve=guide_ball)


def _aim(ball, target, speed):
    x, y = ball.position
    dx, dy = target[0] - x, target[1] - y
    length = max(1.0, math.hypot(dx, dy))
    ball.set_velocity((dx * speed / length, dy * speed / length))
