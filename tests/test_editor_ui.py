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


def test_editor_tab_indents_instead_of_moving_focus():
    entry = Path("web/editor-codemirror-entry.js").read_text()
    assert "indentWithTab" in entry
    bundle = Path("web/vendor/codemirror/editor-codemirror.js").read_text()
    assert '"Tab"' in bundle


def test_editor_run_shortcut_works_in_editor_and_globally():
    entry = Path("web/editor-codemirror-entry.js").read_text()
    assert '"Mod-Enter"' in entry
    source = Path("web/editor.js").read_text()
    assert 'event.key==="Enter"' in source
    assert "ctrlKey||event.metaKey" in source


def test_help_shortcut_toggles_drawer_in_editor_and_globally():
    entry = Path("web/editor-codemirror-entry.js").read_text()
    assert '"F1"' in entry
    assert '"Mod-/"' in entry
    source = Path("web/editor.js").read_text()
    assert 'event.key==="F1"' in source
    api = Path("web/api-reference.js").read_text()
    assert "toggle:()=>" in api
    assert "isOpen:()=>" in api
    assert "return api" in api
