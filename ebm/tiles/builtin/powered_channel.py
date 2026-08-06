from __future__ import annotations

from ebm import Port, TileBase


class PoweredChannelTile(TileBase):
    """Flow tile that distributes incoming balls across all three outputs."""

    id = "ebm.powered-channel"
    title = "Physical Channel"
    author = "EBM"
    api_version = 2

    def build(self, builder) -> None:
        sensor = builder.sensor_box(7.75, 7.75, 192.25, 192.25)
        origin = builder.origin
        outputs = (Port.B0, Port.L1, Port.R1)
        self.next_output = 0
        self.ball_outputs = {}

        def distribute(event):
            ball = event.ball
            output = self.ball_outputs.get(ball)
            if output is None:
                output = outputs[self.next_output]
                self.ball_outputs[ball] = output
                self.next_output = (self.next_output + 1) % len(outputs)
            _steer(ball, output)

        builder.on_ball_contact(sensor, distribute)
        for entry, output in zip((Port.T0, Port.L0, Port.R0), outputs):
            builder.visual_segment(_inside(entry), _inside(output), 3)

    def update(self, _builder, _dt):
        pass


def _inside(port: Port):
    x, y = port.point
    if port == Port.T0: return x, y + 10
    if port == Port.B0: return x, y - 10
    if port in (Port.L0, Port.L1): return x + 10, y
    return x - 10, y


def _steer(ball, output):
    x, y = ball.position
    vx, vy = ball.velocity
    if output == Port.B0:
        error = 100 - x
        velocity = (max(-220, min(220, error * 5)), 45 if abs(error) > 24 else max(140, min(280, vy + 14)))
    elif output == Port.L1:
        error = 150 - y
        velocity = (max(-120, min(120, (100 - x) * 4)) if abs(error) > 24 else min(-140, max(-280, vx - 14)), max(-220, min(220, error * 5)))
    else:
        error = 50 - y
        # Do not accelerate outward until the ball is centered inside R1's
        # aperture; otherwise high-offset entries can leave through bare edge.
        velocity = (max(-120, min(120, (100 - x) * 4)) if abs(error) > 12 else max(140, min(280, vx + 14)), max(-220, min(220, error * 5)))
    ball.set_velocity(velocity)


TILE_CLASS = PoweredChannelTile
