from pathlib import Path


def test_editor_has_no_redundant_tile_metadata_row():
    html = Path("web/editor.html").read_text()
    assert 'class="tile-meta"' not in html
    assert 'id="tile-author"' not in html
    assert 'id="tile-name"' not in html
    assert 'id="tile-origin"' not in html


def test_validation_results_only_show_in_validation_view():
    html = Path("web/editor.html").read_text()
    source = Path("web/editor.js").read_text()
    assert '<div id="validation-results" hidden></div>' in html
    assert 'els.validation_results.hidden=view!=="validation"' in source


def test_replay_restores_validation_view_after_preview_refresh():
    source = Path("web/editor.js").read_text()
    expected = 'refresh_preview")("single");pyodide.globals.get("set_preview_view")("validation");pyodide.globals.get("replay_validation_failure")'
    assert expected in source
