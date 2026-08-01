from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from weakref import WeakKeyDictionary

from .ports import TILE_SIZE

BUILD_MARGIN = 10.0
BALL_COLLISION_TYPE = 1
BALL_FRICTION = 0.45
BALL_ELASTICITY = 0.8
TILE_SENSOR_COLLISION_TYPE = 2
BALL_CATEGORY = 1 << 0


def ball_shape_filter():
    """Balls interact with tile shapes, sensors, and other balls."""
    import pymunk
    return pymunk.ShapeFilter(categories=BALL_CATEGORY)


@dataclass(frozen=True)
class ShapeHandle:
    id: int


@dataclass(frozen=True)
class BodyHandle:
    id: int


@dataclass(frozen=True)
class ConstraintHandle:
    id: int


@dataclass(frozen=True)
class VisualSegment:
    a: tuple[float, float]
    b: tuple[float, float]
    radius: float


@dataclass(frozen=True)
class ContactEvent:
    own_shape: ShapeHandle
    ball_body: Any
    point: tuple[float, float] | None = None
    normal: tuple[float, float] | None = None


class TileResourceRegistry:
    """Engine-owned Pymunk resources and contact dispatch for tile instances."""

    _by_space: WeakKeyDictionary = WeakKeyDictionary()

    def __init__(self, space):
        self.space = space
        self._next = 1
        self._objects: dict[int, Any] = {}
        self._owner: dict[int, int] = {}
        self._shape_handles: dict[Any, ShapeHandle] = {}
        self._callbacks: dict[Any, tuple[Callable[[ContactEvent], Any], bool]] = {}
        self._visuals: dict[int, list[Any]] = {}
        self._install_dispatcher()

    @classmethod
    def for_space(cls, space):
        registry = cls._by_space.get(space)
        if registry is None:
            registry = cls(space)
            cls._by_space[space] = registry
        return registry

    def _install_dispatcher(self):
        def pre_solve(arbiter, _space, _data):
            ball, owned = arbiter.shapes
            if ball.collision_type != BALL_COLLISION_TYPE:
                ball, owned = owned, ball
            registration = self._callbacks.get(owned)
            if registration is None or ball.collision_type != BALL_COLLISION_TYPE:
                return True
            callback, default_collide = registration
            handle = self._shape_handles[owned]
            result = callback(ContactEvent(handle, ball.body))
            return default_collide if result is None else bool(result)

        self.space.on_collision(BALL_COLLISION_TYPE, TILE_SENSOR_COLLISION_TYPE, pre_solve=pre_solve)

    def add(self, owner: int, obj: Any, handle_type):
        handle = handle_type(self._next)
        self._next += 1
        self._objects[handle.id] = obj
        self._owner[handle.id] = owner
        self.space.add(obj)
        if isinstance(handle, ShapeHandle):
            self._shape_handles[obj] = handle
        return handle

    def resolve(self, owner: int, handle):
        if self._owner.get(handle.id) != owner:
            raise PermissionError("tile does not own this resource")
        return self._objects[handle.id]

    def on_contact(self, owner: int, handle: ShapeHandle, callback, *, collide: bool = False):
        shape = self.resolve(owner, handle)
        shape.collision_type = TILE_SENSOR_COLLISION_TYPE
        self._callbacks[shape] = (callback, collide)

    def add_visual(self, owner: int, visual: Any):
        self._visuals.setdefault(owner, []).append(visual)
        return visual

    def destroy_owner(self, owner: int):
        import pymunk

        ids = [key for key, value in self._owner.items() if value == owner]
        priority = {pymunk.Constraint: 0, pymunk.Shape: 1, pymunk.Body: 2}
        objects = [(key, self._objects[key]) for key in ids]
        objects.sort(key=lambda item: next((value for kind, value in priority.items() if isinstance(item[1], kind)), 3))
        for key, obj in objects:
            self._callbacks.pop(obj, None)
            self._shape_handles.pop(obj, None)
            try:
                self.space.remove(obj)
            except Exception:
                pass
            self._objects.pop(key, None)
            self._owner.pop(key, None)
        self._visuals.pop(owner, None)

    def owned_objects(self, owner: int):
        return [self._objects[key] for key, value in self._owner.items() if value == owner]

    def owned_visuals(self, owner: int):
        return list(self._visuals.get(owner, ()))


