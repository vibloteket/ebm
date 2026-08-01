from __future__ import annotations

import json
import sys
import traceback
import types

from .editor_console import console_muted, console_phase
from .ports import Port, RoutePermutation
from .tile_api import TileBuilder, TileResourceRegistry
from .tile_base import TileBase
from .validator import validate_tile_port_spec


class EditorRuntime:
    """Compile and validate an editor-provided tile without touching shipped modules."""

    def __init__(self):
        self.tile_class = None
        self.source = ""

    def compile(self, source: str) -> str:
        module = types.ModuleType("ebm_editor_tile")
        module.__package__ = "ebm"
        namespace = module.__dict__
        try:
            sys.modules[module.__name__] = module
            code = compile(source, "editor_tile.py", "exec")
            with console_phase("compile"):
                exec(code, namespace)
            tile_class = namespace.get("TILE_CLASS")
            self._check_tile_class(tile_class)
            # These instances only verify every declared route. They are not
            # the visible preview tile and must not duplicate its debug output.
            with console_muted():
                for route in tile_class.routes:
                    tile = tile_class(route)
                    self._check_instance(tile, route)
            self.tile_class = tile_class
            self.source = source
            return json.dumps({
                "ok": True,
                "id": tile_class.id,
                "title": tile_class.title,
                "author": tile_class.author,
                "routes": [list(route.key) for route in tile_class.routes],
            })
        except Exception as error:
            return json.dumps(self._error(error))
        finally:
            sys.modules.pop(module.__name__, None)

    def validate(self) -> str:
        if self.tile_class is None:
            return json.dumps({"ok": False, "message": "Run the source before validating."})
        try:
            with console_phase("validation"):
                results = [
                    validate_tile_port_spec(
                        lambda route=route: self.tile_class(route),
                        route,
                        name=f"{self.tile_class.id} {route}",
                        duration=12.0,
                    )
                    for route in self.tile_class.routes
                ]
            return json.dumps({
                "ok": all(result.ok for result in results),
                "results": [result.to_dict() for result in results],
            })
        except Exception as error:
            return json.dumps(self._error(error))

    @staticmethod
    def _check_tile_class(tile_class):
        if not isinstance(tile_class, type) or not issubclass(tile_class, TileBase):
            raise TypeError("Source must export a TileBase subclass as TILE_CLASS")
        if tile_class.api_version != 1:
            raise ValueError(f"Unsupported api_version: {tile_class.api_version}")
        if not isinstance(tile_class.id, str) or not tile_class.id.strip() or tile_class.id == TileBase.id:
            raise ValueError("Tile must declare a stable id")
        if not isinstance(tile_class.title, str) or not tile_class.title.strip():
            raise ValueError("Tile must declare a title")
        if not isinstance(tile_class.author, str) or not tile_class.author.strip():
            raise ValueError("Tile must declare an author")
        if not tile_class.routes or not all(isinstance(route, RoutePermutation) for route in tile_class.routes):
            raise ValueError("Tile must declare one or more RoutePermutation values")

    @staticmethod
    def _check_instance(tile, route):
        if not hasattr(tile, "build"):
            raise TypeError("TILE_CLASS instances must implement build(tile)")
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
        line = None
        if isinstance(error, SyntaxError):
            line = error.lineno
        else:
            for frame in reversed(traceback.extract_tb(error.__traceback__)):
                if frame.filename == "editor_tile.py":
                    line = frame.lineno
                    break
        return {
            "ok": False,
            "type": type(error).__name__,
            "message": str(error),
            "line": line,
            "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        }


_runtime = EditorRuntime()


def compile_source(source: str) -> str:
    return _runtime.compile(source)


def validate_source() -> str:
    return _runtime.validate()
