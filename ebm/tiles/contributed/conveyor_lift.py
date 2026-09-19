from __future__ import annotations

import math

from ebm import TileBase, TileBuilder


BELT_SPEED = 85.0
PIN_SPACING = 38.0
PIN_RADIUS = 5.0
BELT_COLOR = (221, 139, 36, 255)
EXIT_RAILS = (
    ((270, 250), (360, 325)), ((360, 325), (395, 325)),
    ((290, 210), (380, 290)), ((380, 290), (395, 290)),
)


class ConveyorLift(TileBase):
    """Independent L0→B0 chute and T0→R0 physical pin conveyor."""

    author = "Pi"
    enabled = True

    def build(self, b: TileBuilder):
        # L0 has its own narrow vertical chute and a shallow, enclosed ramp to
        # B0. It never shares geometry or storage with the conveyor stream.
        for a, end in (
            ((5, 192), (70, 220)), ((70, 220), (155, 350)),
            ((155, 350), (155, 395)),
            ((65, 50), (105, 155)), ((105, 155), (195, 335)),
            ((195, 335), (195, 395)),
        ):
            b.static_segment(a, end, 5, friction=.05, elasticity=.45)

        # T0 falls onto a plateau. The sloping rail supports each ball while
        # the actual moving pins carry it uphill. The return run is beneath
        # the rail and therefore cannot touch queued or carried balls.
        for a, end in (
            ((120, 3), (120, 125)), ((280, 3), (280, 85)),
            ((120, 125), (205, 270)), ((280, 85), (300, 105)),
            ((195, 285), (300, 145)),
            # A physical backstop catches the ball as its pin rounds the top.
            ((365, 85), (365, 225)),
        ):
            b.static_segment(a, end, 3, friction=.04, elasticity=0)
        # Passive impact chute: its lower rail converts the drop into outward
        # motion before the final nearly-horizontal R0 guide.
        for a, end in EXIT_RAILS:
            b.static_segment(a, end, 5, friction=0, elasticity=.45)

        # A closed, continuously circulating chain of real colliders. Moving
        # a kinematic chain around its prescribed loop is the sole powered
        # conveyor action; balls themselves are never inspected or modified.
        self.path = (
            (210.0, 280.0), (300.0, 137.0),
            (325.0, 170.0), (235.0, 313.0),
        )
        lengths = [math.dist(self.path[i], self.path[(i + 1) % 4]) for i in range(4)]
        self.cumulative = [0.0]
        for length in lengths:
            self.cumulative.append(self.cumulative[-1] + length)
        self.path_length = self.cumulative[-1]
        count = max(2, round(self.path_length / PIN_SPACING))
        self.pins = []
        for index in range(count):
            distance = index * self.path_length / count
            position, velocity, angle = self._sample(distance)
            pin = b.kinematic_body(position, angle=angle)
            b.segment_shape(pin, (0, -2), (0, -27), PIN_RADIUS,
                            density=.01, friction=.8, elasticity=0,
                            fill_color=BELT_COLOR)
            pin.set_velocity(velocity)
            self.pins.append((pin, distance))
        self.travel = 0.0

    def _sample(self, distance):
        distance %= self.path_length
        for index in range(4):
            start_distance, end_distance = self.cumulative[index:index + 2]
            if distance <= end_distance:
                a, end = self.path[index], self.path[(index + 1) % 4]
                length = end_distance - start_distance
                portion = (distance - start_distance) / length
                x = a[0] + (end[0] - a[0]) * portion
                y = a[1] + (end[1] - a[1]) * portion
                velocity = (
                    BELT_SPEED * (end[0] - a[0]) / length,
                    BELT_SPEED * (end[1] - a[1]) / length,
                )
                return (x, y), velocity, math.atan2(end[1] - a[1], end[0] - a[0])
        raise AssertionError("unreachable conveyor position")

    def update(self, b: TileBuilder, dt: float):
        self.travel = (self.travel + BELT_SPEED * dt) % self.path_length
        for pin, offset in self.pins:
            position, velocity, angle = self._sample(offset + self.travel)
            pin.set_position(position)
            pin.set_angle(angle)
            pin.set_velocity(velocity)
