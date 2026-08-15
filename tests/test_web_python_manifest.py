from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_main_entrypoint_cache_key_matches_app_version():
    html = (ROOT / "web" / "index.html").read_text()
    script = (ROOT / "web" / "main.js").read_text()
    assert 'main.js?v=0.57' in html
    assert 'APP_VERSION = "prototype-0.57-tile-400"' in script


def test_editor_entrypoint_cache_key_changes_with_runtime_dependencies():
    html = (ROOT / "web" / "editor.html").read_text()
    assert 'editor.js?v=0.73' in html
    assert 'editor.css?v=0.72' in html


def test_browser_entrypoints_ship_python_dependencies():
    for script in ("main.js", "debug.js", "editor.js"):
        source = (ROOT / "web" / script).read_text()
        assert '"ball_physics.py"' in source, f"{script} must load the shared speed limiter"
        if script == "editor.js":
            assert '"repeat_validation.py"' in source
        for module in ("segment_switchback.py", "teleport_collector.py"):
            assert f'"tiles/contributed/{module}"' in source, (
                f"{script} must load every module imported by tile_catalog.py"
            )
    for script in ("main.js", "debug.js"):
        source = (ROOT / "web" / script).read_text()
        assert '"tile_output.py"' in source, f"{script} must load engine.py's tile_output dependency"
