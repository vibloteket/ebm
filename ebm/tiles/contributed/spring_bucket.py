from __future__ import annotations

import math

from ebm import TileBase, TileBuilder


class SpringBucket(TileBase):
    """A spring-hung bucket; only its one-ball bottom hatch is controlled."""

    author = "Pi"
    enabled = True
    MIN_BALLS = 5

    def build(self, b: TileBuilder):
        self.balls = set()
        self.releasing = set()
        self.open = False
        self.cooldown = 0.0
        self.release_count = 0
        self.bucket = b.dynamic_body((170, 215))
        self.anchor = (170, 25)
        self.attachment = (0, -65)
        for a, end in (
            ((-65, -36), (-65, 40)), ((65, -36), (65, 40)),
            ((-65, -15), (-20, 40)), ((20, 40), (65, -15)),
        ):
            b.segment_shape(self.bucket, a, end, 3, density=.014,
                            friction=.05, elasticity=0, fill_color=(49, 90, 168, 255))
        self.hatch = b.segment_shape(self.bucket, (-20, 40), (20, 40), 2,
                                    density=.0001, friction=.3, elasticity=0,
                                    fill_color=(220, 140, 35, 255))
        # This raised edge is part of the hatch. It breaks the symmetric
        # seating that otherwise forms a two-ball arch over the opening.
        self.gate_finger = b.segment_shape(self.bucket, (-12, 25), (-12, 40), 1,
                                          density=.0001, friction=0, elasticity=0,
                                          fill_color=(220, 140, 35, 255))
        b.spring(self.bucket, self.anchor, self.attachment,
                 rest_length=63, stiffness=800, damping=180)
        # An elastic suspension with a physical extension limit. Neither this
        # safety cord nor its drawing creates a collision shape.
        b.rope(self.bucket, self.anchor, self.attachment, max_length=130)
        self.cord = b.visual_segment(self.anchor, self._world(self.attachment), 1.5,
                                     fill_color=(115, 80, 45, 255), dynamic=True)
        self.handle = [b.visual_segment(self._world(self.attachment), self._world(p), 1.5,
                                       fill_color=(115, 80, 45, 255), dynamic=True)
                       for p in ((-65, -36), (65, -36))]
        sensor = b.sensor_polygon(self.bucket, ((-61, -36), (61, -36), (61, 43), (-61, 43)))
        b.on_ball_contact(sensor, begin=lambda event: self.balls.add(event.ball),
                          separate=lambda event: self.balls.discard(event.ball))

        # Passive inlet guides: both inputs collect in the same bucket.
        for a, end in (
            ((3, 165), (145, 170)), ((3, 30), (115, 30)),
            ((140, 3), (140, 30)), ((140, 30), (140, 120)),
            ((270, 3), (270, 150)), ((270, 150), (210, 170)),
            # Passive splitter and output rails. The narrow B0 throat removes
            # sideways motion; R0's slope supplies speed without a magic push.
            ((195, 335), (397, 355)),
            ((3, 260), (100, 330)), ((100, 330), (145, 390)),
            ((145, 390), (145, 397)),
            ((185, 350), (185, 397)),
        ):
            b.static_segment(a, end, 3, friction=0, elasticity=0)
        b.static_segment((170, 310), (195, 335), 3, friction=0, elasticity=1)

    def _world(self, point):
        x, y = self.bucket.position
        c, s = math.cos(self.bucket.angle), math.sin(self.bucket.angle)
        return x + c * point[0] - s * point[1], y + s * point[0] + c * point[1]

    def _local(self, ball):
        x, y = ball.position
        bx, by = self.bucket.position
        c, s = math.cos(self.bucket.angle), math.sin(self.bucket.angle)
        return c * (x - bx) + s * (y - by), -s * (x - bx) + c * (y - by)

    def update(self, b: TileBuilder, dt: float):
        attachment = self._world(self.attachment)
        self.cord.set_segment_points(self.anchor, attachment)
        for visual, point in zip(self.handle, ((-65, -36), (65, -36))):
            visual.set_segment_points(attachment, self._world(point))
        self.cooldown = max(0, self.cooldown - dt)
        if self.open:
            for ball in tuple(self.releasing):
                try:
                    _, y = self._local(ball)
                    clear = y - ball.radius > 43
                except PermissionError:
                    clear = True
                if clear:
                    self.hatch.resume()
                    self.gate_finger.resume()
                    self.open = False
                    self.releasing.clear()
                    self.release_count += 1
                    self.cooldown = .1
                    break
        elif not self.cooldown:
            contained = set()
            for ball in tuple(self.balls):
                try:
                    x, y = self._local(ball)
                    r = ball.radius
                    floor_y = 40 - max(0, abs(x) - 20) * 55 / 45
                    if abs(x) <= 62 - r + .5 and -36 <= y <= floor_y:
                        contained.add(ball)
                except PermissionError:
                    self.balls.discard(ball)
            if len(contained) >= self.MIN_BALLS:
                self.releasing = contained
                self.hatch.pause()
                self.gate_finger.pause()
                self.open = True
