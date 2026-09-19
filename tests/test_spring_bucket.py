import ast
from collections import Counter
from dataclasses import replace
import inspect

import pymunk
import pytest

from ebm.ports import Port
from ebm.tile_api import TileBuilder, TileResourceRegistry
from ebm.repeat_validation import validate_repeated_flow
from ebm.tiles.contributed.spring_bucket import SpringBucket
from ebm.validator import _spawn_ball, validate_tile_flow

pytestmark = pytest.mark.skipif(not SpringBucket.enabled, reason="Tile disabled")


class AuditedBucket(SpringBucket):
    def build(self, b):
        super().build(b)
        self.observed = {}
        self.crossings = []
        self.finished_cycles = []
        self.cycles = 0
        self.positions = []
        self.angles = []
        self.gate_counts = []
        # Test-only observation: no changes to contacts or ball motion.
        for shape, callbacks in list(b._registry._callbacks.items()):
            if b._registry._shape_handles[shape]._owner != b._owner:
                continue
            original = callbacks.begin

            def entered(event, original=original):
                self.observed.setdefault(event.ball, None)
                return original(event)

            b._registry._callbacks[shape] = replace(callbacks, begin=entered)
        self.crossed = set()

    def update(self, b, dt):
        self.positions.append(self.bucket.position)
        self.angles.append(self.bucket.angle)
        for ball, previous in list(self.observed.items()):
            try:
                x, y = self._local(ball)
            except PermissionError:
                continue
            if previous is not None and previous <= 40 < y and ball not in self.crossed:
                self.crossings.append((self.cycles, self.open, x))
                self.crossed.add(ball)
            self.observed[ball] = y
        was_open = self.open
        super().update(b, dt)
        if not was_open and self.open:
            self.cycles += 1
            self.gate_counts.append(len(self.releasing))
        if was_open and not self.open:
            self.finished_cycles.append(self.cycles)


@pytest.mark.parametrize('dt', [1 / 120, 1 / 60])
def test_bucket_accepts_both_inputs_and_releases_one_ball_per_opening(dt):
    tile = AuditedBucket()
    result = validate_tile_flow(lambda: tile, dt=dt)
    assert result.ok, result.to_dict()
    assert all(result.output_counts.values())
    assert result.peak_active <= 12
    assert tile.MIN_BALLS == 5
    assert tile.gate_counts and min(tile.gate_counts) >= 5
    counts = Counter(cycle for cycle, _, _ in tile.crossings)
    assert all(counts[cycle] == 1 for cycle in tile.finished_cycles), counts
    assert all(count <= 1 for count in counts.values()), counts
    assert all(opened for _, opened, _ in tile.crossings)
    assert all(abs(x) < 6 for _, _, x in tile.crossings), tile.crossings
    assert len(tile.observed) >= result.exited + 4
    # Real, unforced motion rather than a stationary or reset-every-frame body.
    assert max(x for x, _ in tile.positions) - min(x for x, _ in tile.positions) > 2
    assert max(y for _, y in tile.positions) - min(y for _, y in tile.positions) > 3
    assert max(tile.angles) - min(tile.angles) > .02


def test_bucket_repeated_flow_does_not_jam_or_release_multiple_balls():
    tiles = []

    def make():
        tile = AuditedBucket()
        tiles.append(tile)
        return tile

    # Longer than the publication smoke: a plain narrow hopper can pass 30s
    # yet eventually form a permanent two-ball arch and overflow upstream.
    result = validate_repeated_flow(make, duration=90, dt=1 / 60, seed=42)
    assert result.ok, result.to_dict()
    assert result.exited > 150
    assert result.active < 70
    for tile in tiles:
        counts = Counter(cycle for cycle, _, _ in tile.crossings)
        assert all(counts[cycle] == 1 for cycle in tile.finished_cycles), counts
        assert all(count <= 1 for count in counts.values()), counts
        assert all(opened for _, opened, _ in tile.crossings)


def test_four_balls_stay_and_the_fifth_releases_exactly_one():
    space = pymunk.Space()
    space.gravity = (0, 1800)
    registry = TileResourceRegistry.for_space(space)
    b = TileBuilder(registry, 1, (0, 0))
    tile = SpringBucket()
    tile.build(b)

    def advance(seconds):
        for _ in range(round(seconds * 120)):
            tile.update(b, 1 / 120)
            space.step(1 / 120)
            registry.advance(1 / 120)
            registry.validate_geometry()
        assert not registry.runtime_errors

    for i in range(4):
        _spawn_ball(space, i + 1, Port.T0, i * 1.25, 0, 0, 0, 300)
        advance(1.25)
    advance(2)
    assert tile.release_count == 0
    assert len(tile.balls) == 4
    _spawn_ball(space, 5, Port.T0, 7, 0, 0, 0, 300)
    advance(4)
    assert tile.release_count == 1
    assert len(tile.balls) == 4
    assert not tile.open


def test_bucket_has_no_ball_or_body_manipulation_beyond_the_hatch():
    source = inspect.getsource(SpringBucket)
    tree = ast.parse(source)
    calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
    forbidden = {'set_position', 'set_velocity', 'set_angle', 'set_angular_velocity',
                 'apply_force', 'apply_impulse', 'apply_torque', 'motor', 'remove'}
    assert not any(isinstance(func, ast.Attribute) and func.attr in forbidden for func in calls)
    assert 'surface_velocity' not in source
    assert '_registry' not in source
    for func in calls:
        if isinstance(func, ast.Attribute) and func.attr in {'pause', 'resume'}:
            assert ast.unparse(func.value) in {'self.hatch', 'self.gate_finger'}
