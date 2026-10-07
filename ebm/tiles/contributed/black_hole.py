import math

from ebm import TileBase, TileBuilder, Vec2d

# A black hole at the tile center. An invisible influence sensor tracks
# balls inside the zone; every frame each tracked ball gets a velocity
# nudge toward the hole (stronger as it gets closer, ~1/r) plus tangential
# damping so orbits decay into spirals. Capture is a distance check in
# update() — the ball pauses into the stockpile while fully occluded by
# the foreground disc, so no fade or color bookkeeping is needed.
#
# Conservation: stockpiled balls are resumed alternately near B0 and R0
# with an exit kick, paced by EMIT_SECONDS. Spawn points sit outside the
# influence zone so emitted balls are never re-captured.

HOLE = Vec2d(200.0, 200.0)
DISC_RADIUS = 34.0          # Visible black disc (foreground, occludes balls).
HORIZON = 18.0              # Capture distance; DISC > HORIZON + ball r (15).
R_INFLUENCE = 140.0         # Ports stay outside: R0 band is ~176 away.
PULL_AT_HORIZON = 8000.0    # accel u/s^2 at the horizon, falls off as 1/r.
TANGENT_KEEP = 0.98         # tangential keep-factor per 120 Hz frame.
MAX_SPEED = 700.0           # clamp inside the zone; prevents tunneling.
EMIT_SECONDS = 0.6

B0_SPAWN = Vec2d(200.0, 352.0)
B0_KICK = Vec2d(0.0, 260.0)
# R0 re-emit lands on a short powered floor; the kick matches its surface
# speed so the exit reads as the floor carrying the ball out (water-pool
# pattern). A free-floating spawn falls too far and exits over 30°.
R0_SPAWN = Vec2d(375.0, 312.0)
R0_KICK = Vec2d(340.0, 0.0)

HOLE_FILL = (8, 8, 12, 255)
GLOW = (120, 160, 255, 90)
ZONE = (120, 160, 255, 28)
RAIL = (49, 90, 168, 255)


class BlackHole(TileBase):
    """Sucks balls into a central black hole and re-emits them at the exits."""

    author = "Victor"
    enabled = False  # Editor-only while experimenting.

    def build(self, b: TileBuilder) -> None:
        self.captured = set()    # Balls currently inside the influence zone.
        self.stockpile = []      # Paused balls waiting to be re-emitted.
        self.next_exit = "b0"
        self.emit_t = 0.0

        sensor = b.sensor_circle(HOLE, R_INFLUENCE)

        def enter(event):
            self.captured.add(event.ball)

        def leave(event):
            self.captured.discard(event.ball)  # Also fires on pause; harmless.

        b.on_ball_contact(sensor, begin=enter, separate=leave)

        # Containment and guides. The floor's B0-sized gap turns downward
        # slingshot survivors into valid B0 exits; the ceiling keeps upward
        # ones in; the ledge pushes wall-hugging L0 entries into the zone.
        # All of it sits outside the influence zone, so guided balls are
        # never re-grabbed. The right side stays open for R0.
        b.static_segment((4, 397), (180, 397), 3,
                         friction=0.2, elasticity=0.05, fill_color=RAIL)
        b.static_segment((220, 397), (396, 397), 3,
                         friction=0.2, elasticity=0.05, fill_color=RAIL)
        b.static_segment((4, 3), (150, 3), 3,
                         friction=0.2, elasticity=0.05, fill_color=RAIL)
        b.static_segment((250, 3), (396, 3), 3,
                         friction=0.2, elasticity=0.05, fill_color=RAIL)
        b.static_segment((3, 150), (60, 165), 3,
                         friction=0.05, elasticity=0, fill_color=RAIL)
        # Corner guards: floor rollers turn back toward the B0 gap instead
        # of leaking out the bottom corners.
        b.static_segment((3, 168), (3, 394), 3,
                         friction=0.2, elasticity=0.05, fill_color=RAIL)
        b.static_segment((397, 350), (397, 396), 3,
                         friction=0.2, elasticity=0.05, fill_color=RAIL)
        # R0 re-emit floor: powered, so the emitted ball exits at conveyor
        # speed instead of falling past the 30° exit-angle limit.
        b.static_segment((340, 330), (397, 330), 3, friction=0.5,
                         elasticity=0.05, surface_velocity=(340, 0),
                         fill_color=RAIL)

        # The hole: a foreground disc occludes the actual capture point.
        disc = [
            HOLE + Vec2d(DISC_RADIUS, 0).rotated(i * math.tau / 28)
            for i in range(28)
        ]
        b.visual_polygon(disc, fill_color=HOLE_FILL, stroke_color=HOLE_FILL,
                         foreground=True)
        _ring(b, HOLE, DISC_RADIUS + 5, GLOW, foreground=True)
        _ring(b, HOLE, R_INFLUENCE, ZONE)

    def update(self, _b: TileBuilder, dt: float) -> None:
        keep = TANGENT_KEEP ** (dt * 120.0)
        for ball in tuple(self.captured):
            try:
                to_hole = HOLE - ball.position
                velocity = ball.velocity
            except PermissionError:
                self.captured.discard(ball)
                continue
            if ball.paused:
                self.captured.discard(ball)
                continue
            r = to_hole.length
            if r <= HORIZON or r < 1e-6:
                ball.pause()  # Fully behind the disc: the ball is gone.
                self.captured.discard(ball)
                self.stockpile.append(ball)
                continue
            # Split velocity into radial (toward the hole) and tangential
            # parts; pull the radial one, damp the tangential one so orbits
            # decay into spirals instead of circling forever.
            u = to_hole / r
            t = u.perpendicular()
            v_rad = velocity.dot(u) + (PULL_AT_HORIZON * HORIZON / r) * dt
            v_tan = velocity.dot(t) * keep
            v = u * v_rad + t * v_tan
            if v.length > MAX_SPEED:
                v = v.normalized() * MAX_SPEED
            ball.set_velocity(v)

        # Re-emit: strictly alternating, paced, outside the influence zone.
        self.emit_t -= dt
        if self.emit_t <= 0.0 and self.stockpile:
            ball = self.stockpile.pop(0)
            spawn, kick = (B0_SPAWN, B0_KICK) if self.next_exit == "b0" else (R0_SPAWN, R0_KICK)
            self.next_exit = "r0" if self.next_exit == "b0" else "b0"
            try:
                ball.set_position(spawn)
                ball.set_velocity(kick)
                ball.resume()
            except (PermissionError, ValueError, RuntimeError):
                pass
            self.emit_t = EMIT_SECONDS


def _ring(b, center, radius, color, *, foreground=False, segments=40):
    points = [
        center + Vec2d(radius, 0).rotated(i * math.tau / segments)
        for i in range(segments + 1)
    ]
    for a, end in zip(points, points[1:]):
        b.visual_segment(a, end, 2, fill_color=color, stroke_color=color,
                         foreground=foreground)
