import math

from ebm import TileBase, TileBuilder, Vec2d

TURRET = Vec2d(280.0, 280.0)
SENSOR_CENTER = Vec2d(160.0, 160.0)
SENSOR_RADIUS = 130.0
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

# Recycled supply: exploded balls are paused into an invisible stockpile. The
# first wave needs PRIME_STOCK balls; later waves fire every WAVE_SECONDS when
# at least WAVE_COST balls remain, otherwise the supply must re-prime.
WAVE_SECONDS = 2.5
PRIME_STOCK = 3
WAVE_COST = 2

# B0 spawner: a box just above the exit. A recycled ball fades in on the
# closed hatch; when fully visible the hatch opens and the ball drops out.
BOX_SPAWN = (225.0, 370.0)
BOX_FADE_SECONDS = 0.9
BOX_OPEN_SECONDS = 0.3

# R0 spawner: a one-ball-wide pipe from the tile top down to a sliding
# shuttle at y~240. The shuttle carries the bottom ball sideways and drops it
# onto a triangle that bounces it out through R0. The shuttle releases one
# ball per wave, but only while the pipe is full.
PIPE_X = 337.0
PIPE_CAPACITY = 6
PIPE_TOP_SPAWN = (337.0, 25.0)
PIPE_CLEAR_Y = 55.0
SHUTTLE_HOME_X = 337.0
SHUTTLE_DROP_X = 373.0
SHUTTLE_SPEED = 120.0
SHUTTLE_DROP_SECONDS = 0.25
SHUTTLE_REFILL_SECONDS = 0.25
BALL_FILL = (22, 114, 212, 255)
BALL_STROKE = (12, 63, 143, 255)

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
CRATE = (115, 76, 168, 255)
MECH = (220, 140, 35, 255)
PIPE = (49, 90, 168, 255)

