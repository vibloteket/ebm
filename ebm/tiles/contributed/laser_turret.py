from __future__ import annotations

import math

from ebm import TileBase, TileBuilder

TURRET = (280.0, 280.0)
SENSOR_CENTER = (160.0, 160.0)
SENSOR_RADIUS = 125.0
# Only fire at targets well inside the zone; boundary grazers may escape.
FIRE_DEPTH = 200.0
BARREL_LENGTH = 34.0
MUZZLE = 28.0
AIM_SECONDS = 0.25
COOLDOWN_SECONDS = 0.05
BEAM_SECONDS = 0.12
BLAST_SECONDS = 0.45
BLAST_RAYS = 10
RING_SEGMENTS = 48

STEEL = (58, 64, 76, 255)
STEEL_DARK = (30, 33, 40, 255)
EYE = (198, 40, 30, 255)
RING = (215, 60, 48, 46)
RING_FLASH = (215, 60, 48, 150)
NO_RING = (215, 60, 48, 0)
BEAM_CORE = (255, 238, 130, 235)
BEAM_GLOW = (255, 90, 40, 120)
NO_BEAM = (255, 90, 40, 0)
RAY = (255, 150, 45, 230)
NO_RAY = (255, 150, 45, 0)


class LaserTurret(TileBase):
    """A turret tracks balls inside its sensor circle and shoots them; hit balls explode."""

    author = "Pi"
    # Exploded balls never reach an output, which breaks the flow contract
    # until the output respawn mechanism exists. Editor-only until then.
    enabled = False

    def build(self, b: TileBuilder) -> None:
        self.queue = []
        self.target = None
        self.aim = 0.0
        self.cooldown = 0.0
        self.beam_t = 0.0
        self.blast_t = 0.0
        self.blast_center = TURRET
        self.flash_t = 0.0
        self.angle = math.atan2(
            SENSOR_CENTER[1] - TURRET[1], SENSOR_CENTER[0] - TURRET[0]
        )

        sensor = b.sensor_circle(SENSOR_CENTER, SENSOR_RADIUS)

        # Danger-zone ring: a thin translucent outline of the sensor circle.
        self.ring = [
            b.visual_segment(
                (
                    SENSOR_CENTER[0] + SENSOR_RADIUS * math.cos(i * math.tau / RING_SEGMENTS),
                    SENSOR_CENTER[1] + SENSOR_RADIUS * math.sin(i * math.tau / RING_SEGMENTS),
                ),
                (
                    SENSOR_CENTER[0] + SENSOR_RADIUS * math.cos((i + 1) * math.tau / RING_SEGMENTS),
                    SENSOR_CENTER[1] + SENSOR_RADIUS * math.sin((i + 1) * math.tau / RING_SEGMENTS),
                ),
                1.5,
                fill_color=RING,
                stroke_color=NO_RING,
            )
            for i in range(RING_SEGMENTS)
        ]

        # The physical turret: balls bounce off its base just outside the zone.
        b.static_circle(TURRET, 19, friction=0.3, elasticity=0.6,
                        fill_color=STEEL, stroke_color=STEEL_DARK)
        b.static_circle(TURRET, 7.5, friction=0.3, elasticity=0.6,
                        fill_color=EYE, stroke_color=STEEL_DARK)

        # Barrel, beam and blast rays are dynamic visuals, hidden until used.
        self.barrel = b.visual_segment(
            TURRET, self._tip(self.angle, BARREL_LENGTH), 5,
            fill_color=STEEL, stroke_color=STEEL_DARK, dynamic=True,
        )
        self.beam = b.visual_segment(
            TURRET, TURRET, 3,
            fill_color=NO_BEAM, stroke_color=NO_BEAM, dynamic=True,
        )
        self.rays = [
            b.visual_segment(TURRET, TURRET, 3.5,
                             fill_color=NO_RAY, stroke_color=NO_RAY, dynamic=True)
            for _ in range(BLAST_RAYS)
        ]

        def enter(event):
            ball = event.ball
            if ball is not self.target and ball not in self.queue:
                self.queue.append(ball)

        def leave(event):
            ball = event.ball
            if ball in self.queue:
                self.queue.remove(ball)
            if ball is self.target:
                self.target = None

        b.on_ball_contact(sensor, begin=enter, separate=leave)

    def update(self, _b: TileBuilder, dt: float) -> None:
        if self.beam_t > 0:
            self.beam_t = max(0.0, self.beam_t - dt)
            if self.beam_t == 0:
                self.beam.set_fill_color(NO_BEAM)
                self.beam.set_stroke_color(NO_BEAM)
        if self.flash_t > 0:
            self.flash_t = max(0.0, self.flash_t - dt)
            if self.flash_t == 0:
                for segment in self.ring:
                    segment.set_fill_color(RING)
        if self.blast_t > 0:
            self.blast_t = max(0.0, self.blast_t - dt)
            self._draw_blast()
        self.cooldown = max(0.0, self.cooldown - dt)

        if self.target is None:
            while self.queue:
                candidate = self.queue.pop(0)
                try:
                    candidate.position
                except PermissionError:
                    continue
                self.target = candidate
                self.aim = AIM_SECONDS
                break
        if self.target is not None:
            try:
                position = self.target.position
            except PermissionError:
                self.target = None
            else:
                self.angle = math.atan2(
                    position[1] - TURRET[1], position[0] - TURRET[0]
                )
                self.aim -= dt
                if self.aim <= 0 and self.cooldown == 0 and _distance(position, SENSOR_CENTER) <= FIRE_DEPTH:
                    self._fire(position)
        self.barrel.set_segment_points(TURRET, self._tip(self.angle, BARREL_LENGTH))

    def _fire(self, position) -> None:
        ball = self.target
        self.target = None
        self.cooldown = COOLDOWN_SECONDS
        muzzle = self._tip(self.angle, MUZZLE)
        self.beam.set_segment_points(muzzle, position)
        self.beam.set_fill_color(BEAM_CORE)
        self.beam.set_stroke_color(BEAM_GLOW)
        self.beam_t = BEAM_SECONDS
        self.blast_center = position
        self.blast_t = BLAST_SECONDS
        self._draw_blast()
        for segment in self.ring:
            segment.set_fill_color(RING_FLASH)
        self.flash_t = 0.25
        # The explosion destroys the ball: it leaves physics and rendering but
        # stays owned, ready to be respawned at an output later.
        ball.pause()

    def _draw_blast(self) -> None:
        if self.blast_t <= 0:
            for ray in self.rays:
                ray.set_fill_color(NO_RAY)
            return
        progress = 1 - self.blast_t / BLAST_SECONDS
        inner = 8 + 26 * progress
        outer = 16 + 40 * progress
        alpha = int(RAY[3] * (1 - progress))
        cx, cy = self.blast_center
        for i, ray in enumerate(self.rays):
            # Fixed golden-angle jitter keeps the starburst deterministic.
            theta = i * math.tau / BLAST_RAYS + (i * 0.6180339887) % 0.6 - 0.3
            ux, uy = math.cos(theta), math.sin(theta)
            ray.set_segment_points(
                _clamp((cx + inner * ux, cy + inner * uy)),
                _clamp((cx + outer * ux, cy + outer * uy)),
            )
            ray.set_fill_color((RAY[0], RAY[1], RAY[2], alpha))

    @staticmethod
    def _tip(angle: float, length: float):
        return TURRET[0] + length * math.cos(angle), TURRET[1] + length * math.sin(angle)


def _distance(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _clamp(point):
    return (
        min(396.0, max(4.0, point[0])),
        min(396.0, max(4.0, point[1])),
    )
