"""Advisory live exit feedback using the validator's full-passage rules."""
import math

from .ports import TILE_SIZE, Port, right_neighbor, tile_origin
from .validator import classify_ball_state, _failure_message


class PreviewExitMonitor:
    def __init__(self, size=1):
        self.size = size
        self.tracked = {}
        self.failed = set()
        self.markers = []

    def add(self, body, row, col):
        self.tracked[body] = (row, col)

    def remove(self, body):
        self.tracked.pop(body, None)
        self.failed.discard(body)

    def advance(self, dt):
        for marker in self.markers:
            marker["remaining"] -= dt
        self.markers = [marker for marker in self.markers if marker["remaining"] > 0]

    def check(self, body, radius):
        if body not in self.tracked:
            return
        row, col = self.tracked[body]
        ox, oy = tile_origin(row, col)
        x, y = body.position.x - ox, body.position.y - oy
        vx, vy = body.velocity
        classification = classify_ball_state(x, y, vx, vy, radius)
        if classification is None:
            return
        status, label = classification
        if status == "exited":
            next_row, next_col = (row + 1, col) if label == Port.B0.name else right_neighbor(row, col)
            if 0 <= next_row < self.size and 0 <= next_col < self.size:
                self.tracked[body] = (next_row, next_col)
            else:
                self.tracked.pop(body)
            return
        self.tracked.pop(body)
        self.failed.add(body)
        message = _failure_message(status, label, x, y, vx, vy)
        text = message
        if label and label.startswith("bad-exit-angle:"):
            port = label.rsplit(":", 1)[1]
            outward = vy if port == "B0" else vx
            angle = math.degrees(math.acos(max(-1, min(1, outward / max(math.hypot(vx, vy), 1e-12)))))
            text = f"{port}: {angle:.1f}° > 30°"
        elif label in ("bottom", "right"):
            text = f"{'B0' if label == 'bottom' else 'R0'}: outside aperture"
        elif label in ("top", "left"):
            text = f"Invalid {label} exit"
        if not math.isfinite(x) or not math.isfinite(y):
            x, y = TILE_SIZE / 2, TILE_SIZE / 2
        self.markers.append({
            "x": ox + max(0, min(TILE_SIZE, x)),
            "y": oy + max(0, min(TILE_SIZE, y)),
            "text": text, "message": message, "row": row, "col": col,
            "remaining": 8.0,
        })
        self.markers = self.markers[-12:]