class LaserTurret(TileBase):
    """A turret tracks balls inside its sensor circle and shoots them; hit balls
    explode and are recycled into the B0 spawn box and the R0 pipe, which release
    them in synchronized clock-driven waves."""

    author = "Pi"
    enabled = True

    def build(self, b: TileBuilder) -> None:
        self.queue = []
        self.target = None
        self.aim = 0.0
        self.cooldown = 0.0
        self.beam_t = 0.0
        self.blast_t = 0.0
        self.blast_center = TURRET
        self.flash_t = 0.0
        self.angle = (SENSOR_CENTER - TURRET).angle
        self.stockpile = []
        self.primed = False
        self.wave_t = 0.0
        self.box_ball = None
        self.box_t = 0.0
        self.hatch_open = False
        self.hatch_t = 0.0
        self.pipe_balls = []
        self.pending_spawn = []
        self.shuttle_phase = "home"
        self.shuttle_t = 0.0

        sensor = b.sensor_circle(SENSOR_CENTER, SENSOR_RADIUS)

        # Danger-zone ring: a thin translucent outline of the sensor circle.
        ring_points = [
            SENSOR_CENTER + Vec2d(SENSOR_RADIUS, 0).rotated(i * math.tau / RING_SEGMENTS)
            for i in range(RING_SEGMENTS + 1)
        ]
        self.ring = [
            b.visual_segment(a, end, 1.5, fill_color=RING, stroke_color=NO_RING)
            for a, end in zip(ring_points, ring_points[1:])
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

        # B0 spawner: an open-topped box whose floor is a pausable hatch.
        b.static_segment((195, 345), (195, 391), 3, friction=0, elasticity=0,
                         fill_color=CRATE)
        b.static_segment((255, 345), (255, 391), 3, friction=0, elasticity=0,
                         fill_color=CRATE)
        self.hatch = b.static_segment((198, 388), (252, 388), 3,
                                      friction=0.2, elasticity=0, fill_color=MECH)

        # R0 spawner: a one-ball-wide pipe from the top edge down to the
        # shuttle channel. The right wall has a slot at channel height.
        b.static_segment((318, 8), (318, 258), 3, friction=0.05, elasticity=0,
                         fill_color=PIPE)
        b.static_segment((356, 8), (356, 218), 3, friction=0.05, elasticity=0,
                         fill_color=PIPE)
        b.static_segment((356, 218), (396, 218), 3, friction=0.05, elasticity=0,
                         fill_color=PIPE)
        b.static_segment((320, 258), (354, 258), 3, friction=0.05, elasticity=0,
                         fill_color=PIPE)

        # The shuttle: a sliding holder with a ball-sized gap. At home the gap
        # aligns with the pipe bore; slid right it carries the bottom ball over
        # the drop slot while its top plate blocks the column above.
        self.shuttle = b.kinematic_body((SHUTTLE_HOME_X, 240))
        b.segment_shape(self.shuttle, (-18, -12), (-18, 12), 2,
                        friction=0.05, elasticity=0, fill_color=MECH)
        b.segment_shape(self.shuttle, (18, -12), (18, 12), 2,
                        friction=0.05, elasticity=0, fill_color=MECH)
        b.segment_shape(self.shuttle, (-18, -14), (18, -14), 2,
                        friction=0.05, elasticity=0, fill_color=MECH)

        # The triangle bounces the dropped ball out through R0.
        b.static_polygon(((283, 335), (340, 285), (397, 335)),
                         friction=0.05, elasticity=0.85, fill_color=CRATE)

        # Near-stationary L0 arrivals hug the left wall and slide past the
        # sensor's leftmost reach by half a unit. A small ledge inside the
        # kill zone catches them; the turret recycles them like the rest.
        b.static_segment((3, 150), (60, 165), 3, friction=0.05, elasticity=0)

        def enter(event):
            ball = event.ball
            if ball != self.target and ball not in self.queue:
                self.queue.append(ball)

        def leave(event):
            ball = event.ball
            if ball in self.queue:
                self.queue.remove(ball)
            if ball == self.target:
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
                self.angle = (position - TURRET).angle
                self.aim -= dt
                if self.aim <= 0 and self.cooldown == 0 and position.get_distance(SENSOR_CENTER) <= FIRE_DEPTH:
                    self._fire(position)
        self.barrel.set_segment_points(TURRET, self._tip(self.angle, BARREL_LENGTH))
        wave_fired = self._update_supply(dt)
        self._update_box(dt)
        self._update_pipe(dt, wave_fired)

    def _update_supply(self, dt: float) -> bool:
        """Advance the shared wave clock; return True when a wave fired."""
        self._prune(self.stockpile)
        if not self.primed:
            if len(self.stockpile) >= PRIME_STOCK:
                self.primed = True
                self.wave_t = 0.0
            else:
                return False
        self.wave_t -= dt
        if self.wave_t > 0:
            return False
        if len(self.stockpile) < WAVE_COST:
            self.primed = False
            return False
        self.wave_t = WAVE_SECONDS
        self._box_start(self.stockpile.pop(0))
        self.pending_spawn.append(self.stockpile.pop(0))
        return True

    def _box_start(self, ball) -> None:
        ball.set_position(BOX_SPAWN)
        ball.set_velocity((0, 0))
        ball.set_fill_color(BALL_FILL[:3] + (0,))
        ball.set_stroke_color(BALL_STROKE[:3] + (0,))
        ball.resume()
        self.box_ball = ball
        self.box_t = 0.0

    def _update_box(self, dt: float) -> None:
        if self.box_ball is not None and not self.hatch_open:
            self.box_t += dt
            if self.box_t >= BOX_FADE_SECONDS:
                self.hatch.pause()
                self.hatch_open = True
                self.hatch_t = 0.0
            else:
                alpha = int(255 * self.box_t / BOX_FADE_SECONDS)
                try:
                    self.box_ball.set_fill_color(BALL_FILL[:3] + (alpha,))
                    self.box_ball.set_stroke_color(BALL_STROKE[:3] + (alpha,))
                except PermissionError:
                    self.box_ball = None
        if self.hatch_open:
            self.hatch_t += dt
            if self.hatch_t >= BOX_OPEN_SECONDS:
                self.hatch.resume()
                self.hatch_open = False
                self.box_ball = None

    def _update_pipe(self, dt: float, wave_fired: bool) -> None:
        self._prune(self.pipe_balls)
        if self.pending_spawn:
            top_clear = True
            for ball in self.pipe_balls:
                try:
                    if ball.position[1] < PIPE_CLEAR_Y:
                        top_clear = False
                        break
                except PermissionError:
                    pass
            if top_clear:
                ball = self.pending_spawn.pop(0)
                ball.set_position(PIPE_TOP_SPAWN)
                ball.set_velocity((0, 0))
                ball.resume()
                self.pipe_balls.append(ball)
        if (
            wave_fired
            and self.shuttle_phase == "home"
            and len(self.pipe_balls) >= PIPE_CAPACITY
        ):
            self.shuttle_phase = "carry"
            self.shuttle.set_velocity((SHUTTLE_SPEED, 0))
            self.pipe_balls.pop(0)
        x = self.shuttle.position[0]
        if self.shuttle_phase == "carry" and x >= SHUTTLE_DROP_X:
            self.shuttle.set_velocity((0, 0))
            self.shuttle_phase = "drop"
            self.shuttle_t = SHUTTLE_DROP_SECONDS
        elif self.shuttle_phase == "drop":
            self.shuttle_t -= dt
            if self.shuttle_t <= 0:
                self.shuttle_phase = "return"
                self.shuttle.set_velocity((-SHUTTLE_SPEED, 0))
        elif self.shuttle_phase == "return" and x <= SHUTTLE_HOME_X:
            self.shuttle.set_velocity((0, 0))
            self.shuttle_phase = "refill"
            self.shuttle_t = SHUTTLE_REFILL_SECONDS
        elif self.shuttle_phase == "refill":
            self.shuttle_t -= dt
            if self.shuttle_t <= 0:
                self.shuttle_phase = "home"

    @staticmethod
    def _prune(balls) -> None:
        kept = []
        for ball in balls:
            try:
                ball.position
            except PermissionError:
                continue
            kept.append(ball)
        balls[:] = kept

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
        # stays owned in the invisible stockpile, ready to be recycled into an
        # output spawner by the next wave.
        ball.pause()
        self.stockpile.append(ball)

    def _draw_blast(self) -> None:
        if self.blast_t <= 0:
            for ray in self.rays:
                ray.set_fill_color(NO_RAY)
            return
        progress = 1 - self.blast_t / BLAST_SECONDS
        inner = 8 + 26 * progress
        outer = 16 + 40 * progress
        alpha = int(RAY[3] * (1 - progress))
        center = self.blast_center
        for i, ray in enumerate(self.rays):
            # Fixed golden-angle jitter keeps the starburst deterministic.
            theta = i * math.tau / BLAST_RAYS + (i * 0.6180339887) % 0.6 - 0.3
            direction = Vec2d(1, 0).rotated(theta)
            ray.set_segment_points(
                _clamp(center + direction * inner),
                _clamp(center + direction * outer),
            )
            ray.set_fill_color((RAY[0], RAY[1], RAY[2], alpha))

    @staticmethod
    def _tip(angle: float, length: float):
        return TURRET + Vec2d(length, 0).rotated(angle)

def _clamp(point):
    return (
        min(396.0, max(4.0, point[0])),
        min(396.0, max(4.0, point[1])),
    )
