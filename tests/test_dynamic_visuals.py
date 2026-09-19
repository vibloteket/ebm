import ast
from pathlib import Path
from types import SimpleNamespace

import pymunk

from ebm.tile_api import TileBuilder, TileResourceRegistry, VisualSegment


class Context:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name, args))


class Canvas:
    def __init__(self):
        self.context = Context()

    def getContext(self, kind):
        return self.context


def renderer():
    # Exercise the real render functions without importing browser-only js.
    path = Path(__file__).parents[1] / 'ebm/web_demo.py'
    tree = ast.parse(path.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {'_cached_tile', 'draw_dynamic', '_css_color'}]
    scope = dict(VisualSegment=VisualSegment, Engine=object, TILE_SIZE=400,
                 _TILE_PAD=20, _renderer='basic', _tile_cache={},
                 _render_profile={'cache_hits': 0, 'cache_misses': 0},
                 document=SimpleNamespace(createElement=lambda name: Canvas()),
                 _transform=lambda ctx, engine: (10, 20, 1))
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), scope)
    return scope


def test_moving_cord_does_not_rebuild_static_cache_and_draws_at_world_coordinates():
    registry = TileResourceRegistry.for_space(pymunk.Space())
    b = TileBuilder(registry, 7, (400, 200))
    line = b.visual_segment((20, 20), (180, 180), 2, dynamic=True)
    scope = renderer()
    active = SimpleNamespace(builder=b, owner_id=7, tile=object())
    cached = scope['_cached_tile'](active)
    assert not cached.context.calls
    line.set_segment_points((30, 30), (160, 170))
    line.set_fill_color((100, 80, 60, 255))
    assert b.visual_revision == 0
    assert registry.resolve(7, line).dynamic
    registry.validate_geometry()
    assert scope['_cached_tile'](active) is cached
    canvas = Canvas()
    scope['draw_dynamic'](canvas, SimpleNamespace(active_tiles={7: active}, balls=[]))
    assert ('moveTo', (420, 210)) in canvas.context.calls
    assert ('lineTo', (550, 350)) in canvas.context.calls


def test_static_style_cache_discards_previous_revisions_of_the_same_instance():
    registry = TileResourceRegistry.for_space(pymunk.Space())
    b = TileBuilder(registry, 7, (0, 0))
    line = b.visual_segment((20, 20), (180, 180), 2)
    scope = renderer()
    other = ('basic', 'other', 'Tile', 0, 99, 1)
    scope['_tile_cache'][other] = object()
    active = SimpleNamespace(builder=b, owner_id=7, tile=object())
    for i in range(100):
        line.set_segment_points((20 + i / 100, 20), (180, 180))
        scope['_cached_tile'](active)
    assert len(scope['_tile_cache']) == 2
    assert other in scope['_tile_cache']
