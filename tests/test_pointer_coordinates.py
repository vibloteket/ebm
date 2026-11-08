"""Coordinate picking uses the exact preview transform, including staggered tiles."""
import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from ebm.ports import COLUMN_OFFSET, TILE_SIZE, tile_origin


def functions():
    tree = ast.parse(Path("ebm/editor_preview.py").read_text())
    names = {"preview_transform", "canvas_tile_coordinates", "pointer_coordinates"}
    module = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    ns = dict(math=math, TILE_SIZE=TILE_SIZE, COLUMN_OFFSET=COLUMN_OFFSET, tile_origin=tile_origin, _preview=None, _canvas=None)
    exec(compile(module, "ebm/editor_preview.py", "exec"), ns)
    return ns


@pytest.mark.parametrize("size", [1, 3])
@pytest.mark.parametrize("dimensions", [(300, 260), (900, 600), (1400, 350), (320, 900)])
def test_every_tile_roundtrips_including_mobile_and_nonzero_origins(size, dimensions):
    ns = functions()
    width, height = dimensions
    scale, ox, oy = ns["preview_transform"](width, height, size)
    for row in range(size):
        for col in range(size):
            tx, ty = tile_origin(row, col)
            for x, y in ((0.1, 0.1), (123.4, 234.5), (399.9, 399.9)):
                point = ns["canvas_tile_coordinates"](ox + (tx + x) * scale, oy + (ty + y) * scale, width, height, size)
                assert point["x"] == pytest.approx(x)
                assert point["y"] == pytest.approx(y)
                assert (point["row"], point["col"], point["gridSize"]) == (row, col, size)


@pytest.mark.parametrize("size", [1, 3])
def test_canvas_margins_and_staggered_grid_gaps_have_no_coordinates(size):
    ns = functions()
    scale, ox, oy = ns["preview_transform"](600, 600, size)
    def pick(wx, wy):
        return ns["canvas_tile_coordinates"](ox + wx * scale, oy + wy * scale, 600, 600, size)
    for wx, wy in ((-1, 100), (100, -1), (400 * size + 1, 100), (100, size * 400 + 1)):
        assert pick(wx, wy) is None
    if size == 3:
        assert pick(500, 100) is None  # above middle column
        assert pick(100, 1300) is None  # below first column
        assert pick(500, 1300)["row"] == 2
        assert pick(500, 1300)["y"] == pytest.approx(300)


def test_web_wrapper_null_before_start_and_json_after_start():
    ns = functions()
    assert ns["pointer_coordinates"](100, 100) == "null"
    ns["_preview"] = SimpleNamespace(grid_size=1)
    ns["_canvas"] = SimpleNamespace(width=600, height=600)
    point = json.loads(ns["pointer_coordinates"](300, 300))
    assert point["x"] == point["y"] == 200
    assert ns["pointer_coordinates"](0, 0) == "null"
