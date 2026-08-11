from __future__ import annotations

from ebm import Port, TileBase


class PoweredChannelTile(TileBase):
    """Flow tile that distributes incoming balls across both outputs."""

    id = "ebm.powered-channel"
    title = "Physical Channel"
    author = "EBM"
    api_version = 1

    def build(self, builder) -> None:
        sensor = builder.sensor_box(15, 15, 385, 385)
        origin = builder.origin
        outputs = (Port.B0, Port.R0)
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

        builder.on_ball_contact(sensor, pre_solve=distribute)
        for entry, output in zip((Port.T0, Port.L0), outputs):
            builder.visual_segment(_inside(entry), _inside(output), 6)

    def update(self, _builder, _dt):
        pass


def _inside(port: Port):
    x, y = port.point
    if port == Port.T0: return x, y + 20
    if port == Port.B0: return x, y - 20
    if port == Port.L0: return x + 20, y
    return x - 20, y


def _steer(ball, output):
    x, y = ball.position
    vx, vy = ball.velocity
    if output == Port.B0:
        error = 200 - x
        velocity = (max(-440, min(440, error * 5)), 90 if abs(error) > 48 else max(280, min(560, vy + 28)))
    else:
        error = 300 - y
        # Do not accelerate outward until the ball is centered inside R0's
        # aperture; otherwise high-offset entries can leave through bare edge.
        velocity = (max(-240, min(240, (200 - x) * 4)) if abs(error) > 24 else max(280, min(560, vx + 28)), max(-440, min(440, error * 5)))
    ball.set_velocity(velocity)


TILE_CLASS = PoweredChannelTile
