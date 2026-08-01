from __future__ import annotations

from contextlib import contextmanager
import json
import sys
import time


MAX_LINES = 500
MAX_LINES_PER_SECOND = 50


class EditorConsole:
    """Bounded stdout/stderr capture used only by the browser tile editor."""

    def __init__(self):
        self.entries: list[dict[str, str]] = []
        self.phase = "runtime"
        self._pending = {"stdout": "", "stderr": ""}
        self._window_started = time.monotonic()
        self._window_lines = 0
        self._suppressed = 0

    def writer(self, stream: str):
        return _ConsoleWriter(self, stream)

    def write(self, stream: str, text: str) -> None:
        pending = self._pending[stream] + str(text)
        parts = pending.split("\n")
        self._pending[stream] = parts.pop()
        for line in parts:
            if line:
                self._append(stream, line)

    def _append(self, stream: str, text: str) -> None:
        now = time.monotonic()
        if now - self._window_started >= 1:
            if self._suppressed:
                self._store("warning", f"Output throttled: {self._suppressed} messages suppressed")
            self._window_started = now
            self._window_lines = 0
            self._suppressed = 0
        if self._window_lines >= MAX_LINES_PER_SECOND:
            self._suppressed += 1
            return
        self._window_lines += 1
        self._store(stream, text)

    def _store(self, stream: str, text: str) -> None:
        self.entries.append({"phase": self.phase, "stream": stream, "text": text})
        if len(self.entries) > MAX_LINES:
            del self.entries[: len(self.entries) - MAX_LINES]

    def drain(self) -> str:
        entries, self.entries = self.entries, []
        return json.dumps(entries)

    def clear(self) -> None:
        self.entries.clear()
        self._pending = {"stdout": "", "stderr": ""}
        self._suppressed = 0


class _ConsoleWriter:
    def __init__(self, console: EditorConsole, stream: str):
        self.console = console
        self.stream = stream

    def write(self, text) -> int:
        value = str(text)
        self.console.write(self.stream, value)
        return len(value)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


console = EditorConsole()
_installed = False


def install_console() -> None:
    """Route ordinary print() calls to the editor's bounded output buffer."""
    global _installed
    if _installed:
        return
    sys.stdout = console.writer("stdout")
    sys.stderr = console.writer("stderr")
    _installed = True


@contextmanager
def console_phase(name: str):
    previous = console.phase
    console.phase = name
    try:
        yield
    finally:
        console.phase = previous


def drain_console() -> str:
    return console.drain()


def clear_console() -> None:
    console.clear()
