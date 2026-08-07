import json

from ebm.editor_console import console
from ebm.editor_runtime import EditorRuntime


SOURCE = '''from ebm import TileBase

class TestTile(TileBase):
    id = "test.editor"
    title = "Editor test"
    author = "Tests"
    api_version = 2

    def build(self, builder):
        builder.visual_segment((20, 20), (180, 180), 3)

TILE_CLASS = TestTile
'''


def test_editor_compiles_route_free_source():
    result = json.loads(EditorRuntime().compile(SOURCE))
    assert result["ok"]
    assert result["id"] == "test.editor"
    assert "routes" not in result


def test_editor_reports_source_line_for_build_failure():
    result = json.loads(EditorRuntime().compile(SOURCE.replace("(180, 180)", "(480, 180)")))
    assert not result["ok"]
    assert result["type"] == "ValueError"
    assert result["line"] == 10


def test_editor_rejects_missing_entrypoint():
    result = json.loads(EditorRuntime().compile("from ebm import TileBase\n"))
    assert not result["ok"]
    assert "TILE_CLASS" in result["message"]


def test_compile_check_does_not_emit_output_from_hidden_instance():
    source = SOURCE.replace("def build(self, builder):", 'def __init__(self):\n        print("hidden init")\n\n    def build(self, builder):\n        print("hidden build")')
    console.clear()
    assert json.loads(EditorRuntime().compile(source))["ok"]
    assert json.loads(console.drain()) == []


def test_validation_failures_include_explanation_and_replay_trajectory():
    source = SOURCE.replace(
        'builder.visual_segment((20, 20), (180, 180), 3)',
        'builder.static_segment((0, 200), (400, 200), elasticity=1.0)',
    )
    runtime = EditorRuntime()
    assert json.loads(runtime.compile(source))["ok"]
    result = json.loads(runtime.validate())["result"]
    failures = [detail for detail in result["details"] if detail["status"] in ("invalid", "lost")]
    assert failures
    assert all(detail["message"] for detail in failures)
    assert all(len(detail["trajectory"]) >= 2 for detail in failures)
    assert all(len(point) == 3 for detail in failures for point in detail["trajectory"])
