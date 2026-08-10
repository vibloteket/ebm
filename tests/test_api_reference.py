import inspect

import pytest

from ebm.tile_api import TileBuilder
from scripts.generate_api_reference import build_reference


def test_api_reference_covers_public_builder_methods():
    reference = build_reference()
    documented = {method["name"] for method in reference["tileBuilder"]["methods"]}
    public = {
        name
        for name, member in inspect.getmembers(TileBuilder, inspect.isfunction)
        if not name.startswith("_")
    }
    assert documented == public


def test_api_reference_describes_current_contract():
    reference = build_reference()
    assert reference["apiVersion"] == 1
    assert reference["tileSize"] == 400
    assert {port["name"] for port in reference["ports"]} == {"T0", "L0", "R0", "B0", "L1", "R1"}
    assert all(method["description"] for method in reference["tileBuilder"]["methods"])
    signatures = {method["name"]: method["signature"] for method in reference["tileBuilder"]["methods"]}
    assert "a: Point" in signatures["static_segment"]
    assert "-> ShapeHandle" in signatures["static_segment"]
    assert "begin: CollisionCallback | None" in signatures["on_ball_contact"]
    assert "pre_solve: CollisionCallback | None" in signatures["on_ball_contact"]
    assert "post_solve: ContactCallback | None" in signatures["on_ball_contact"]
    assert "separate: ContactCallback | None" in signatures["on_ball_contact"]
    assert {item["name"] for item in reference["commonTypes"]} == {
        "Point", "Vector", "Color", "ShapeHandle", "BallHandle",
    }
    assert reference["portRules"] == {
        "aperture": 120,
        "ballRadius": 15,
        "ballDiameter": 30,
        "centerRange": 45,
        "buildMargin": 20.0,
    }
    assert reference["flow"] == {
        "entryTestSpeeds": [1.0, 300.0, 600.0],
        "maxBallSpeed": 600.0,
        "spawnInterval": 0.4,
        "perInputInterval": pytest.approx(1.2),
    }
    assert reference["validation"] == {"balls": 120, "maxActive": 20}
    assert reference["capabilities"]["available"]
    assert reference["capabilities"]["unavailable"]
    assert {prop["name"] for prop in reference["contactEvent"]["properties"]} == {
        "own_shape", "ball", "point", "normal", "impulse", "kinetic_energy",
    }
