import json

from ebm.editor_runtime import EditorRuntime
from ebm.tiles.builtin.powered_channel import PoweredChannelTile


def source_for(tile_class):
    return f'''from ebm import DEFAULT_ROUTES, TileBase

class TestTile(TileBase):
    id = "test.editor"
    title = "Editor test"
    author = "Tests"
    api_version = 1
    routes = DEFAULT_ROUTES

    def __init__(self, route):
        self.route = route

    def build(self, tile):
        tile.visual_segment((20, 20), (180, 180), 3)

TILE_CLASS = TestTile
'''


def test_editor_compiles_valid_standalone_source():
    result = json.loads(EditorRuntime().compile(source_for(PoweredChannelTile)))
    assert result["ok"]
    assert result["id"] == "test.editor"
    assert len(result["routes"]) == 3


def test_editor_reports_source_line_for_build_failure():
    result = json.loads(EditorRuntime().compile(source_for(PoweredChannelTile).replace(
        'tile.visual_segment((20, 20), (180, 180), 3)',
        'tile.visual_segment((20, 20), (280, 180), 3)',
    )))
    assert not result["ok"]
    assert result["type"] == "ValueError"
    assert result["line"] == 14


def test_editor_rejects_missing_entrypoint():
    result = json.loads(EditorRuntime().compile("from ebm import TileBase\n"))
    assert not result["ok"]
    assert "TILE_CLASS" in result["message"]
