from __future__ import annotations

import math

from ebm import TileBase, TileBuilder

# A funnel collects T0 into a bowl where a rotating spiked wheel shreds
# incoming balls into a handful of small balls (minis) that rain through the
# throat into a catch tray. L0 instead opens into a teleport box: the ball
# rolls in, slides behind the
# box's foreground plate, and reappears behind a matching plate just left of
# R0, rolling out through the exit. (Foreground graphics draw after balls, so
# the plates genuinely occlude them; no fade tricks.) Stage 1 keeps shredded
# balls in an
# invisible stockpile; stage 2 adds splitter buckets that convert a full tray
# load back into stockpiled balls at the outputs.

WHEEL = (200.0, 120.0)
SPOKES = 10
SPOKE_INNER = 12.0
SPOKE_OUTER = 62.0
SPOKE_RADIUS = 3.0
HUB_RADIUS = 12.0
WHEEL_RATE = 2.5

# Geometry contract: every path from T0 to the throat passes within
# SPOKE_OUTER of the wheel hub. The bowl walls guide wall-hugging balls to
# ~56 units from the hub and the free-fall cone from T0 crosses the swept
# disc, so no ball can reach the throat without touching a spoke. The bowl
# wall tops sit clear of the swallow box; the sides are deliberately less
# steep after the funnel was raised one ball.
BOWL_LEFT = ((60.0, 70.0), (170.0, 195.0))
BOWL_RIGHT = ((340.0, 70.0), (230.0, 195.0))
# The chute reaches below the tray wall tops so exiting minis are already
# between the tray walls; sideways hops over the tray walls cannot happen.
CHUTE_LEFT = ((170.0, 195.0), (170.0, 270.0))
CHUTE_RIGHT = ((230.0, 195.0), (230.0, 270.0))
TRAY_LEFT = ((110.0, 265.0), (110.0, 392.0))
TRAY_RIGHT = ((290.0, 265.0), (290.0, 392.0))
FLOOR_LEFT = ((4.0, 386.0), (200.0, 393.0))
FLOOR_RIGHT = ((200.0, 393.0), (396.0, 386.0))

# The swallow box covers the L0 aperture. Its sloped ceiling catches
# upward-angled arrivals and guides them inside; the floor drags balls to the
# back wall, whose contact means the ball is wholly inside the silhouette.
SWALLOW_CEILING = ((4.0, 29.0), (55.0, 37.0))
SWALLOW_BACK = ((55.0, 37.0), (55.0, 167.0))
SWALLOW_FLOOR = ((4.0, 167.0), (55.0, 167.0))

# The exit box just left of R0 emits swallowed balls through the exit band.
EXIT_CEILING = ((345.0, 232.0), (396.0, 232.0))
EXIT_BACK = ((345.0, 232.0), (345.0, 378.0))
EXIT_FLOOR = ((345.0, 330.0), (396.0, 330.0))
EXIT_BOTTOM = ((345.0, 378.0), (396.0, 378.0))
EXIT_SPAWN = (368.0, 311.0)
# Fast enough that free fall past the floor lip keeps the R0 exit within the
# 30 degree port cone when the ball is classified outside the edge.
EXIT_VELOCITY = (280.0, 0.0)
# Solid foreground plates occlude the box interiors: the swallowed ball is
# fully hidden before it teleports, and the emerged ball stays hidden until
# it rolls out from behind the exit plate.
SWALLOW_PLATE = (2.0, 24.0, 57.0, 176.0)
EXIT_PLATE = (339.0, 226.0, 397.0, 384.0)

# Edge guards seal everything except the two port apertures. The top guards
# stop 6 units short of the T0 cone; the remaining gaps are narrower than a
# mini is wide. The right guard splits around the exit box.
GUARD_LEFT = ((4.0, 174.0), (4.0, 392.0))
GUARD_RIGHT_TOP = ((396.0, 4.0), (396.0, 232.0))
GUARD_RIGHT_BOTTOM = ((396.0, 382.0), (396.0, 392.0))
GUARD_CORNER = ((4.0, 4.0), (4.0, 30.0))
GUARD_TOP_LEFT = ((4.0, 4.0), (135.0, 4.0))
GUARD_TOP_RIGHT = ((265.0, 4.0), (396.0, 4.0))

