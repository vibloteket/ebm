from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

TILE_SIZE = 200
MAX_EXIT_ANGLE_DEGREES = 30.0
# Representative speeds span the complete shared contract: almost stationary,
# ordinary flow, and the world's global speed cap.
ENTRY_TEST_SPEEDS = (1.0, 150.0, 300.0)
ENTRY_TEST_ANGLES = (-MAX_EXIT_ANGLE_DEGREES, 0.0, MAX_EXIT_ANGLE_DEGREES)


@dataclass(frozen=True)
class PortSpec:
    """Entry/exit tolerances for a port.

    For entry ports: these define the range of positions and velocities that
    balls from the previous tile may arrive with.  The tile must handle ALL
    values within these ranges.

    For exit ports: these define the range that the tile MUST NOT exceed when
    balls leave.  The next tile's entry spec is the mirror of this.
    """

    x_center: float
    y_center: float
    x_range: float
    y_range: float
    # Direction constraint on the component that must push the ball *out* of
    # the tile.  For B0/T0 it's vy_min (ball must go down); for L/R ports
    # it's vx_min with sign (ball must go left/right).
    vy_min: float
    vx_min: float
    # Entry velocity ranges — what the previous tile guarantees for incoming
    # balls.  These are deliberately narrower than the full-physics ranges a
    # tile might produce.
    entry_vx_range: float
    entry_vy_range: float
    # Exit velocity tolerances — what the current tile may produce.
    exit_vx_range: float
    exit_vy_range: float

    def sample_values(self):
        """Return a small, representative list of (pos_offset_x, pos_offset_y,
        vel_delta_vx, vel_delta_vy) tuples covering the min / mid / max of
        each entry range."""
        xs = (-self.x_range, 0.0, self.x_range)
        ys = (-self.y_range, 0.0, self.y_range)
        vxs = (-self.entry_vx_range, 0.0, self.entry_vx_range)
        vys = (-self.entry_vy_range, 0.0, self.entry_vy_range)
        samples: list[tuple[float, float, float, float]] = []
        for dx in xs:
            for dy in ys:
                for dvx in vxs:
                    for dvy in vys:
                        samples.append((dx, dy, dvx, dvy))
        return [xs, ys, vxs, vys], samples


# --- Port definitions ------------------------------------------------


class Port(Enum):
    # Input ports
    T0 = (100, 0)
    L0 = (0, 50)
    R0 = (200, 150)

    # Output ports
    B0 = (100, 200)
    L1 = (0, 150)
    R1 = (200, 50)

    @property
    def point(self) -> tuple[float, float]:
        x, y = self.value
        return float(x), float(y)


INPUT_PORTS = frozenset({Port.T0, Port.L0, Port.R0})
OUTPUT_PORTS = frozenset({Port.B0, Port.L1, Port.R1})

MIRROR_PORT = {
    Port.B0: Port.T0,
    Port.T0: Port.B0,
    Port.R1: Port.L0,
    Port.L0: Port.R1,
    Port.L1: Port.R0,
    Port.R0: Port.L1,
}

# Mirroring an exit spec gives the entry spec of its counterpart, and vice
# versa. This is the contract between successive tiles: what the tile above
# guarantees and what the tile below expects.
PORT_SPECS: dict[Port, PortSpec] = {
    Port.T0: PortSpec(
        x_center=100, y_center=0,
        x_range=25, y_range=4,
        vy_min=40, vx_min=0,
        entry_vx_range=40, entry_vy_range=25,
        exit_vx_range=60, exit_vy_range=999,
    ),
    Port.B0: PortSpec(
        x_center=100, y_center=200,
        x_range=25, y_range=4,
        vy_min=40, vx_min=0,
        entry_vx_range=40, entry_vy_range=25,
        exit_vx_range=60, exit_vy_range=999,
    ),
    Port.L0: PortSpec(
        x_center=0, y_center=50,
        x_range=4, y_range=20,
        vy_min=0, vx_min=40,
        entry_vx_range=25, entry_vy_range=30,
        exit_vx_range=40, exit_vy_range=200,
    ),
    Port.R1: PortSpec(
        x_center=200, y_center=50,
        x_range=4, y_range=20,
        vy_min=0, vx_min=40,
        entry_vx_range=25, entry_vy_range=30,
        exit_vx_range=40, exit_vy_range=200,
    ),
    Port.R0: PortSpec(
        x_center=200, y_center=150,
        x_range=4, y_range=20,
        vy_min=0, vx_min=40,
        entry_vx_range=25, entry_vy_range=30,
        exit_vx_range=40, exit_vy_range=200,
    ),
    Port.L1: PortSpec(
        x_center=0, y_center=150,
        x_range=4, y_range=20,
        vy_min=0, vx_min=40,
        entry_vx_range=25, entry_vy_range=30,
        exit_vx_range=40, exit_vy_range=200,
    ),
}

# Check self-consistency: mirrored specs must have the same ranges.
for _p1, _p2 in MIRROR_PORT.items():
    s1 = PORT_SPECS[_p1]
    s2 = PORT_SPECS[_p2]
    assert s1.x_range == s2.x_range, f"x_range mismatch for {_p1}/{_p2}"
    assert s1.y_range == s2.y_range, f"y_range mismatch for {_p1}/{_p2}"
    assert s1.vy_min == s2.vy_min, f"vy_min mismatch for {_p1}/{_p2}"
    assert s1.entry_vx_range == s2.entry_vx_range, f"entry_vx_range mismatch for {_p1}/{_p2}"
    assert s1.entry_vy_range == s2.entry_vy_range, f"entry_vy_range mismatch for {_p1}/{_p2}"


def entry_velocity(port: Port, speed: float, angle_degrees: float) -> tuple[float, float]:
    """Return an inward velocity mirrored from the matching output cone."""
    angle = math.radians(max(-MAX_EXIT_ANGLE_DEGREES, min(MAX_EXIT_ANGLE_DEGREES, angle_degrees)))
    outward_normal = {
        Port.T0: (0.0, 1.0),
        Port.L0: (1.0, 0.0),
        Port.R0: (-1.0, 0.0),
    }[port]
    nx, ny = outward_normal
    # Rotate the inward normal by the signed angle.
    cosine, sine = math.cos(angle), math.sin(angle)
    return speed * (nx * cosine - ny * sine), speed * (nx * sine + ny * cosine)


def entry_flow_samples(port: Port) -> list[tuple[float, float, float, float]]:
    """Sample position, speed, and angle from the output-symmetric contract."""
    spec = PORT_SPECS[port]
    along_offsets = (-spec.x_range, 0.0, spec.x_range) if port == Port.T0 else (-spec.y_range, 0.0, spec.y_range)
    samples = []
    for offset in along_offsets:
        for speed in ENTRY_TEST_SPEEDS:
            for angle in ENTRY_TEST_ANGLES:
                vx, vy = entry_velocity(port, speed, angle)
                dx, dy = (offset, 0.0) if port == Port.T0 else (0.0, offset)
                samples.append((dx, dy, vx, vy))
    return samples


UNIFORM_INPUTS = (Port.T0, Port.L0, Port.R0)
UNIFORM_OUTPUTS = (Port.B0, Port.L1, Port.R1)
