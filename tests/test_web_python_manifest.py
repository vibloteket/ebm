from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_browser_entrypoints_ship_python_dependencies():
    for script in ("main.js", "debug.js", "editor.js"):
        source = (ROOT / "web" / script).read_text()
        assert '"ball_physics.py"' in source, f"{script} must load the shared speed limiter"
    for script in ("main.js", "debug.js"):
        source = (ROOT / "web" / script).read_text()
        assert '"tile_output.py"' in source, f"{script} must load engine.py's tile_output dependency"