class TileBuilder:
    """Tile-local, ownership-checked construction API; exposes no Space."""

    def __init__(self, registry: TileResourceRegistry, owner: int, origin: tuple[float, float]):
        self._registry = registry
        self._owner = owner
        self.origin = origin

    def _point(self, point):
        x, y = map(float, point)
        if not (-BUILD_MARGIN <= x <= TILE_SIZE + BUILD_MARGIN and -BUILD_MARGIN <= y <= TILE_SIZE + BUILD_MARGIN):
            raise ValueError(f"point outside tile build bounds: {(x, y)}")
        return self.origin[0] + x, self.origin[1] + y

    def static_segment(self, a, b, radius=1, *, friction=.8, elasticity=.2, surface_velocity=(0, 0)):
        """Build a fixed physical rail from local point a to b; return its ShapeHandle."""
        import pymunk

        if radius < 0 or radius > BUILD_MARGIN:
            raise ValueError("segment radius outside build budget")
        shape = pymunk.Segment(self._registry.space.static_body, self._point(a), self._point(b), radius)
        shape.friction, shape.elasticity = friction, elasticity
        shape.surface_velocity = surface_velocity
        return self._registry.add(self._owner, shape, ShapeHandle)

    def static_circle(self, center, radius, *, friction=.4, elasticity=.75):
        """Build a fixed physical circle in local coordinates; return its ShapeHandle."""
        import pymunk

        x, y = map(float, center)
        self._point((x-radius, y-radius)); self._point((x+radius, y+radius))
        body = pymunk.Body(body_type=pymunk.Body.STATIC); body.position = self._point(center)
        body_handle = self._registry.add(self._owner, body, BodyHandle)
        shape = pymunk.Circle(body, radius); shape.friction, shape.elasticity = friction, elasticity
        return self._registry.add(self._owner, shape, ShapeHandle)

    def sensor_box(self, left, top, right, bottom):
        """Build an invisible, non-colliding rectangular sensor; return its ShapeHandle."""
        import pymunk

        points=[self._point(p) for p in ((left,top),(right,top),(right,bottom),(left,bottom))]
        shape=pymunk.Poly(self._registry.space.static_body,points);shape.sensor=True;shape.ebm_hidden=True
        return self._registry.add(self._owner,shape,ShapeHandle)

    def on_ball_contact(self, shape: ShapeHandle, callback, *, collide: bool = False):
        """Call callback(ContactEvent) while a ball contacts an owned shape."""
        self._registry.on_contact(self._owner, shape, callback, collide=collide)

    def visual_segment(self, a, b, radius=3):
        """Build a non-physical line used only by renderers; return a VisualSegment."""
        # Visual-only primitives are owned and bounds-checked but never added to
        # Pymunk, so reference graphics cannot interfere with ball routing.
        local_a=(float(a[0]),float(a[1]));local_b=(float(b[0]),float(b[1]))
        self._point(local_a);self._point(local_b)
        return self._registry.add_visual(self._owner,VisualSegment(local_a,local_b,float(radius)))

    def body_position(self, body: BodyHandle):
        """Return the current world-space position of an owned BodyHandle."""
        return self._registry.resolve(self._owner, body).position

    def remove(self, handle):
        """Remove an owned resource from the simulation before normal cleanup."""
        obj=self._registry.resolve(self._owner,handle)
        self._registry.space.remove(obj)

    @property
    def visual_objects(self):
        return self._registry.owned_objects(self._owner) + self._registry.owned_visuals(self._owner)
