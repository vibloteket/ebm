import math

import pymunk
import pytest

from ebm.preview_validation import PreviewExitMonitor
from ebm.ports import tile_origin
from ebm.validator import classify_ball_state


def body_at(position, velocity=(300, 0)):
    body = pymunk.Body(1, 100)
    body.position = position
    body.velocity = velocity
    return body


def test_live_exit_waits_for_full_passage_then_marks_angle_failure():
    body = body_at((410, 300), (300, 200))
    monitor = PreviewExitMonitor()
    monitor.add(body, 0, 0)
    monitor.check(body, 15)
    assert not monitor.failed
    body.position = (416, 300)
    monitor.check(body, 15)
    assert body in monitor.failed
    assert monitor.markers[0]["text"] == "R0: 33.7° > 30°"
    monitor.check(body, 15)
    assert len(monitor.markers) == 1
    monitor.remove(body)
    assert body not in monitor.failed
    assert monitor.markers  # marker survives ball removal
    monitor.advance(8.1)
    assert not monitor.markers


@pytest.mark.parametrize("position,velocity,label", [
    ((416, 300), (300, 0), "R0"),
    ((200, 416), (0, 300), "B0"),
    ((416, 350), (300, 0), "right"),
    ((250, 416), (0, 300), "bottom"),
    ((-16, 100), (-300, 0), "left"),
    ((200, -16), (0, -300), "top"),
])
def test_preview_matches_validator_for_each_exit(position, velocity, label):
    body = body_at(position, velocity)
    monitor = PreviewExitMonitor()
    monitor.add(body, 0, 0)
    status, actual_label = classify_ball_state(*position, *velocity, 15)
    assert actual_label == label
    monitor.check(body, 15)
    assert (body in monitor.failed) == (status != "exited")
    assert len(monitor.markers) == (status != "exited")


@pytest.mark.parametrize("row,col,next_tile", [(0, 0, (0, 1)), (0, 1, (1, 2))])
def test_repeat_handoff_uses_staggered_origins(row, col, next_tile):
    ox, oy = tile_origin(row, col)
    body = body_at((ox+416, oy+300))
    monitor = PreviewExitMonitor(3)
    monitor.add(body, row, col)
    monitor.check(body, 15)
    assert monitor.tracked[body] == next_tile
    monitor.check(body, 15)
    assert not monitor.failed  # now inside receiving tile, not an input escape
    nx, ny = tile_origin(*next_tile)
    body.position = (nx+416, ny+300)
    body.velocity = (300, 250)
    monitor.check(body, 15)
    assert body in monitor.failed
    assert monitor.markers[0]["row"] == next_tile[0]


def test_marker_storage_is_bounded():
    monitor = PreviewExitMonitor()
    for _ in range(30):
        body = body_at((416, 360))
        monitor.add(body, 0, 0)
        monitor.check(body, 15)
        monitor.remove(body)
    assert len(monitor.markers) == 12
    assert not monitor.tracked and not monitor.failed
