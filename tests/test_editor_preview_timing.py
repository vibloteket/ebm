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