# Minis straying this close to an edge are dropped back into the tray; the
# port bands must stay physically open, so this invisible backstop covers
# them. Real balls touching the floor or guards are tossed back into the
# bowl instead: the frame is lava.
MINI_EDGE_MARGIN = 30.0
BALL_RETURN_POINT = (200.0, 60.0)

MINI_RADIUS = 5.0
MINI_DENSITY = 0.002
MINI_MAX_SPEED = 470.0
MAX_MINIS = 70
# Deterministic shatter sizes, averaging 7 minis per ball.
MINI_COUNTS = (6, 7, 8, 9, 7, 6, 8, 5)

BLAST_RAYS = 8
BLAST_SECONDS = 0.35
FLASH_SECONDS = 0.15

WALL = (49, 90, 168, 255)
TRAY = (115, 76, 168, 255)
SPOKE_FILL = (198, 40, 30, 255)
SPOKE_FLASH = (255, 120, 60, 255)
SPOKE_STROKE = (110, 20, 15, 255)
HUB_FILL = (58, 64, 76, 255)
HUB_STROKE = (30, 33, 40, 255)
MINI_FILL = (96, 165, 250, 255)
MINI_STROKE = (37, 99, 235, 255)
PLATE_STROKE = (70, 46, 104, 255)
RAY = (255, 150, 45, 230)
NO_RAY = (255, 150, 45, 0)


