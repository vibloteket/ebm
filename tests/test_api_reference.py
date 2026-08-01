import inspect

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
    assert reference["tileSize"] == 200
    assert {port["name"] for port in reference["ports"]} == {"T0", "L0", "R0", "B0", "L1", "R1"}
    assert all(method["description"] for method in reference["tileBuilder"]["methods"])
    assert any("not available yet" in limitation for limitation in reference["limitations"])
