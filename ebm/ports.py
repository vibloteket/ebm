from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

TILE_SIZE = 200


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


UNIFORM_INPUTS = (Port.T0, Port.L0, Port.R0)
UNIFORM_OUTPUTS = (Port.B0, Port.L1, Port.R1)


@dataclass(frozen=True)
class RoutePermutation:
    """Explicit bijection between the global three inputs and outputs."""

    exits: tuple[Port, Port, Port]

    def __init__(self, mapping):
        if isinstance(mapping, dict):
            exits = tuple(mapping[p] for p in UNIFORM_INPUTS)
        else:
            exits = tuple(mapping)
        if len(exits) != 3 or set(exits) != set(UNIFORM_OUTPUTS):
            raise ValueError("route must map T0/L0/R0 bijectively to B0/L1/R1")
        object.__setattr__(self, "exits", exits)

    @property
    def entries(self):
        return UNIFORM_INPUTS

    def exit_for(self, entry: Port) -> Port:
        return self.exits[UNIFORM_INPUTS.index(entry)]

    @property
    def mapping(self) -> dict[Port, Port]:
        return dict(zip(UNIFORM_INPUTS, self.exits))

    @property
    def key(self) -> tuple[str, str, str]:
        return tuple(p.name for p in self.exits)

    def __str__(self) -> str:
        return ", ".join(f"{a.name}->{b.name}" for a, b in zip(UNIFORM_INPUTS, self.exits))