class FunnelShredder(TileBase):
    """T0 falls into a funnel where a spiked wheel shreds balls into small
    balls raining into a catch tray; L0 balls roll into a teleport box and
    re-emerge from a matching box at R0. Stage 1: no B0 output yet."""

    author = "Pi"
    enabled = False

    def build(self, b: TileBuilder) -> None:
        self.pending = {}
        self.returning = set()
        self.swallowed = set()
        self.stockpile = []
        self.minis = []
        self.mini_pool = []
        self.shatters = 0
        self.blast_t = 0.0
        self.blast_center = WHEEL
        self.flash_t = 0.0

        # The spiked wheel: a kinematic hub with spoke segments. Kinematic
        # bodies pass through static walls, so the spoke reach must stay clear
        # of the bowl walls; the reach still provably blocks every ball path
        # to the throat (see the geometry note above).
        self.wheel = b.kinematic_body(WHEEL)
        self.wheel.set_angular_velocity(WHEEL_RATE)
        self.spokes = []
        for i in range(SPOKES):
            angle = i * math.tau / SPOKES
            c, s = math.cos(angle), math.sin(angle)
            spoke = b.segment_shape(
                self.wheel,
                (SPOKE_INNER * c, SPOKE_INNER * s),
                (SPOKE_OUTER * c, SPOKE_OUTER * s),
                SPOKE_RADIUS,
                density=0.01,
                friction=0.2,
                elasticity=0.4,
                fill_color=SPOKE_FILL,
                stroke_color=SPOKE_STROKE,
            )
            self.spokes.append(spoke)
        hub = b.circle_shape(
            self.wheel, (0, 0), HUB_RADIUS,
            density=0.01, friction=0.1, elasticity=0.4,
            fill_color=HUB_FILL, stroke_color=HUB_STROKE,
        )

        def catch_ball(event):
            self.pending[event.ball] = event.point
            return False  # The wheel grabs the ball instead of bouncing it.

        for spoke in self.spokes:
            b.on_ball_contact(spoke, begin=catch_ball)
        b.on_ball_contact(hub, begin=catch_ball)

        def return_ball(event):
            ball = event.ball
            if ball not in self.pending:
                self.returning.add(ball)

        # Funnel bowl, throat chute, catch tray and a full-width safety floor.
        # Walls are radius 4 so a speed-capped mini can never tunnel. Bowl
        # walls are nearly dead so incoming balls slide in instead of
        # bouncing back out through the open sides.
        for a, end in (BOWL_LEFT, BOWL_RIGHT):
            b.static_segment(a, end, 4, friction=0.05, elasticity=0.05,
                             fill_color=WALL)
        for a, end in (CHUTE_LEFT, CHUTE_RIGHT):
            b.static_segment(a, end, 4, friction=0.05, elasticity=0.2,
                             fill_color=WALL)
        for a, end in (TRAY_LEFT, TRAY_RIGHT):
            b.static_segment(a, end, 4, friction=0.5, elasticity=0.15,
                             fill_color=TRAY)
        lava = (FLOOR_LEFT, FLOOR_RIGHT, GUARD_LEFT, GUARD_RIGHT_TOP,
                GUARD_RIGHT_BOTTOM, GUARD_CORNER, GUARD_TOP_LEFT,
                GUARD_TOP_RIGHT)
        for a, end in lava:
            shape = b.static_segment(a, end, 4, friction=0.6, elasticity=0.2,
                                     fill_color=TRAY)
            b.on_ball_contact(shape, begin=return_ball)

        # The swallow box at L0: the sloped ceiling catches upward-angled
        # arrivals, the floor drags balls to the back wall, and back-wall
        # contact swallows them.
        b.static_segment(*SWALLOW_CEILING, 4, friction=0.1, elasticity=0.1,
                         fill_color=TRAY)
        b.static_segment(*SWALLOW_FLOOR, 4, friction=0.1, elasticity=0.1,
                         surface_velocity=(50.0, 0.0), fill_color=TRAY)
        back = b.static_segment(*SWALLOW_BACK, 4, friction=0.1, elasticity=0.1,
                                fill_color=TRAY)

        def swallow_ball(event):
            self.swallowed.add(event.ball)
            return False  # The wall absorbs the ball instead of bouncing it.

        b.on_ball_contact(back, begin=swallow_ball)
        b.visual_box(*SWALLOW_PLATE, fill_color=TRAY, stroke_color=PLATE_STROKE,
                     foreground=True)

        # The exit box just left of R0: a false-bottom crate whose floor
        # carries emerged balls out through the exit band.
        b.static_segment(*EXIT_CEILING, 4, friction=0.1, elasticity=0.1,
                         fill_color=TRAY)
        b.static_segment(*EXIT_BACK, 4, friction=0.1, elasticity=0.1,
                         fill_color=TRAY)
        b.static_segment(*EXIT_FLOOR, 4, friction=0.1, elasticity=0.1,
                         surface_velocity=(280.0, 0.0), fill_color=TRAY)
        b.static_segment(*EXIT_BOTTOM, 4, friction=0.1, elasticity=0.1,
                         fill_color=TRAY)
        b.visual_box(*EXIT_PLATE, fill_color=TRAY, stroke_color=PLATE_STROKE,
                     foreground=True)

        # The mini pool: pre-created paused bodies. Creating bodies mid-run
        # would not emit scene events, so the web renderer would never show
        # them; pause/resume of pooled bodies does emit and renders correctly.
        for _ in range(MAX_MINIS):
            body = b.dynamic_body(WHEEL)
            b.circle_shape(
                body, (0, 0), MINI_RADIUS,
                density=MINI_DENSITY, friction=0.35, elasticity=0.35,
                fill_color=MINI_FILL, stroke_color=MINI_STROKE,
            )
            body.pause()
            self.mini_pool.append(body)

        # Shatter flash: a short starburst, hidden until a ball breaks.
        self.rays = [
            b.visual_segment(WHEEL, WHEEL, 3.5,
                             fill_color=NO_RAY, stroke_color=NO_RAY, dynamic=True)
            for _ in range(BLAST_RAYS)
        ]

    def update(self, b: TileBuilder, dt: float) -> None:
        for ball in tuple(self.swallowed):
            self.swallowed.discard(ball)
            try:
                ball.pause()
                ball.set_position(EXIT_SPAWN)
                ball.set_velocity(EXIT_VELOCITY)
                ball.resume()
            except (PermissionError, ValueError, RuntimeError):
                continue
        for ball in tuple(self.returning):
            self.returning.discard(ball)
            try:
                if not ball.paused:
                    ball.set_position(BALL_RETURN_POINT)
                    ball.set_velocity((0.0, 120.0))
            except (PermissionError, ValueError):
                pass
        if self.pending:
            pending = list(self.pending.items())
            self.pending.clear()
            for ball, point in pending:
                self.returning.discard(ball)
                try:
                    position = ball.position
                    ball.pause()
                except (PermissionError, ValueError, RuntimeError):
                    continue
                self.stockpile.append(ball)
                self._shatter(position)
                # One flash per frame even when several balls break at once.
                self.blast_center = point or position
                self.blast_t = BLAST_SECONDS
                self.flash_t = FLASH_SECONDS
                for spoke in self.spokes:
                    spoke.set_fill_color(SPOKE_FLASH)
        if self.flash_t > 0:
            self.flash_t = max(0.0, self.flash_t - dt)
            if self.flash_t == 0:
                for spoke in self.spokes:
                    spoke.set_fill_color(SPOKE_FILL)
        if self.blast_t > 0:
            self.blast_t = max(0.0, self.blast_t - dt)
            self._draw_blast()
        for body in self.minis:
            x, y = body.position
            if x < MINI_EDGE_MARGIN or (x > 375 and y < 370) or y < 20:
                body.set_position((200.0, 320.0))
                body.set_velocity((0.0, 0.0))
                body.set_angular_velocity(0.0)
                continue
            vx, vy = body.velocity
            squared = vx * vx + vy * vy
            # Minis are tile-owned bodies, so the engine ball speed cap does
            # not cover them; cap here to keep walls tunnel-proof at 60 Hz.
            if squared > MINI_MAX_SPEED * MINI_MAX_SPEED:
                scale = MINI_MAX_SPEED / math.sqrt(squared)
                body.set_velocity((vx * scale, vy * scale))

    def _shatter(self, position: tuple[float, float]) -> None:
        count = MINI_COUNTS[self.shatters % len(MINI_COUNTS)]
        n = self.shatters
        self.shatters += 1
        rx, ry = position[0] - WHEEL[0], position[1] - WHEEL[1]
        for k in range(count):
            angle = k * 2.399963 + n * 0.7  # Golden-angle spread, per-shatter phase.
            dx, dy = math.cos(angle), math.sin(angle)
            speed = 70 + 35 * ((k * 37 + n * 11) % 5)
            # Part of the wheel's surface velocity at the contact: the spokes
            # fling the fresh minis.
            kick = 0.35 * WHEEL_RATE
            self._spawn_mini(
                (position[0] + 10 * dx, position[1] + 10 * dy),
                (dx * speed - kick * ry, dy * speed + kick * rx),
            )

    def _spawn_mini(self, position, velocity) -> None:
        body = self._take_mini()
        body.set_position((
            min(392.0, max(8.0, position[0])),
            min(392.0, max(8.0, position[1])),
        ))
        body.set_velocity(velocity)
        body.set_angle(0.0)
        body.set_angular_velocity(0.0)
        body.resume()
        self.minis.append(body)

    def _take_mini(self):
        if self.mini_pool:
            return self.mini_pool.pop()
        # Pool exhausted: recycle a stray mini resting outside the tray first
        # (they are the visual mess), then the calmest one in the tray pile.
        def score(body):
            x, y = body.position
            in_tray = 1 if (110 <= x <= 290 and y > 265) else 0
            vx, vy = body.velocity
            return (in_tray, vx * vx + vy * vy)

        body = min(self.minis, key=score)
        self.minis.remove(body)
        body.pause()
        return body

    def _draw_blast(self) -> None:
        if self.blast_t <= 0:
            for ray in self.rays:
                ray.set_fill_color(NO_RAY)
            return
        progress = 1 - self.blast_t / BLAST_SECONDS
        inner = 6 + 22 * progress
        outer = 14 + 34 * progress
        alpha = int(RAY[3] * (1 - progress))
        cx, cy = self.blast_center
        for i, ray in enumerate(self.rays):
            theta = i * math.tau / BLAST_RAYS + (i * 0.6180339887) % 0.6 - 0.3
            ux, uy = math.cos(theta), math.sin(theta)
            ray.set_segment_points(
                _clamp((cx + inner * ux, cy + inner * uy)),
                _clamp((cx + outer * ux, cy + outer * uy)),
            )
            ray.set_fill_color((RAY[0], RAY[1], RAY[2], alpha))


def _clamp(point):
    return (
        min(396.0, max(4.0, point[0])),
        min(396.0, max(4.0, point[1])),
    )
