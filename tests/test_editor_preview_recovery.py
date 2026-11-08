"""Exercise the real frame/refresh functions without requiring a browser."""
import ast
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext

import pytest


def preview_harness():
    source = ast.parse(Path("ebm/editor_preview.py").read_text())
    names = {"start", "refresh", "get_error", "_record_error"}
    module = ast.Module(body=[node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    frames, errors = [], []
    preview = SimpleNamespace(configure=lambda mode: None, step=lambda dt: None)
    ns = dict(
        _preview=None, _canvas=None, _last_ts=None, _paused=False,
        _view="simulation", _error="", _proxies=[],
        EditorPreview=lambda: preview, create_proxy=lambda fn: fn,
        window=SimpleNamespace(requestAnimationFrame=frames.append, addEventListener=lambda *args: None),
        draw=lambda *args: None, console_phase=lambda phase: nullcontext(),
        traceback=SimpleNamespace(print_exc=lambda: errors.append(True)),
    )
    exec(compile(module, "ebm/editor_preview.py", "exec"), ns)
    canvas = SimpleNamespace(clientWidth=500, clientHeight=400, addEventListener=lambda *args: None)
    ns["start"](canvas)
    return ns, preview, frames, errors


@pytest.mark.parametrize("failure_site", ["step", "draw"])
def test_frame_failure_latches_once_and_run_recovers(failure_site):
    ns, preview, frames, errors = preview_harness()
    def broken(*args):
        raise TypeError("bad tile callback")
    if failure_site == "step":
        preview.step = broken
    else:
        ns["draw"] = broken
    frames.pop(0)(1000)
    assert ns["get_error"]() == "TypeError: bad tile callback"
    assert len(frames) == 1
    frames.pop(0)(1016)
    assert errors == [True]  # no repeated tracebacks or stepping failed state
    steps = []
    preview.step = steps.append
    ns["draw"] = lambda *args: None
    ns["refresh"]("single")
    assert ns["get_error"]() == ""
    assert ns["_last_ts"] is None
    frames.pop(0)(100000)  # no accumulated time after recovery
    assert steps == [1 / 60]
    assert len(frames) == 1


def test_failed_rebuild_stops_partial_preview_until_successful_run():
    ns, preview, frames, errors = preview_harness()
    def broken(mode):
        raise ValueError("bad build")
    preview.configure = broken
    with pytest.raises(ValueError, match="bad build"):
        ns["refresh"]()
    steps = []
    preview.step = steps.append
    frames.pop(0)(1000)
    assert steps == []
    assert ns["get_error"]() == "ValueError: bad build"
    preview.configure = lambda mode: None
    ns["refresh"]()
    frames.pop(0)(1016)
    assert steps == [1 / 60]
