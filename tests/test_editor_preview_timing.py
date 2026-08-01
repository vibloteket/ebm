import ast
from pathlib import Path


def test_editor_preview_uses_independent_boundary_spawn_clocks():
    source = Path("ebm/editor_preview.py").read_text()
    tree = ast.parse(source)
    step = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "step"
    )
    step_source = ast.get_source_segment(source, step)
    assert "for boundary in list(self.spawn_clocks)" in step_source
    assert "self.rng.uniform(0.65, 1.35)" in step_source
    assert "spawn_boundary()" not in step_source


def test_editor_preview_skips_physics_and_drawing_while_paused():
    source = Path("ebm/editor_preview.py").read_text()
    tree = ast.parse(source)
    frame = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "frame"
    )
    frame_source = ast.get_source_segment(source, frame)
    assert "if not _paused" in frame_source
    assert "_preview.step(dt)" in frame_source
    assert "draw(canvas, _preview)" in frame_source


def test_resuming_resets_frame_timestamp_to_avoid_catch_up():
    source = Path("ebm/editor_preview.py").read_text()
    tree = ast.parse(source)
    setter = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "set_paused"
    )
    setter_source = ast.get_source_segment(source, setter)
    assert "_last_ts = None" in setter_source
