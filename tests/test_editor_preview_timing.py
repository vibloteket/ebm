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


def test_editor_preview_draws_physical_builder_shapes():
    source = Path("ebm/editor_preview.py").read_text()
    assert 'type(shape).__name__ == "Segment"' in source
    assert 'type(shape).__name__ == "Circle"' in source
    assert 'getattr(shape,"ebm_hidden",False)' in source


def test_editor_preview_draws_sensors_only_in_single_mode():
    source = Path("ebm/editor_preview.py").read_text()
    assert "def _draw_sensor_overlay" in source
    assert 'if preview.mode == "single":\n            for shape in builder.visual_objects:' in source
    assert "_draw_sensor_overlay(ctx, shape, sx, sy, scale)" in source
    assert 'ctx.fillStyle = "rgba(71,85,105,.13)"' in source
    assert "ctx.setLineDash" in source


def test_refresh_rebuilds_and_draws_once_while_paused():
    source = Path("ebm/editor_preview.py").read_text()
    tree = ast.parse(source)
    refresh = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "refresh"
    )
    refresh_source = ast.get_source_segment(source, refresh)
    assert "_preview.configure" in refresh_source
    assert "draw(_canvas, _preview)" in refresh_source
    assert "_preview.step" not in refresh_source


def test_validation_view_stops_live_simulation_and_canvas_tracks_layout_size():
    source = Path("ebm/editor_preview.py").read_text()
    assert 'if _view == "simulation": _preview.step(dt)' in source
    assert 'if _preview and _view == "simulation": _preview.spawn_boundary()' in source
    assert "for ball in list(_preview.balls)" in source
    web_source = Path("web/editor.js").read_text()
    assert "new ResizeObserver(syncPreviewSize).observe(els.preview)" in web_source


def test_repeat_preview_can_scale_below_point_three_to_fit_mobile_canvas():
    source = Path("ebm/editor_preview.py").read_text()
    assert "scale = max(.01, min((width-36)/world, (height-44)/world))" in source
    assert "scale = max(.3," not in source


def test_failure_replay_draws_validator_trajectory_overlay():
    source = Path("ebm/editor_preview.py").read_text()
    assert "def replay_failure" in source
    assert 'detail.get("trajectory")' in source
    assert 'ctx.strokeStyle="rgba(190,24,24,.48)"' in source
    assert 'ctx.fillStyle="#dc2626"' in source


def test_resuming_resets_frame_timestamp_to_avoid_catch_up():
    source = Path("ebm/editor_preview.py").read_text()
    tree = ast.parse(source)
    setter = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "set_paused"
    )
    setter_source = ast.get_source_segment(source, setter)
    assert "_last_ts = None" in setter_source
