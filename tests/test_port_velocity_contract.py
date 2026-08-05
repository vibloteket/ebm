import math

import pytest

from ebm.ports import (
    ENTRY_TEST_ANGLES,
    ENTRY_TEST_SPEEDS,
    MAX_EXIT_ANGLE_DEGREES,
    Port,
    entry_flow_samples,
    entry_velocity,
)


@pytest.mark.parametrize("port,normal", [
    (Port.T0, (0, 1)),
    (Port.L0, (1, 0)),
    (Port.R0, (-1, 0)),
])
def test_entry_velocity_is_inside_symmetric_30_degree_cone(port, normal):
    for speed in ENTRY_TEST_SPEEDS:
        for angle in ENTRY_TEST_ANGLES:
            vx, vy = entry_velocity(port, speed, angle)
            assert math.hypot(vx, vy) == pytest.approx(speed)
            dot = vx * normal[0] + vy * normal[1]
            measured = math.degrees(math.acos(dot / speed))
            assert measured == pytest.approx(abs(angle))
            assert measured <= MAX_EXIT_ANGLE_DEGREES


def test_entry_samples_cover_speed_angle_and_position_extremes():
    for port in (Port.T0, Port.L0, Port.R0):
        samples = entry_flow_samples(port)
        assert len(samples) == 3 * len(ENTRY_TEST_SPEEDS) * len(ENTRY_TEST_ANGLES)
        speeds = {round(math.hypot(vx, vy), 6) for _, _, vx, vy in samples}
        assert speeds == set(ENTRY_TEST_SPEEDS)
