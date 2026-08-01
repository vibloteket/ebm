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

        def distribute(event):
            body = event.ball_body
            if getattr(body, "ebm_flow_origin", None) != origin:
                body.ebm_flow_origin = origin
                body.ebm_flow_output = outputs[self.next_output]
                self.next_output = (self.next_output + 1) % len(outputs)
            _steer(body, origin, body.ebm_flow_output)

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


def _steer(body, origin, output):
    ox, oy = origin
    x, y = float(body.position.x - ox), float(body.position.y - oy)
    if output == Port.B0:
        error = 100 - x
        body.velocity = (max(-220, min(220, error * 5)), 45 if abs(error) > 24 else max(140, min(280, float(body.velocity.y) + 14)))
    elif output == Port.L1:
        error = 150 - y
        body.velocity = (max(-120, min(120, (100 - x) * 4)) if abs(error) > 24 else min(-140, max(-280, float(body.velocity.x) - 14)), max(-220, min(220, error * 5)))
    else:
        error = 50 - y
        body.velocity = (max(-120, min(120, (100 - x) * 4)) if abs(error) > 24 else max(140, min(280, float(body.velocity.x) + 14)), max(-220, min(220, error * 5)))


TILE_CLASS = PoweredChannelTile
