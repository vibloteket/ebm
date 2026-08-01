import json

from ebm.editor_console import EditorConsole, MAX_LINES, MAX_LINES_PER_SECOND, console, console_muted, console_phase


def test_console_captures_lines_with_phase_and_stream():
    captured = EditorConsole()
    captured.phase = "build"
    writer = captured.writer("stdout")
    print("position", (10, 20), file=writer)
    assert json.loads(captured.drain()) == [
        {"phase": "build", "stream": "stdout", "text": "position (10, 20)"}
    ]


def test_console_bounds_total_lines():
    captured = EditorConsole()
    captured._window_lines = -MAX_LINES
    for index in range(MAX_LINES + 20):
        captured._append("stdout", str(index))
    entries = json.loads(captured.drain())
    assert len(entries) == MAX_LINES
    assert entries[0]["text"] == "20"


def test_console_throttles_hot_print_loop():
    captured = EditorConsole()
    for index in range(MAX_LINES_PER_SECOND + 10):
        captured._append("stdout", str(index))
    assert len(json.loads(captured.drain())) == MAX_LINES_PER_SECOND
    assert captured._suppressed == 10


def test_console_phase_restores_previous_context():
    previous = console.phase
    with console_phase("validation"):
        assert console.phase == "validation"
    assert console.phase == previous


def test_muted_console_discards_output():
    console.clear()
    with console_muted():
        console.writer("stdout").write("hidden\n")
    assert json.loads(console.drain()) == []
