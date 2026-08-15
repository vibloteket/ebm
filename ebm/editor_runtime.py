from __future__ import annotations

import json
import sys
import traceback
import types

from .editor_console import console_muted, console_phase
from .repeat_validation import validate_repeated_flow
from .tile_api import TileBuilder, TileResourceRegistry
from .tile_base import TileBase, tile_class_from_module, tile_display_name
from .validator import validate_tile_flow


class EditorRuntime:
    """Compile and validate an editor-provided flow tile."""

    def __init__(self):
        self.tile_class = None
        self.source = ""

    def compile(self, source: str) -> str:
        module = types.ModuleType("ebm_editor_tile")
        module.__package__ = "ebm"
        try:
            sys.modules[module.__name__] = module
            code = compile(source, "editor_tile.py", "exec")
            with console_phase("compile"):
                exec(code, module.__dict__)
            tile_class = tile_class_from_module(module)
            self._check_tile_class(tile_class)
            with console_muted():
                self._check_instance(tile_class())
            self.tile_class = tile_class
            self.source = source
            return json.dumps({"ok": True, "className": tile_class.__name__, "displayName": tile_display_name(tile_class), "author": tile_class.author})
        except Exception as error:
            return json.dumps(self._error(error))
        finally:
            sys.modules.pop(module.__name__, None)

    def validate(self) -> str:
        if self.tile_class is None:
            return json.dumps({"ok": False, "message": "Run the source before validating."})
        try:
            with console_phase("validation"):
                result = validate_tile_flow(self.tile_class, name=tile_display_name(self.tile_class))
                repeat = validate_repeated_flow(self.tile_class)
            return json.dumps({
                "ok": result.ok and repeat.ok,
                "result": result.to_dict(),
                "repeatResult": repeat.to_dict(),
            })
        except Exception as error:
            return json.dumps(self._error(error))

    @staticmethod
    def _check_tile_class(tile_class):
        if not isinstance(tile_class, type) or not issubclass(tile_class, TileBase):
            raise TypeError("Tile source must define a TileBase subclass")
        if not isinstance(tile_class.author, str) or not tile_class.author.strip() or tile_class.author == TileBase.author:
            raise ValueError("Tile must declare an author")

    @staticmethod
    def _check_instance(tile):
        import pymunk
        space = pymunk.Space()
        registry = TileResourceRegistry.for_space(space)
        builder = TileBuilder(registry, 1, (0, 0))
        try:
            with console_phase("build"):
                tile.build(builder)
        finally:
            registry.destroy_owner(1)

    @staticmethod
    def _error(error: Exception) -> dict:
        line = error.lineno if isinstance(error, SyntaxError) else None
        if line is None:
            for frame in reversed(traceback.extract_tb(error.__traceback__)):
                if frame.filename == "editor_tile.py":
                    line = frame.lineno
                    break
        return {"ok": False, "type": type(error).__name__, "message": str(error), "line": line}


_runtime = EditorRuntime()


def compile_source(source: str) -> str:
    return _runtime.compile(source)


def validate_source() -> str:
    return _runtime.validate()
