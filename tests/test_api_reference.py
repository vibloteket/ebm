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
    assert {port["name"] for port in reference["ports"]} == {"T0", "L0", "B0", "R0"}
    assert all(method["description"] for method in reference["tileBuilder"]["methods"])
    assert reference["tileBase"]["properties"] == [{
        "name": "author",
        "type": "str",
        "required": True,
        "description": "Name of the tile author or project.",
    }, {
        "name": "enabled",
        "type": "bool",
        "required": False,
        "description": "Defaults to True. False skips publication flow checks and machine selection, but keeps the tile in the editor. Syntax, imports and metadata must still be valid.",
    }]
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
        "buildMargin": 0.0,
    }
    assert reference["flow"] == {
        "entryTestSpeeds": [1.0, 300.0, 600.0],
        "maxBallSpeed": 600.0,
        "spawnInterval": 1.25,
        "perInputInterval": pytest.approx(2.5),
    }
    assert reference["validation"] == {"balls": 120, "maxActive": 20}
    assert reference["capabilities"]["available"]
    assert reference["capabilities"]["unavailable"]
    assert {prop["name"] for prop in reference["contactEvent"]["properties"]} == {
        "own_shape", "ball", "point", "normal", "impulse", "kinetic_energy",
    }
