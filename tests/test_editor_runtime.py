import json

from ebm.editor_console import console
from ebm.editor_runtime import EditorRuntime


SOURCE = '''from ebm import TileBase

class TestTile(TileBase):
    author = "Tests"

    def build(self, builder):
        builder.visual_segment((20, 20), (180, 180), 3)

'''


def test_editor_compiles_route_free_source():
    result = json.loads(EditorRuntime().compile(SOURCE))
    assert result["ok"]
    assert result["className"] == "TestTile"
    assert result["displayName"] == "Test Tile"
    assert "routes" not in result


def test_editor_reports_source_line_for_build_failure():
    result = json.loads(EditorRuntime().compile(SOURCE.replace("(180, 180)", "(480, 180)")))
    assert not result["ok"]
    assert result["type"] == "GeometryBoundsError"
    assert result["line"] == 7


def test_editor_requires_exactly_one_tile_class():
    result = json.loads(EditorRuntime().compile("from ebm import TileBase\n"))
    assert not result["ok"]
    assert "exactly one" in result["message"]

    duplicate = SOURCE + "\nclass OtherTile(TileBase):\n    author = 'Tests'\n    def build(self, builder): pass\n"
    result = json.loads(EditorRuntime().compile(duplicate))
    assert not result["ok"]
    assert "TestTile, OtherTile" in result["message"]


def test_compile_check_does_not_emit_output_from_hidden_instance():
    source = SOURCE.replace("def build(self, builder):", 'def __init__(self):\n        print("hidden init")\n\n    def build(self, builder):\n        print("hidden build")')
    console.clear()
    assert json.loads(EditorRuntime().compile(source))["ok"]
    assert json.loads(console.drain()) == []


def test_validation_failures_include_explanation_and_replay_trajectory():
    source = SOURCE.replace(
        'builder.visual_segment((20, 20), (180, 180), 3)',
        'builder.static_segment((2, 200), (398, 200), elasticity=1.0)',
    )
    runtime = EditorRuntime()
    assert json.loads(runtime.compile(source))["ok"]
    response = json.loads(runtime.validate())
    result = response["result"]
    assert "repeatResult" in response
    failures = [detail for detail in result["details"] if detail["status"] in ("invalid", "lost")]
    assert failures
    assert all(detail["message"] for detail in failures)
    assert all(len(detail["trajectory"]) >= 2 for detail in failures)
    assert all(len(point) == 3 for detail in failures for point in detail["trajectory"])


def test_fail_fast_skips_repeat_and_preserves_replay():
    runtime = EditorRuntime()
    assert json.loads(runtime.compile('''from ebm import TileBase
class EmptyTile(TileBase):
    author = "Tests"
    def build(self, b): pass
'''))["ok"]
    result = json.loads(runtime.validate(stop_on_first_failure=True))
    assert not result["ok"]
    assert result["repeatSkipped"] and result["repeatResult"] is None
    assert result["result"]["stopped_early"]
    assert result["result"]["conserved"]
    failure = next(d for d in result["result"]["details"] if d["status"] == "invalid")
    assert failure["trajectory"]


def test_seeded_editor_runs_are_reproducible_and_restore_random():
    import random

    runtime = EditorRuntime()
    assert json.loads(runtime.compile('''from ebm import TileBase
import random
class RandomTile(TileBase):
    author = "Tests"
    def build(self, b):
        height = random.uniform(100, 300)
        b.static_segment((20, height), (380, height), 3)
'''))["ok"]
    state = random.getstate()
    first = json.loads(runtime.validate(stop_on_first_failure=True, seed="123"))
    assert random.getstate() == state
    random.random()  # preview activity must not change the seeded result
    next_state = random.getstate()
    second = json.loads(runtime.validate(stop_on_first_failure=True, seed=123))
    assert random.getstate() == next_state
    assert first == second and first["seed"] == 123
    assert first["result"]["details"]
    random.setstate(state)


def test_editor_reseeds_repeat_and_forwards_input_seed(monkeypatch):
    import random
    import ebm.editor_runtime as module
    from types import SimpleNamespace

    draws = []
    result = SimpleNamespace(ok=True, to_dict=lambda: {"ok": True})
    def single(*args, **kwargs):
        draws.append(random.random())
        return result
    def repeat(*args, **kwargs):
        assert kwargs["seed"] == 0
        draws.append(random.random())
        return result
    monkeypatch.setattr(module, "validate_tile_flow", single)
    monkeypatch.setattr(module, "validate_repeated_flow", repeat)
    runtime = EditorRuntime()
    runtime.tile_class = type("TestTile", (), {})
    output = json.loads(runtime.validate(seed="0"))
    assert output["ok"] and output["seed"] == 0
    assert draws == [random.Random(0).random()] * 2


def test_editor_seed_error_is_actionable():
    runtime = EditorRuntime()
    runtime.tile_class = type("TestTile", (), {})
    output = json.loads(runtime.validate(seed="abc"))
    assert not output["ok"]
    assert "Seed must be an integer" in output["message"]
