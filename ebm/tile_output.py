from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout


class _NullWriter:
    def write(self, text) -> int:
        return len(str(text))

    def flush(self) -> None:
        pass


_NULL = _NullWriter()


@contextmanager
def suppress_tile_output():
    """Keep forgotten contributor print calls out of the full machine output."""
    with redirect_stdout(_NULL), redirect_stderr(_NULL):
        yield
