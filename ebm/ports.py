from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

TILE_SIZE = 400
COLUMN_OFFSET = TILE_SIZE // 2
BALL_RADIUS = 15
PORT_APERTURE = 120
PORT_CENTER_RANGE = (PORT_APERTURE - 2 * BALL_RADIUS) / 2
MAX_EXIT_ANGLE_DEGREES = 30.0
ENTRY_TEST_SPEEDS = (1.0, 300.0, 600.0)
ENTRY_TEST_ANGLES = (-MAX_EXIT_ANGLE_DEGREES, 0.0, MAX_EXIT_ANGLE_DEGREES)


@dataclass(frozen=True)
class PortSpec:
    """Entry/exit position and velocity tolerances for a port."""

    x_center: float
    y_center: float
    x_range: float
    y_range: float
    vy_min: float
    vx_min: float
    entry_vx_range: float
    entry_vy_range: float
    exit_vx_range: float
    exit_vy_range: float

    def sample_values(self):
        xs = (-self.x_range, 0.0, self.x_range)
        ys = (-self.y_range, 0.0, self.y_range)
        vxs = (-self.entry_vx_range, 0.0, self.entry_vx_range)
        vys = (-self.entry_vy_range, 0.0, self.entry_vy_range)
        samples = [
            (dx, dy, dvx, dvy)
            for dx in xs for dy in ys for dvx in vxs for dvy in vys
        ]
        return [xs, ys, vxs, vys], samples


class Port(Enum):
    # Inputs
    T0 = (200, 0)
    L0 = (0, 100)

    # Outputs. R0 meets the next column's L0 because odd columns are shifted
    # down by half a tile.
    B0 = (200, 400)
    R0 = (400, 300)

    @property
    def point(self) -> tuple[float, float]:
        x, y = self.value
        return float(x), float(y)


INPUT_PORTS = frozenset({Port.T0, Port.L0})
OUTPUT_PORTS = frozenset({Port.B0, Port.R0})
MIRROR_PORT = {
    Port.B0: Port.T0,
    Port.T0: Port.B0,
    Port.R0: Port.L0,
    Port.L0: Port.R0,
}

PORT_SPECS: dict[Port, PortSpec] = {
    Port.T0: PortSpec(
        x_center=200, y_center=0, x_range=PORT_CENTER_RANGE, y_range=8,
        vy_min=80, vx_min=0, entry_vx_range=80, entry_vy_range=50,
        exit_vx_range=120, exit_vy_range=1998,
    ),
    Port.B0: PortSpec(
        x_center=200, y_center=400, x_range=PORT_CENTER_RANGE, y_range=8,
        vy_min=80, vx_min=0, entry_vx_range=80, entry_vy_range=50,
        exit_vx_range=120, exit_vy_range=1998,
    ),
    Port.L0: PortSpec(
        x_center=0, y_center=100, x_range=8, y_range=PORT_CENTER_RANGE,
        vy_min=0, vx_min=80, entry_vx_range=50, entry_vy_range=60,
        exit_vx_range=80, exit_vy_range=400,
    ),
    Port.R0: PortSpec(
        x_center=400, y_center=300, x_range=8, y_range=PORT_CENTER_RANGE,
        vy_min=0, vx_min=80, entry_vx_range=50, entry_vy_range=60,
        exit_vx_range=80, exit_vy_range=400,
    ),
}

for _p1, _p2 in MIRROR_PORT.items():
    s1, s2 = PORT_SPECS[_p1], PORT_SPECS[_p2]
    assert s1.x_range == s2.x_range
    assert s1.y_range == s2.y_range
    assert s1.vy_min == s2.vy_min
    assert s1.entry_vx_range == s2.entry_vx_range
    assert s1.entry_vy_range == s2.entry_vy_range


def tile_origin(row: int, col: int) -> tuple[int, int]:
    """Return the staggered world origin for a logical grid coordinate."""
    return col * TILE_SIZE, row * TILE_SIZE + (col & 1) * COLUMN_OFFSET


def right_neighbor(row: int, col: int) -> tuple[int, int]:
    """Tile whose L0 receives this tile's R0."""
    return (row if col % 2 == 0 else row + 1), col + 1


def left_neighbor(row: int, col: int) -> tuple[int, int]:
    """Tile whose R0 feeds this tile's L0."""
    return (row - 1 if col % 2 == 0 else row), col - 1


def entry_velocity(port: Port, speed: float, angle_degrees: float) -> tuple[float, float]:
    """Return an inward velocity mirrored from the matching output cone."""
    angle = math.radians(max(-MAX_EXIT_ANGLE_DEGREES, min(MAX_EXIT_ANGLE_DEGREES, angle_degrees)))
    outward_normal = {Port.T0: (0.0, 1.0), Port.L0: (1.0, 0.0)}[port]
    nx, ny = outward_normal
    cosine, sine = math.cos(angle), math.sin(angle)
    return speed * (nx * cosine - ny * sine), speed * (nx * sine + ny * cosine)


def entry_flow_samples(port: Port) -> list[tuple[float, float, float, float]]:
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


UNIFORM_INPUTS = (Port.T0, Port.L0)
UNIFORM_OUTPUTS = (Port.B0, Port.R0)
