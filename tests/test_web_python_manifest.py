from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_main_entrypoint_cache_key_matches_app_version():
    html = (ROOT / "web" / "index.html").read_text()
    script = (ROOT / "web" / "main.js").read_text()
    assert 'main.js?v=0.71' in html
    assert 'APP_VERSION = "prototype-0.71-tile-400"' in script


def test_editor_entrypoint_cache_key_changes_with_runtime_dependencies():
    html = (ROOT / "web" / "editor.html").read_text()
    assert 'editor.js?v=0.94' in html
    assert 'pointer-coordinates.js?v=2' in (ROOT / 'web' / 'editor.js').read_text()
    assert 'web/pointer-coordinates.js' in (ROOT / 'scripts' / 'build-static-site.sh').read_text()
    assert 'api-reference.js?v=0.79' in (ROOT / 'web' / 'editor.js').read_text()
    assert 'editor.css?v=0.76' in html


def test_browser_entrypoints_ship_python_dependencies():
    for script in ("main.js", "debug.js", "editor.js"):
        source = (ROOT / "web" / script).read_text()
        assert 'import {loadPythonPackage}' in source
        assert 'await loadPythonPackage(pyodide)' in source
        assert 'PY_FILES' not in source
    loader = (ROOT / 'web' / 'python-package.js').read_text()
    assert './python-files.json' in loader
    assert 'mkdirTree' in loader


def test_help_has_a_dedicated_tile_publication_section():
    source = (ROOT / 'web' / 'api-reference.js').read_text()
    assert '["publishing","Publishing tiles",' in source
    assert 'ebm/tiles/contributed/my_scanner.py' in source
    assert 'https://github.com/vibloteket/ebm/tree/main/ebm/tiles/contributed' in source
    assert 'Add file → Upload files' in source
    assert 'commit to <code>main</code>' in source


def test_physics_selection_is_main_machine_only():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    main = (root / "web/main.js").read_text()
    assert 'from "./physics-config.js?v=1"' in main
    build = (root / "scripts/build-static-site.sh").read_text()
    assert '"$ROOT/web/physics-config.js" "$OUT/physics-config.js"' in build
    for entry in ("editor.js", "debug.js"):
        source = (root / "web" / entry).read_text()
        assert "pymunk-7.3.1-cp314" in source
        assert "physics-config" not in source
    for version in ("7.3.1", "7.4.0"):
        assert (root / "web/vendor" / f"pymunk-{version}-cp314-cp314-pyemscripten_2026_0_wasm32.whl").is_file()
