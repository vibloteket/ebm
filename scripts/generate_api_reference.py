#!/usr/bin/env python3
"""Generate the browser tile API reference from the public Python API."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ebm.ports import BALL_RADIUS, PORT_APERTURE, PORT_CENTER_RANGE, Port, TILE_SIZE  # noqa: E402
from ebm.tile_api import BUILD_MARGIN, BallHandle, BodyHandle, ContactEvent, ShapeHandle, TileBuilder, VisualHandle  # noqa: E402
from ebm.tile_base import TileBase  # noqa: E402
from ebm.validator import MAX_ACTIVE_BALLS, VALIDATION_BALLS  # noqa: E402


def public_signature(member) -> str:
    signature = str(inspect.signature(member))
    return signature.replace("(self, ", "(").replace("(self)", "()")


def method_reference(cls, names: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "signature": public_signature(getattr(cls, name)),
            "description": inspect.getdoc(getattr(cls, name)) or "",
        }
        for name in names
    ]


def build_reference() -> dict:
    return {
        "apiVersion": TileBase.api_version,
        "tileSize": TILE_SIZE,
        "tileBase": {
            "description": inspect.getdoc(TileBase),
            "properties": [
                {"name": "id", "type": "str", "required": True, "description": "Stable, globally unique tile ID, for example vb.water-wheel."},
                {"name": "title", "type": "str", "required": True, "description": "Human-readable name shown in the editor and catalog."},
                {"name": "author", "type": "str", "required": True, "description": "Name of the tile author or project."},
                {"name": "api_version", "type": "int", "required": True, "description": "Tile API version. The current supported value is 2."},
            ],
            "methods": method_reference(TileBase, ("build", "update")),
        },
        "tileBuilder": {
            "description": inspect.getdoc(TileBuilder),
            "methods": method_reference(TileBuilder, (
                "static_segment", "static_circle", "sensor_box", "on_ball_contact",
                "visual_segment", "body_position", "remove",
            )),
        },
        "handles": [
            {
                "name": "ShapeHandle",
                "description": "Ownership-safe handle returned by physical shape builders.",
                "methods": method_reference(ShapeHandle, ("set_fill_color", "set_stroke_color", "set_friction", "set_elasticity", "pause", "resume")),
            },
            {
                "name": "VisualHandle",
                "description": "Ownership-safe handle returned by visual-only builders.",
                "methods": method_reference(VisualHandle, ("set_fill_color", "set_stroke_color", "pause", "resume")),
            },
            {
                "name": "BodyHandle",
                "description": "Ownership-safe handle for a physical body.",
                "methods": method_reference(BodyHandle, ("set_position", "set_velocity", "pause", "resume")),
            },
            {
                "name": "BallHandle",
                "description": "Tile-bound handle to a contacting ball. Style and material changes reset after handoff.",
                "methods": method_reference(BallHandle, ("set_fill_color", "set_stroke_color", "set_friction", "set_elasticity", "set_position", "set_velocity", "pause", "resume")),
            },
        ],
        "contactEvent": {
            "description": inspect.getdoc(ContactEvent),
            "properties": [
                {"name": "own_shape", "type": "ShapeHandle", "description": "The tile-owned shape that received the contact."},
                {"name": "ball", "type": "BallHandle", "description": "The tile-bound contacting ball handle."},
                {"name": "point", "type": "tuple[float, float] | None", "description": "Reserved contact point; currently None in API v2."},
                {"name": "normal", "type": "tuple[float, float] | None", "description": "Reserved contact normal; currently None in API v2."},
            ],
        },
        "ports": [{"name": port.name, "point": list(port.point), "kind": "input" if port.name in {"T0", "L0", "R0"} else "output"} for port in Port],
        "portRules": {
            "aperture": PORT_APERTURE,
            "ballRadius": BALL_RADIUS,
            "centerRange": PORT_CENTER_RANGE,
            "buildMargin": BUILD_MARGIN,
        },
        "validation": {
            "balls": VALIDATION_BALLS,
            "maxActive": MAX_ACTIVE_BALLS,
        },
        "recipes": [
            {
                "title": "Sloping rail",
                "description": "A physical segment that guides balls using friction and restitution.",
                "code": "builder.static_segment(\n    (40, 140), (360, 260),\n    radius=8, friction=0.8, elasticity=0.2,\n)",
            },
            {
                "title": "Powered channel",
                "description": "A rail whose surface actively carries contacting balls.",
                "code": "builder.static_segment(\n    (40, 200), (360, 200),\n    radius=8, surface_velocity=(160, 0),\n)",
            },
            {
                "title": "Ball contact sensor",
                "description": "Detect balls without adding visible or colliding geometry.",
                "code": "sensor = builder.sensor_box(80, 80, 320, 320)\n\ndef on_ball(event):\n    event.ball.set_fill_color((255, 40, 40, 255))\n\nbuilder.on_ball_contact(sensor, on_ball)",
            },
        ],
        "capabilities": {
            "available": [
                "Static segments and circles",
                "Sensor boxes and ball-contact callbacks",
                "Visual-only segments",
                "Surface velocity for powered rails",
                "Mutable colors and physical materials",
                "Position and velocity changes through ownership-checked handles",
                "Pause, resume, and owned-resource removal",
                "Optional per-frame update(builder, dt)",
            ],
            "unavailable": [
                "User-created dynamic bodies and attached shapes",
                "Joints, motors, and springs",
                "Direct forces and impulses",
                "Direct access to the shared Pymunk Space",
            ],
        },
    }


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "web" / "api-reference.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_reference(), indent=2) + "\n")
    print(f"Generated {output}")


if __name__ == "__main__":
    main()
