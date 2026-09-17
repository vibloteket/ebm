from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_main_entrypoint_cache_key_matches_app_version():
    html = (ROOT / "web" / "index.html").read_text()
    script = (ROOT / "web" / "main.js").read_text()
    assert 'main.js?v=0.68' in html
    assert 'APP_VERSION = "prototype-0.68-tile-400"' in script


def test_editor_entrypoint_cache_key_changes_with_runtime_dependencies():
    html = (ROOT / "web" / "editor.html").read_text()
    assert 'editor.js?v=0.84' in html
    assert 'editor.css?v=0.72' in html


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
