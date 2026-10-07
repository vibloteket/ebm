from dataclasses import dataclass, field
import math
import sys
import traceback
from typing import Any, Callable
from weakref import WeakKeyDictionary

from pymunk import Vec2d

from .ports import TILE_SIZE
from .geometry_bounds import GeometryBoundsError, MAX_SHAPE_RADIUS, check_bounds, local_shape_geometry, points_bounds, radius_value, shape_bounds, transformed_bounds

BUILD_MARGIN = 0.0  # Kept for API reference compatibility; no geometry may overhang.
BALL_COLLISION_TYPE = 1
BALL_FRICTION = 0.45
BALL_ELASTICITY = 0.8
TILE_SENSOR_COLLISION_TYPE = 2
BALL_CATEGORY = 1 << 0
type Point = tuple[float, float]
type Vector = tuple[float, float]
type Color = tuple[int, int, int, int]
DEFAULT_SEGMENT_FILL: Color = (49, 90, 168, 255)
DEFAULT_SEGMENT_STROKE: Color = (0, 0, 0, 0)
DEFAULT_CIRCLE_FILL: Color = (220, 118, 37, 255)
DEFAULT_CIRCLE_STROKE: Color = (140, 67, 24, 255)
DEFAULT_BALL_FILL: Color = (22, 114, 212, 255)
DEFAULT_BALL_STROKE: Color = (12, 63, 143, 255)

def _validate_color(color) -> Color:
    if color is None:
        return (0, 0, 0, 0)  # None means "do not paint this layer".
    if not isinstance(color, (tuple, list)) or len(color) != 4:
        raise ValueError("color must be an RGBA tuple of four integers, or None to leave the layer unpainted")
    if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255 for value in color):
        raise ValueError("RGBA color components must be integers from 0 to 255")
    return tuple(color)

# Sentinel distinguishing "argument omitted" from an explicit None (which
# clears the paint layer) in style setters.
_UNSET: Any = object()

def _validate_flag(value, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be True or False")
    return value

def ball_shape_filter():
    """Balls interact with tile shapes, sensors, and other balls."""
    import pymunk
    return pymunk.ShapeFilter(categories=BALL_CATEGORY)

@dataclass(frozen=True)
class ResourceHandle:
    id: int
    _owner: int = field(repr=False, compare=False)
    _registry: Any = field(repr=False, compare=False)

    def pause(self) -> None:
        """Temporarily remove this object from physics and normal rendering."""
        self._registry.pause_resource(self._owner, self)

    def resume(self, *, delay: float = 0) -> None:
        """Restore a paused object, optionally after simulation-time seconds."""
        self._registry.resume_resource(self._owner, self, delay=delay)

@dataclass(frozen=True)
class StyledHandle(ResourceHandle):
    def set_fill_color(self, color: Color | None) -> None:
        """Set this object's fill RGBA tuple (four integers from 0 to 255), or None for no fill."""
        self._registry.set_style(self._owner, self, fill_color=color)

    def set_stroke_color(self, color: Color | None) -> None:
        """Set this object's outline RGBA tuple (four integers from 0 to 255), or None for no outline."""
        self._registry.set_style(self._owner, self, stroke_color=color)

@dataclass(frozen=True)
class ShapeHandle(StyledHandle):
    def set_friction(self, friction: float) -> None:
        """Set this physical shape's friction coefficient."""
        self._registry.set_shape_material(self._owner, self, friction=friction)

    def set_elasticity(self, elasticity: float) -> None:
        """Set this physical shape's elasticity from 0 to 1."""
        self._registry.set_shape_material(self._owner, self, elasticity=elasticity)

@dataclass(frozen=True)
class BodyHandle(ResourceHandle):
    @property
    def position(self) -> Point:
        """Current tile-local body position, as a Vec2d."""
        return self._registry.body_position(self._owner, self)

    @property
    def velocity(self) -> Vector:
        """Current world-space linear velocity, as a Vec2d."""
        return self._registry.body_velocity(self._owner, self)

    @property
    def angle(self) -> float:
        """Current body angle in radians."""
        return self._registry.body_angle(self._owner, self)

    @property
    def angular_velocity(self) -> float:
        """Current angular velocity in radians per second."""
        return self._registry.body_angular_velocity(self._owner, self)

    def set_position(self, position: Point) -> None:
        """Move this body to a tile-local position."""
        self._registry.set_body_position(self._owner, self, position)

    def set_velocity(self, velocity: Vector) -> None:
        """Set this body's world-space velocity vector."""
        self._registry.set_body_velocity(self._owner, self, velocity)

    def set_angle(self, angle: float) -> None:
        """Set this body's angle in radians."""
        self._registry.set_body_angle(self._owner, self, angle)

    def set_angular_velocity(self, velocity: float) -> None:
        """Set this body's angular velocity in radians per second."""
        self._registry.set_body_angular_velocity(self._owner, self, velocity)

    def apply_force(self, force: Vector, point: Point = (0, 0)) -> None:
        """Apply a world-space force at a body-local point."""
        self._registry.apply_body_force(self._owner, self, force, point)

    def apply_impulse(self, impulse: Vector, point: Point = (0, 0)) -> None:
        """Apply a world-space impulse at a body-local point."""
        self._registry.apply_body_impulse(self._owner, self, impulse, point)

    def apply_torque(self, torque: float) -> None:
        """Add torque to this body for the current simulation step."""
        self._registry.apply_body_torque(self._owner, self, torque)

@dataclass(frozen=True)
class ConstraintHandle(ResourceHandle):
    pass

@dataclass(frozen=True)
class MotorHandle(ConstraintHandle):
    def set_rate(self, rate: float) -> None:
        """Set the target angular rate in radians per second."""
        self._registry.set_motor(self._owner, self, rate=rate)

    def set_max_force(self, max_force: float) -> None:
        """Set the maximum motor force."""
        self._registry.set_motor(self._owner, self, max_force=max_force)

@dataclass(frozen=True)
class VisualHandle(StyledHandle):
    def set_segment_points(self, a: Point, b: Point) -> None:
        """Move the endpoints of a visual segment in tile-local coordinates."""
        self._registry.set_visual_segment_points(self._owner, self, a, b)

@dataclass
class VisualStyle:
    fill_color: Color
    stroke_color: Color
    # Foreground graphics draw after balls, so they can occlude them.
    foreground: bool = False

@dataclass(frozen=True)
class VisualSegment:
    a: Point
    b: Point
    radius: float
    dynamic: bool = False

@dataclass(frozen=True)
class VisualPolygon:
    """Non-physical filled polygon; tile-local points, immutable."""
    points: tuple[Point, ...]
    radius: float = 0.0

@dataclass(frozen=True)
class BallHandle:
    """Tile-bound handle to one logical ball."""

    _owner: int = field(repr=False, compare=False)
    _registry: Any = field(repr=False, compare=False)
    _body: Any = field(repr=False)
    _generation: int = field(repr=False)

    @property
    def position(self) -> Point:
        """Current tile-local position, as a Vec2d."""
        return self._registry.ball_position(self)

    @property
    def velocity(self) -> Vector:
        """Current world-space velocity, as a Vec2d."""
        return self._registry.ball_velocity(self)

    @property
    def radius(self) -> float:
        """Ball radius."""
        return self._registry.ball_radius(self)

    @property
    def paused(self) -> bool:
        """Whether the ball is outside physics and normal rendering."""
        return self._registry.ball_paused(self)

    def set_fill_color(self, color: Color | None) -> None:
        """Set the ball's fill RGBA tuple (four integers from 0 to 255), or None for no fill."""
        self._registry.set_ball_style(self, fill_color=color)

    def set_stroke_color(self, color: Color | None) -> None:
        """Set the ball's outline RGBA tuple (four integers from 0 to 255), or None for no outline."""
        self._registry.set_ball_style(self, stroke_color=color)

    def set_friction(self, friction: float) -> None:
        self._registry.set_ball_material(self, friction=friction)

    def set_elasticity(self, elasticity: float) -> None:
        self._registry.set_ball_material(self, elasticity=elasticity)

    def set_position(self, position: Point) -> None:
        """Move the ball to a tile-local position wholly inside this tile."""
        self._registry.set_ball_position(self, position)

    def set_velocity(self, velocity: Vector) -> None:
        self._registry.set_ball_velocity(self, velocity)

    def pause(self) -> None:
        """Temporarily remove the ball from physics and normal rendering."""
        self._registry.pause_ball(self)

    def resume(self, *, delay: float = 0) -> None:
        """Restore a paused ball, optionally after simulation-time seconds."""
        self._registry.resume_ball(self, delay=delay)

@dataclass(frozen=True)
class ContactEvent:
    """Safe tile-facing view of one ball/shape contact phase."""

    own_shape: ShapeHandle
    ball: BallHandle
    point: Point | None
    normal: Vector | None
    impulse: Vector | None = None
    kinetic_energy: float | None = None

type ContactCallback = Callable[[ContactEvent], None]
type CollisionCallback = Callable[[ContactEvent], bool | None]

@dataclass(frozen=True)
class ContactCallbacks:
    begin: CollisionCallback | None = None
    pre_solve: CollisionCallback | None = None
    post_solve: ContactCallback | None = None
    separate: ContactCallback | None = None

class TileResourceRegistry:
    """Engine-owned Pymunk resources and contact dispatch for tile instances."""

    _by_space: WeakKeyDictionary = WeakKeyDictionary()

    def __init__(self, space):
        self.space = space
        self._next = 1
        self._objects: dict[int, Any] = {}
        self._owner: dict[int, int] = {}
        self._shape_handles: dict[Any, ShapeHandle] = {}
        self._callbacks: dict[Any, ContactCallbacks] = {}
        self._visuals: dict[int, list[int]] = {}
        self._styles: dict[int, VisualStyle] = {}
        self._visual_revisions: dict[int, int] = {}
        self._origins: dict[int, tuple[float, float]] = {}
        self._paused_resources: set[int] = set()
        self._resource_resumes: dict[int, float] = {}
        self._body_members: dict[int, set[int]] = {}
        self._body_for_object: dict[int, int] = {}
        self._balls: dict[Any, dict[str, Any]] = {}
        self._static_shape_bodies: dict[int, Any] = {}
        self._shape_geometries: dict[int, Any] = {}
        self._body_geometry_radii: dict[Any, float] = {}
        self._checked_static_poses: dict[int, Any] = {}
        self._checked_visuals: dict[int, VisualSegment] = {}
        self._ball_constraints: dict[Any, list[int]] = {}
        self._filter_groups: dict[Any, int] = {}
        self._filter_group_members: dict[int, set[Any]] = {}
        self._next_filter_group = 1
        self._constraint_endpoints: dict[int, set[int]] = {}
        self._scene_listeners: list[Callable[[str, int], None]] = []
        self.runtime_errors: list[dict[str, Any]] = []
        self._install_dispatcher()

    @classmethod
    def for_space(cls, space):
        registry = cls._by_space.get(space)
        if registry is None:
            registry = cls(space)
            cls._by_space[space] = registry
        return registry

    def add_scene_listener(self, listener: Callable[[str, int], None]) -> None:
        """Register a callable notified with (kind, ident) on visual/ball changes.

        kind "visual" carries a tile owner id; kind "ball" carries a body id.
        Listeners let the web scene exporter mirror state without polling.
        """
        self._scene_listeners.append(listener)

    def _emit_scene(self, kind: str, ident: int) -> None:
        for listener in self._scene_listeners:
            listener(kind, ident)

    def _install_dispatcher(self):
        def dispatch(phase: str, arbiter) -> None:
            ball, owned = arbiter.shapes
            if ball.collision_type != BALL_COLLISION_TYPE:
                ball, owned = owned, ball
            registration = self._callbacks.get(owned)
            if registration is None or ball.collision_type != BALL_COLLISION_TYPE:
                return
            callback = getattr(registration, phase)
            if callback is None:
                return
            handle = self._shape_handles[owned]
            ball_handle = self._claim_ball(handle._owner, ball.body, ball)
            event = self._contact_event(handle, ball_handle, arbiter, phase)
            try:
                result = callback(event)
            except PermissionError as error:
                # A ball can touch the next tile's sensor one physics step
                # before the previous tile releases ownership at handoff.
                # This is transient, not an authoring failure: suppress this
                # solve and let a pre_solve callback retry on the next step.
                if str(error) == "ball is no longer owned by this tile":
                    arbiter.process_collision = False
                    return
                raise
            except Exception as error:
                # Never let an authoring error escape through CFFI as
                # "Exception ignored". Record it for validators, report it
                # through captured stderr, and disable this registration.
                self._callbacks.pop(owned, None)
                arbiter.process_collision = False
                rendered = "".join(traceback.format_exception(error))
                self.runtime_errors.append({
                    "owner": handle._owner,
                    "phase": phase,
                    "type": type(error).__name__,
                    "message": str(error),
                    "traceback": rendered,
                    **getattr(error, "details", {}),
                })
                print(
                    f"Tile contact callback error during {phase}: "
                    f"{type(error).__name__}: {error}",
                    file=sys.stderr,
                )
                traceback.print_exception(error, file=sys.stderr)
                return
            if phase in {"begin", "pre_solve"} and result is not None:
                arbiter.process_collision = bool(result)

        self.space.on_collision(
            BALL_COLLISION_TYPE,
            TILE_SENSOR_COLLISION_TYPE,
            begin=lambda arbiter, _space, _data: dispatch("begin", arbiter),
            pre_solve=lambda arbiter, _space, _data: dispatch("pre_solve", arbiter),
            post_solve=lambda arbiter, _space, _data: dispatch("post_solve", arbiter),
            separate=lambda arbiter, _space, _data: dispatch("separate", arbiter),
        )

    def _contact_event(self, handle: ShapeHandle, ball: BallHandle, arbiter, phase: str) -> ContactEvent:
        ox, oy = self._origins[handle._owner]
        point = None
        if phase != "separate":
            contact_set = arbiter.contact_point_set
            if contact_set.points:
                contact = contact_set.points[0]
                point = Vec2d(
                    (float(contact.point_a.x) + float(contact.point_b.x)) / 2 - ox,
                    (float(contact.point_a.y) + float(contact.point_b.y)) / 2 - oy,
                )
        normal = Vec2d(float(arbiter.normal.x), float(arbiter.normal.y))
        impulse = None
        kinetic_energy = None
        if phase == "post_solve":
            impulse = Vec2d(float(arbiter.total_impulse.x), float(arbiter.total_impulse.y))
            kinetic_energy = float(arbiter.total_ke)
        return ContactEvent(handle, ball, point, normal, impulse, kinetic_energy)

    def register_owner(self, owner: int, origin: tuple[float, float]) -> None:
        self._origins[owner] = tuple(map(float, origin))

    def validate_geometry(self, owner: int | None = None, *, time: float = 0, phase: str = "build") -> None:
        """Validate owned shapes, sensors and visuals, including paused resources.

        Called only by validation, not the live machine's frame loop. Static
        shape geometry is immutable through the public API; remeasure it only
        if its body transform changes. Visual endpoint changes replace the
        immutable VisualSegment. Dynamic geometry is always remeasured.
        """
        poses = {}
        interior_bodies = set()
        for key, resource_owner in self._owner.items():
            if owner is not None and owner != resource_owner:
                continue
            obj = self._objects[key]
            is_visual = isinstance(obj, (VisualSegment, VisualPolygon))
            static_body = self._static_shape_bodies.get(key)
            if is_visual and self._checked_visuals.get(key) is obj:
                continue
            shape_data = self._shape_geometries.get(key)
            if shape_data is not None:
                body, geometry = shape_data
                if body in interior_bodies:
                    continue
                if body not in poses:
                    poses[body] = (body.position, body.angle)
                    radius = self._body_geometry_radii.get(body)
                    if radius is not None:
                        position, angle = poses[body]
                        ox, oy = self._origins[resource_owner]
                        x, y = position.x - ox, position.y - oy
                        # This circle encloses every attached shape at ANY
                        # rotation. If it fits, all their exact bounds fit too.
                        if math.isfinite(angle) and radius <= x <= TILE_SIZE - radius and radius <= y <= TILE_SIZE - radius:
                            interior_bodies.add(body)
                            continue
                if static_body is not None and self._checked_static_poses.get(key) == poses[body]:
                    continue
            elif not is_visual:
                continue
            label = f"{type(obj).__name__} #{key}, tile {resource_owner}, t={time:.6g}s ({phase})"
            details = dict(owner=resource_owner, object_id=key, time=time, phase=phase)
            try:
                if isinstance(obj, VisualSegment):
                    bounds = points_bounds((obj.a, obj.b), obj.radius)
                elif isinstance(obj, VisualPolygon):
                    bounds = points_bounds(obj.points, obj.radius)
                elif shape_data is not None:
                    bounds = transformed_bounds(geometry, poses[body], self._origins[resource_owner])
                else:
                    continue
            except ValueError as error:
                raise GeometryBoundsError(f"{label}: {error}", **details) from error
            check_bounds(bounds, label=label, **details)
            if static_body is not None:
                self._checked_static_poses[key] = poses[static_body]
            if is_visual:
                self._checked_visuals[key] = obj

    def add(self, owner: int, obj: Any, handle_type, *, body: BodyHandle | None = None):
        if issubclass(handle_type, ShapeHandle):
            check_bounds(shape_bounds(obj, self._origins[owner]),
                         label=f"{type(obj).__name__} #{self._next}, tile {owner}", owner=owner, object_id=self._next)
        handle = handle_type(self._next, owner, self)
        self._next += 1
        self._objects[handle.id] = obj
        self._owner[handle.id] = owner
        self.space.add(obj)
        if isinstance(handle, BodyHandle):
            self._body_members[handle.id] = set()
        if body is not None:
            self.resolve(owner, body)
            self._body_members.setdefault(body.id, set()).add(handle.id)
            self._body_for_object[handle.id] = body.id
        if isinstance(handle, ShapeHandle):
            self._shape_handles[obj] = handle
            self._shape_geometries[handle.id] = (obj.body, local_shape_geometry(obj))
            if obj.body.body_type == obj.body.STATIC:
                self._static_shape_bodies[handle.id] = obj.body
            else:
                points, radius = self._shape_geometries[handle.id][1]
                extent = max(math.hypot(x, y) for x, y in points) + radius
                self._body_geometry_radii[obj.body] = max(self._body_geometry_radii.get(obj.body, 0), extent)
        return handle

    def resolve(self, owner: int, handle):
        if self._owner.get(handle.id) != owner:
            raise PermissionError("tile does not own this resource")
        return self._objects[handle.id]

    def on_contact(self, owner: int, handle: ShapeHandle, callbacks: ContactCallbacks) -> None:
        shape = self.resolve(owner, handle)
        shape.collision_type = TILE_SENSOR_COLLISION_TYPE
        self._callbacks[shape] = callbacks

    @staticmethod
    def _number(value, name: str, *, minimum=None, maximum=None) -> float:
        import math
        value = float(value)
        if not math.isfinite(value) or (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
            bounds = f" from {minimum}" if maximum is None else f" from {minimum} to {maximum}"
            raise ValueError(f"{name} must be finite and{bounds}")
        return value

    def set_shape_material(self, owner: int, handle, *, friction=None, elasticity=None):
        shape = self.resolve(owner, handle)
        if friction is not None:
            shape.friction = self._number(friction, "friction", minimum=0)
        if elasticity is not None:
            shape.elasticity = self._number(elasticity, "elasticity", minimum=0, maximum=1)

    def set_body_position(self, owner: int, handle, position):
        body = self.resolve(owner, handle)
        x, y = map(float, position)
        ox, oy = self._origins[owner]
        check_bounds(points_bounds(((x, y),)), label="set_position")
        previous = body.position
        body.position = ox + x, oy + y
        try:
            self._check_body_shapes(owner, handle)
        except Exception:
            body.position = previous
            raise

    def _check_body_shapes(self, owner, handle):
        for key in self._body_members.get(handle.id, ()):
            obj = self._objects[key]
            if obj in self._shape_handles:
                check_bounds(shape_bounds(obj, self._origins[owner]),
                             label=f"{type(obj).__name__} #{key}, tile {owner}", owner=owner, object_id=key)

    def body_position(self, owner: int, handle) -> Point:
        body = self.resolve(owner, handle); ox, oy = self._origins[owner]
        return Vec2d(float(body.position.x - ox), float(body.position.y - oy))

    def body_velocity(self, owner: int, handle) -> Vector:
        body = self.resolve(owner, handle)
        return Vec2d(float(body.velocity.x), float(body.velocity.y))

    def body_angle(self, owner: int, handle) -> float:
        return float(self.resolve(owner, handle).angle)

    def body_angular_velocity(self, owner: int, handle) -> float:
        return float(self.resolve(owner, handle).angular_velocity)

    def set_body_velocity(self, owner: int, handle, velocity):
        body = self.resolve(owner, handle)
        body.velocity = tuple(map(float, velocity))

    def set_body_angle(self, owner: int, handle, angle):
        body = self.resolve(owner, handle)
        previous = body.angle
        body.angle = self._number(angle, "angle")
        try:
            self._check_body_shapes(owner, handle)
        except Exception:
            body.angle = previous
            raise

    def set_body_angular_velocity(self, owner: int, handle, velocity):
        self.resolve(owner, handle).angular_velocity = self._number(velocity, "angular velocity")

    def apply_body_force(self, owner: int, handle, force, point):
        body = self.resolve(owner, handle)
        body.apply_force_at_local_point(tuple(map(float, force)), tuple(map(float, point)))

    def apply_body_impulse(self, owner: int, handle, impulse, point):
        body = self.resolve(owner, handle)
        body.apply_impulse_at_local_point(tuple(map(float, impulse)), tuple(map(float, point)))

    def apply_body_torque(self, owner: int, handle, torque):
        body = self.resolve(owner, handle)
        body.torque += self._number(torque, "torque")

    def set_motor(self, owner: int, handle, *, rate=None, max_force=None):
        motor = self.resolve(owner, handle)
        if rate is not None: motor.rate = self._number(rate, "rate")
        if max_force is not None: motor.max_force = self._number(max_force, "max_force", minimum=0)

    def _resource_group(self, resource_id: int) -> set[int]:
        group = {resource_id, *self._body_members.get(resource_id, ())}
        for cid, endpoints in self._constraint_endpoints.items():
            if endpoints & group:
                group.add(cid)
        return group

    @staticmethod
    def _removal_priority(obj) -> int:
        import pymunk
        if isinstance(obj, pymunk.Constraint): return 0
        if isinstance(obj, pymunk.Shape): return 1
        if isinstance(obj, pymunk.Body): return 2
        return 3

    def pause_resource(self, owner: int, handle) -> None:
        self.resolve(owner, handle)
        group = self._resource_group(handle.id)
        if group & self._paused_resources:
            raise RuntimeError("object or one of its dependencies is already paused")
        pinned = {cid for ids in self._ball_constraints.values() for cid in ids}
        if group & pinned:
            raise RuntimeError("object pins a ball; remove the pin before pausing")
        removable = [key for key in group if key not in self._visuals.get(owner, ())]
        try:
            for key in sorted(removable, key=lambda item: self._removal_priority(self._objects[item])):
                self.space.remove(self._objects[key])
        except Exception as exc:
            raise RuntimeError("object cannot be paused independently") from exc
        self._paused_resources.update(group)
        self._resource_resumes.pop(handle.id, None)
        self._visual_revisions[owner] = self._visual_revisions.get(owner, 0) + 1
        self._emit_scene("visual", owner)

    def resume_resource(self, owner: int, handle, *, delay=0) -> None:
        self.resolve(owner, handle)
        parent = self._body_for_object.get(handle.id)
        if parent is not None and parent in self._paused_resources:
            raise RuntimeError("resume the paused body rather than one of its dependencies")
        if handle.id not in self._paused_resources or handle.id in self._resource_resumes:
            raise RuntimeError("object is not paused or already scheduled to resume")
        delay = self._number(delay, "delay", minimum=0)
        if delay:
            self._resource_resumes[handle.id] = delay
        else:
            self._restore_resource(owner, handle.id)

    def _restore_resource(self, owner: int, resource_id: int) -> None:
        group = self._resource_group(resource_id)
        restorable = [key for key in group if key not in self._visuals.get(owner, ())]
        for key in sorted(restorable, key=lambda item: -self._removal_priority(self._objects[item])):
            self.space.add(self._objects[key])
        self._paused_resources.difference_update(group)
        self._resource_resumes.pop(resource_id, None)
        self._visual_revisions[owner] = self._visual_revisions.get(owner, 0) + 1
        self._emit_scene("visual", owner)

    def set_style(self, owner: int, handle, *, fill_color=_UNSET, stroke_color=_UNSET):
        obj = self.resolve(owner, handle)
        style = self._styles.get(handle.id)
        if style is None:
            raise TypeError("resource has no visual style")
        changed = False
        if fill_color is not _UNSET:
            value = _validate_color(fill_color)
            if style.fill_color != value: style.fill_color = value; changed = True
        if stroke_color is not _UNSET:
            value = _validate_color(stroke_color)
            if style.stroke_color != value: style.stroke_color = value; changed = True
        if changed:
            if isinstance(obj, VisualSegment) and obj.dynamic:
                self._emit_scene("dynvisual", owner)
            else:
                self._visual_revisions[owner] = self._visual_revisions.get(owner, 0) + 1
                self._emit_scene("visual", owner)

    def add_visual(self, owner: int, visual: Any, fill_color: Color | None, stroke_color: Color | None, foreground: bool = False):
        if isinstance(visual, VisualPolygon):
            bounds = points_bounds(visual.points, visual.radius)
        else:
            bounds = points_bounds((visual.a, visual.b), visual.radius)
        check_bounds(bounds,
                     label=f"{type(visual).__name__} #{self._next}, tile {owner}", owner=owner, object_id=self._next)
        handle = VisualHandle(self._next, owner, self)
        self._next += 1
        self._objects[handle.id] = visual
        self._owner[handle.id] = owner
        self._styles[handle.id] = VisualStyle(_validate_color(fill_color), _validate_color(stroke_color), _validate_flag(foreground, "foreground"))
        self._visuals.setdefault(owner, []).append(handle.id)
        self._emit_scene("visual", owner)
        return handle

    def set_object_style(self, handle, fill_color: Color | None, stroke_color: Color | None, foreground: bool = False):
        self._styles[handle.id] = VisualStyle(_validate_color(fill_color), _validate_color(stroke_color), _validate_flag(foreground, "foreground"))

    def set_visual_segment_points(self, owner: int, handle, a, b) -> None:
        visual = self.resolve(owner, handle)
        if not isinstance(visual, VisualSegment):
            raise TypeError("resource is not a visual segment")
        points = [tuple(map(float, point)) for point in (a, b)]
        check_bounds(points_bounds(points, visual.radius),
                     label=f"VisualSegment #{handle.id}, tile {owner}", owner=owner, object_id=handle.id)
        self._objects[handle.id] = VisualSegment(points[0], points[1], visual.radius, visual.dynamic)
        self._checked_visuals[handle.id] = self._objects[handle.id]
        if visual.dynamic:
            self._emit_scene("dynvisual", owner)
        else:
            self._visual_revisions[owner] = self._visual_revisions.get(owner, 0) + 1
            self._emit_scene("visual", owner)

    def visual_items(self, owner: int):
        result = []
        for key, value in self._owner.items():
            if value == owner and key in self._styles and key not in self._paused_resources:
                result.append((self._objects[key], self._styles[key]))
        return result

    def visual_revision(self, owner: int):
        return self._visual_revisions.get(owner, 0)

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
            self._static_shape_bodies.pop(key, None)
            self._shape_geometries.pop(key, None)
            self._body_geometry_radii.pop(obj, None)
            self._checked_static_poses.pop(key, None)
            self._checked_visuals.pop(key, None)
            self._owner.pop(key, None)
            self._styles.pop(key, None)
            self._paused_resources.discard(key)
            self._resource_resumes.pop(key, None)
            body_id = self._body_for_object.pop(key, None)
            if body_id is not None: self._body_members.get(body_id, set()).discard(key)
            self._body_members.pop(key, None)
        self._visuals.pop(owner, None)
        self._visual_revisions.pop(owner, None)
        self._origins.pop(owner, None)
        for record in self._balls.values():
            if record.get("owner") == owner:
                self._release_ball(record)

    def owned_objects(self, owner: int):
        return [self._objects[key] for key, value in self._owner.items() if value == owner]

    def owned_visuals(self, owner: int):
        return [self._objects[key] for key in self._visuals.get(owner, ()) if key in self._objects]

    def _claim_ball(self, owner: int, body, shape) -> BallHandle:
        record = self._balls.get(body)
        if record is None:
            record = {"body": body, "shape": shape, "owner": None, "generation": 0, "paused": False, "resume": None}
            self._balls[body] = record
        if record["owner"] is None:
            record["owner"] = owner
            record["generation"] += 1
            record["snapshot"] = (
                float(shape.friction), float(shape.elasticity),
                getattr(shape, "ebm_fill_color", DEFAULT_BALL_FILL),
                getattr(shape, "ebm_stroke_color", DEFAULT_BALL_STROKE),
                shape.filter,
            )
        return BallHandle(owner, self, body, record["generation"])

    def _ball_record(self, handle: BallHandle):
        record = self._balls.get(handle._body)
        if record is None or record["owner"] != handle._owner or record["generation"] != handle._generation:
            raise PermissionError("ball is no longer owned by this tile")
        return record

    def _ball_point(self, handle: BallHandle, position):
        record = self._ball_record(handle)
        x, y = map(float, position)
        radius = float(record["shape"].radius)
        if not (radius <= x <= TILE_SIZE - radius and radius <= y <= TILE_SIZE - radius):
            raise ValueError("the complete ball must remain inside the tile")
        ox, oy = self._origins[handle._owner]
        return record, (ox + x, oy + y)

    def ball_position(self, handle):
        record = self._ball_record(handle); ox, oy = self._origins[handle._owner]
        return Vec2d(float(record["body"].position.x - ox), float(record["body"].position.y - oy))

    def ball_velocity(self, handle):
        body = self._ball_record(handle)["body"]
        return Vec2d(float(body.velocity.x), float(body.velocity.y))

    def ball_radius(self, handle):
        return float(self._ball_record(handle)["shape"].radius)

    def ball_paused(self, handle):
        return bool(self._ball_record(handle)["paused"])

    def set_ball_style(self, handle, *, fill_color=_UNSET, stroke_color=_UNSET):
        record = self._ball_record(handle); shape = record["shape"]
        if fill_color is not _UNSET: shape.ebm_fill_color = _validate_color(fill_color)
        if stroke_color is not _UNSET: shape.ebm_stroke_color = _validate_color(stroke_color)
        self._emit_scene("ball", record["body"].id)

    def set_ball_material(self, handle, *, friction=None, elasticity=None):
        record = self._ball_record(handle); shape = record["shape"]
        if friction is not None: shape.friction = self._number(friction, "friction", minimum=0)
        if elasticity is not None: shape.elasticity = self._number(elasticity, "elasticity", minimum=0, maximum=1)

    def set_ball_position(self, handle, position):
        record, world = self._ball_point(handle, position); record["body"].position = world

    def set_ball_velocity(self, handle, velocity):
        record = self._ball_record(handle); record["body"].velocity = tuple(map(float, velocity))

    def pause_ball(self, handle):
        record = self._ball_record(handle)
        if record["paused"]:
            raise RuntimeError("ball is already paused")
        if record["body"] in self._ball_constraints:
            raise RuntimeError("ball is pinned; remove the pin before pausing it")
        # Contact can begin while an incoming ball still straddles a port edge.
        # Ownership already prevents another tile from claiming it, so allow
        # capture as long as some part of the ball overlaps this tile.
        x, y = self.ball_position(handle)
        radius = float(record["shape"].radius)
        if not (-radius < x < TILE_SIZE + radius and -radius < y < TILE_SIZE + radius):
            raise ValueError("ball must overlap the tile before it can be paused")
        self.space.remove(record["shape"], record["body"])
        record["paused"] = True; record["resume"] = None
        self._emit_scene("ball", record["body"].id)

    def resume_ball(self, handle, *, delay=0):
        record = self._ball_record(handle)
        if not record["paused"] or record["resume"] is not None:
            raise RuntimeError("ball is not paused or already scheduled to resume")
        # A captured boundary ball must be moved wholly inside before release.
        self._ball_point(handle, self.ball_position(handle))
        delay = self._number(delay, "delay", minimum=0)
        if delay: record["resume"] = delay
        else: self._restore_ball(record)

    def _restore_ball(self, record):
        self.space.add(record["body"], record["shape"])
        record["paused"] = False; record["resume"] = None
        self._emit_scene("ball", record["body"].id)

    def _release_ball(self, record):
        body = record["body"]
        self._drop_ball_constraints(body)
        group = self._filter_groups.pop(body, None)
        if group is not None:
            members = self._filter_group_members.get(group)
            if members is not None:
                members.discard(body)
        if record["paused"]:
            self._restore_ball(record)
        friction, elasticity, fill, stroke, shape_filter = record["snapshot"]
        shape = record["shape"]
        shape.friction, shape.elasticity = friction, elasticity
        shape.ebm_fill_color, shape.ebm_stroke_color = fill, stroke
        shape.filter = shape_filter
        record["owner"] = None; record["generation"] += 1
        self._emit_scene("ball", record["body"].id)

    def ball_is_paused(self, body) -> bool:
        record = self._balls.get(body)
        return bool(record and record["paused"])

    def _pin_body(self, owner: int, handle):
        """Resolve a BodyHandle or an owned BallHandle to its raw pymunk body."""
        if isinstance(handle, BallHandle):
            return self._ball_record(handle)["body"]
        return self.resolve(owner, handle)

    def _track_ball_constraint(self, handle: BallHandle, constraint_id: int) -> None:
        record = self._ball_record(handle)
        self._ball_constraints.setdefault(record["body"], []).append(constraint_id)

    def _drop_ball_constraints(self, body) -> None:
        """Break every pin holding this ball (handoff, teardown, ball removal)."""
        for resource_id in self._ball_constraints.pop(body, ()):
            self._purge_resource(resource_id)

    @staticmethod
    def _set_shape_group(shape, group: int) -> None:
        import pymunk
        current = shape.filter
        shape.filter = pymunk.ShapeFilter(group=group, categories=current.categories, mask=current.mask)

    def _merge_filter_group(self, bodies) -> None:
        """Put all given bodies into one collision group so they never collide.

        Merging is transitive: pinning link1-link2 and then link2-link3 leaves
        the whole chain in a single group.
        """
        groups = {self._filter_groups[body] for body in bodies if body in self._filter_groups}
        if groups:
            target = min(groups)
        else:
            target = self._next_filter_group
            self._next_filter_group += 1
        members = set(bodies)
        for old in groups - {target}:
            members |= self._filter_group_members.pop(old, set())
        self._filter_group_members.setdefault(target, set()).update(members)
        for body in members:
            self._filter_groups[body] = target
            for shape in body.shapes:
                self._set_shape_group(shape, target)

    def remove_resource(self, owner: int, handle) -> None:
        """Remove an owned resource and its bookkeeping; the handle is dead afterwards."""
        self.resolve(owner, handle)
        for body, ids in list(self._ball_constraints.items()):
            if handle.id in ids:
                ids.remove(handle.id)
                if not ids:
                    del self._ball_constraints[body]
        self._purge_resource(handle.id)

    def _purge_resource(self, resource_id: int) -> None:
        obj = self._objects.pop(resource_id, None)
        if obj is None:
            return
        self._owner.pop(resource_id, None)
        try:
            self.space.remove(obj)
        except Exception:
            pass
        self._callbacks.pop(obj, None)
        self._shape_handles.pop(obj, None)
        self._static_shape_bodies.pop(resource_id, None)
        self._shape_geometries.pop(resource_id, None)
        self._checked_static_poses.pop(resource_id, None)
        self._checked_visuals.pop(resource_id, None)
        self._styles.pop(resource_id, None)
        self._paused_resources.discard(resource_id)
        self._resource_resumes.pop(resource_id, None)
        self._constraint_endpoints.pop(resource_id, None)
        body_id = self._body_for_object.pop(resource_id, None)
        if body_id is not None:
            members = self._body_members.get(body_id)
            if members is not None:
                members.discard(resource_id)
        self._body_members.pop(resource_id, None)

    def advance(self, dt: float) -> None:
        dt = max(0.0, float(dt))
        for resource_id, remaining in list(self._resource_resumes.items()):
            remaining -= dt
            if remaining <= 0:
                self._restore_resource(self._owner[resource_id], resource_id)
            else:
                self._resource_resumes[resource_id] = remaining
        for record in list(self._balls.values()):
            if record["paused"]:
                if record["resume"] is not None:
                    record["resume"] -= dt
                    if record["resume"] <= 0: self._restore_ball(record)
                continue
            owner = record["owner"]
            if owner is None: continue
            ox, oy = self._origins.get(owner, (0, 0)); x, y = record["body"].position; radius = float(record["shape"].radius)
            # Handoff happens when the complete ball has crossed a tile edge,
            # matching the flow validator's geometry-based boundary rule.
            if x + radius <= ox or x - radius >= ox + TILE_SIZE or y + radius <= oy or y - radius >= oy + TILE_SIZE:
                self._release_ball(record)

class TileBuilder:
    """Tile-local, ownership-checked construction API; exposes no Space."""

    def __init__(self, registry: TileResourceRegistry, owner: int, origin: Point):
        self._registry = registry
        self._owner = owner
        self.origin = origin
        self._registry.register_owner(owner, origin)

    def _point(self, point):
        x, y = map(float, point)
        check_bounds(points_bounds(((x, y),)), label="tile point")
        return self.origin[0] + x, self.origin[1] + y

    def static_segment(self, a: Point, b: Point, radius: float = 2, *, friction: float = .8, elasticity: float = .2, surface_velocity: Vector = (0, 0), fill_color: Color | None = DEFAULT_SEGMENT_FILL, stroke_color: Color | None = DEFAULT_SEGMENT_STROKE, foreground: bool = False) -> ShapeHandle:
        """Build a fixed physical rail from local point a to b; return its ShapeHandle.

        foreground=True draws the shape after balls, so it can occlude them."""
        import pymunk

        radius = radius_value(radius, maximum=MAX_SHAPE_RADIUS)
        check_bounds(points_bounds((a, b), radius), label="static_segment")
        shape = pymunk.Segment(self._registry.space.static_body, self._point(a), self._point(b), radius)
        shape.friction, shape.elasticity = friction, elasticity
        shape.surface_velocity = surface_velocity
        handle = self._registry.add(self._owner, shape, ShapeHandle)
        self._registry.set_object_style(handle, fill_color, stroke_color, foreground)
        return handle

    def static_circle(self, center: Point, radius: float, *, friction: float = .4, elasticity: float = .75, fill_color: Color | None = DEFAULT_CIRCLE_FILL, stroke_color: Color | None = DEFAULT_CIRCLE_STROKE, foreground: bool = False) -> ShapeHandle:
        """Build a fixed physical circle in local coordinates; return its ShapeHandle. foreground=True draws it after balls."""
        import pymunk

        radius = radius_value(radius)
        x, y = map(float, center)
        check_bounds(points_bounds(((x, y),), radius), label="static_circle")
        body = pymunk.Body(body_type=pymunk.Body.STATIC); body.position = self._point(center)
        body_handle = self._registry.add(self._owner, body, BodyHandle)
        shape = pymunk.Circle(body, radius); shape.friction, shape.elasticity = friction, elasticity
        handle = self._registry.add(self._owner, shape, ShapeHandle)
        self._registry.set_object_style(handle, fill_color, stroke_color, foreground)
        return handle

    def static_polygon(self, points: list[Point] | tuple[Point, ...], *, radius: float = 0, friction: float = .8, elasticity: float = .2, fill_color: Color | None = DEFAULT_SEGMENT_FILL, stroke_color: Color | None = DEFAULT_SEGMENT_STROKE, foreground: bool = False) -> ShapeHandle:
        """Build a fixed convex polygon from tile-local points. foreground=True draws it after balls."""
        import pymunk

        local = self._polygon_points(points, radius)
        shape = pymunk.Poly(self._registry.space.static_body, [self._point(point) for point in local], radius=radius)
        shape.friction, shape.elasticity = friction, elasticity
        handle = self._registry.add(self._owner, shape, ShapeHandle)
        self._registry.set_object_style(handle, fill_color, stroke_color, foreground)
        return handle

    def static_box(self, left: float, top: float, right: float, bottom: float, *, radius: float = 0, friction: float = .8, elasticity: float = .2, fill_color: Color | None = DEFAULT_SEGMENT_FILL, stroke_color: Color | None = DEFAULT_SEGMENT_STROKE, foreground: bool = False) -> ShapeHandle:
        """Build a fixed physical rectangle from tile-local extents; return its ShapeHandle. foreground=True draws it after balls."""
        return self.static_polygon(
            ((left, top), (right, top), (right, bottom), (left, bottom)),
            radius=radius, friction=friction, elasticity=elasticity,
            fill_color=fill_color, stroke_color=stroke_color, foreground=foreground,
        )

    def dynamic_body(self, position: Point, *, angle: float = 0) -> BodyHandle:
        """Create a dynamic body; attach one or more shapes to define its mass."""
        import pymunk

        body = pymunk.Body()
        body.position = self._point(position)
        body.angle = self._registry._number(angle, "angle")
        return self._registry.add(self._owner, body, BodyHandle)

    def kinematic_body(self, position: Point, *, angle: float = 0) -> BodyHandle:
        """Create an externally driven body for a continuously powered mechanism."""
        import pymunk

        body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        body.position = self._point(position)
        body.angle = self._registry._number(angle, "angle")
        return self._registry.add(self._owner, body, BodyHandle)

    def circle_shape(self, body: BodyHandle, center: Point, radius: float, *, density: float = .01, friction: float = .8, elasticity: float = .2, fill_color: Color | None = DEFAULT_CIRCLE_FILL, stroke_color: Color | None = DEFAULT_CIRCLE_STROKE, foreground: bool = False) -> ShapeHandle:
        """Attach a physical circle to a body using body-local coordinates. foreground=True draws it after balls."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        radius = radius_value(radius)
        points_bounds((center,))
        shape = pymunk.Circle(raw, radius, tuple(map(float, center)))
        return self._add_attached_shape(body, shape, density, friction, elasticity, fill_color, stroke_color, foreground)

    def segment_shape(self, body: BodyHandle, a: Point, b: Point, radius: float = 2, *, density: float = .01, friction: float = .8, elasticity: float = .2, surface_velocity: Vector = (0, 0), fill_color: Color | None = DEFAULT_SEGMENT_FILL, stroke_color: Color | None = DEFAULT_SEGMENT_STROKE, foreground: bool = False) -> ShapeHandle:
        """Attach a physical segment to a body using body-local coordinates. foreground=True draws it after balls."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        radius = radius_value(radius, maximum=MAX_SHAPE_RADIUS)
        a, b = tuple(map(float, a)), tuple(map(float, b))
        points_bounds((a, b))
        shape = pymunk.Segment(raw, a, b, radius); shape.surface_velocity = tuple(map(float, surface_velocity))
        return self._add_attached_shape(body, shape, density, friction, elasticity, fill_color, stroke_color, foreground)

    def polygon_shape(self, body: BodyHandle, points: list[Point] | tuple[Point, ...], *, radius: float = 0, density: float = .01, friction: float = .8, elasticity: float = .2, fill_color: Color | None = DEFAULT_SEGMENT_FILL, stroke_color: Color | None = DEFAULT_SEGMENT_STROKE, foreground: bool = False) -> ShapeHandle:
        """Attach a convex polygon to a body using body-local points. foreground=True draws it after balls."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        local = self._polygon_points(points, radius)
        shape = pymunk.Poly(raw, local, radius=radius)
        return self._add_attached_shape(body, shape, density, friction, elasticity, fill_color, stroke_color, foreground)

    def box_shape(self, body: BodyHandle, left: float, top: float, right: float, bottom: float, *, radius: float = 0, density: float = .01, friction: float = .8, elasticity: float = .2, fill_color: Color | None = DEFAULT_SEGMENT_FILL, stroke_color: Color | None = DEFAULT_SEGMENT_STROKE, foreground: bool = False) -> ShapeHandle:
        """Attach a physical rectangle to a body using body-local extents. foreground=True draws it after balls."""
        return self.polygon_shape(
            body, ((left, top), (right, top), (right, bottom), (left, bottom)),
            radius=radius, density=density, friction=friction, elasticity=elasticity,
            fill_color=fill_color, stroke_color=stroke_color, foreground=foreground,
        )

    def pivot(self, a: BodyHandle | BallHandle, b: BodyHandle | BallHandle | Point, point: Point | None = None, *, collide: bool = False) -> ConstraintHandle:
        """Pin bodies and owned balls together at a pivot point.

        pivot(body, anchor) pins a body to the static world at a tile-local point.
        pivot(a, b, point) pins two owned bodies (or balls) so the given tile-local
        point stays coincident on both — chain such pins to build ropes.
        pivot(body, ball) without a point glues the ball where it is: the ball's
        center is pinned at its current position relative to the other body, with
        no visible jump. With a point, the ball's center snaps to that tile-local
        point instead. collide=False (default) merges the pair into a shared
        collision group so jointed bodies never collide; chaining pins extends the
        group transitively. builder.remove(handle) detaches the pair.
        """
        import pymunk

        registry = self._registry
        if not isinstance(b, (BodyHandle, BallHandle)):
            if point is not None:
                raise ValueError("point is only valid when pinning two handles")
            if collide:
                raise ValueError("collide only applies when pinning two handles")
            raw = registry.resolve(self._owner, a)
            constraint = pymunk.PivotJoint(registry.space.static_body, raw, self._point(b))
            return registry.add(self._owner, constraint, ConstraintHandle, body=a)
        if not isinstance(a, (BodyHandle, BallHandle)):
            raise TypeError("pivot expects handles or a tile-local anchor point")
        raw_a = registry._pin_body(self._owner, a)
        raw_b = registry._pin_body(self._owner, b)
        if raw_a is raw_b:
            raise ValueError("cannot pin a body to itself")
        balls = [side for side in (a, b) if isinstance(side, BallHandle)]
        if point is None:
            if len(balls) != 1:
                raise ValueError("point is required unless exactly one side is a ball")
            ball_raw, other_raw = (raw_a, raw_b) if isinstance(a, BallHandle) else (raw_b, raw_a)
            anchor_ball, anchor_other = (0.0, 0.0), other_raw.world_to_local(ball_raw.position)
            anchors = (anchor_ball, anchor_other) if isinstance(a, BallHandle) else (anchor_other, anchor_ball)
            constraint = pymunk.PivotJoint(raw_a, raw_b, *anchors)
        elif len(balls) == 1:
            # Snap glue: the ball's center is pulled onto the given point.
            world = self._point(point)
            ball_raw, other_raw = (raw_a, raw_b) if isinstance(a, BallHandle) else (raw_b, raw_a)
            anchor_ball, anchor_other = (0.0, 0.0), other_raw.world_to_local(world)
            anchors = (anchor_ball, anchor_other) if isinstance(a, BallHandle) else (anchor_other, anchor_ball)
            constraint = pymunk.PivotJoint(raw_a, raw_b, *anchors)
        else:
            constraint = pymunk.PivotJoint(raw_a, raw_b, self._point(point))
        if not collide:
            registry._merge_filter_group((raw_a, raw_b))
        parent = a if isinstance(a, BodyHandle) else (b if isinstance(b, BodyHandle) else None)
        handle = registry.add(self._owner, constraint, ConstraintHandle, body=parent)
        registry._constraint_endpoints[handle.id] = {side.id for side in (a, b) if isinstance(side, BodyHandle)}
        for side in balls:
            registry._track_ball_constraint(side, handle.id)
        return handle

    def spring(self, body: BodyHandle, anchor: Point, attachment: Point, *, rest_length: float, stiffness: float, damping: float) -> ConstraintHandle:
        """Suspend a body from a tile-local anchor; attachment is body-local. No collision geometry is created."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        attachment = tuple(map(float, attachment))
        points_bounds((attachment,))
        world = raw.local_to_world(attachment)
        self._point((world.x - self.origin[0], world.y - self.origin[1]))
        number = self._registry._number
        constraint = pymunk.DampedSpring(
            self._registry.space.static_body, raw, self._point(anchor), attachment,
            number(rest_length, "rest length", minimum=0),
            number(stiffness, "stiffness", minimum=0),
            number(damping, "damping", minimum=0),
        )
        return self._registry.add(self._owner, constraint, ConstraintHandle, body=body)

    def rope(self, body: BodyHandle, anchor: Point, attachment: Point, *, max_length: float) -> ConstraintHandle:
        """Limit distance to a tile-local anchor, allowing slack. Attachment is body-local; no rope collider is created."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        attachment = tuple(map(float, attachment))
        points_bounds((attachment,))
        world = raw.local_to_world(attachment)
        self._point((world.x - self.origin[0], world.y - self.origin[1]))
        constraint = pymunk.SlideJoint(
            self._registry.space.static_body, raw, self._point(anchor), attachment,
            0, self._registry._number(max_length, "maximum rope length", minimum=0),
        )
        return self._registry.add(self._owner, constraint, ConstraintHandle, body=body)

    def sensor_segment(self, a: Point, b: Point, radius: float = 2, *, body: BodyHandle | None = None) -> ShapeHandle:
        """Build an invisible, massless, non-colliding segment sensor; tile-local, or body-local when body is given."""
        import pymunk

        radius = radius_value(radius, maximum=MAX_SHAPE_RADIUS)
        if body is None:
            check_bounds(points_bounds((a, b), radius), label="sensor_segment")
            raw = self._registry.space.static_body
            a, b = self._point(a), self._point(b)
        else:
            raw = self._registry.resolve(self._owner, body)
            a, b = tuple(map(float, a)), tuple(map(float, b))
            points_bounds((a, b))
        return self._add_sensor(pymunk.Segment(raw, a, b, radius), body)

    def sensor_circle(self, center: Point, radius: float, *, body: BodyHandle | None = None) -> ShapeHandle:
        """Build an invisible, massless, non-colliding circular sensor; tile-local, or body-local when body is given."""
        import pymunk

        radius = radius_value(radius)
        if body is None:
            x, y = map(float, center)
            check_bounds(points_bounds(((x, y),), radius), label="sensor_circle")
            raw = self._registry.space.static_body
            offset = self._point(center)
        else:
            raw = self._registry.resolve(self._owner, body)
            offset = tuple(map(float, center))
            points_bounds((offset,))
        return self._add_sensor(pymunk.Circle(raw, radius, offset), body)

    def sensor_polygon(self, points: list[Point] | tuple[Point, ...], *, radius: float = 0, body: BodyHandle | None = None) -> ShapeHandle:
        """Build an invisible, massless, non-colliding convex sensor; tile-local, or body-local when body is given."""
        import pymunk

        local = self._polygon_points(points, radius)
        if body is None:
            raw = self._registry.space.static_body
            local = [self._point(point) for point in local]
        else:
            raw = self._registry.resolve(self._owner, body)
        return self._add_sensor(pymunk.Poly(raw, local, radius=radius), body)

    def sensor_box(self, left: float, top: float, right: float, bottom: float, *, body: BodyHandle | None = None) -> ShapeHandle:
        """Build an invisible, massless, non-colliding rectangular sensor; tile-local, or body-local when body is given."""
        return self.sensor_polygon(((left, top), (right, top), (right, bottom), (left, bottom)), body=body)

    def _add_sensor(self, shape, body: BodyHandle | None) -> ShapeHandle:
        shape.sensor = True
        shape.ebm_hidden = True
        return self._registry.add(self._owner, shape, ShapeHandle, body=body)

    def motor(self, body: BodyHandle, *, rate: float, max_force: float) -> MotorHandle:
        """Drive a body relative to the static world at a target angular rate."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        constraint = pymunk.SimpleMotor(self._registry.space.static_body, raw, self._registry._number(rate, "rate"))
        constraint.max_force = self._registry._number(max_force, "max_force", minimum=0)
        return self._registry.add(self._owner, constraint, MotorHandle, body=body)

    def _polygon_points(self, points, radius):
        radius_value(radius, maximum=MAX_SHAPE_RADIUS)
        local = [tuple(map(float, point)) for point in points]
        if len(local) < 3: raise ValueError("polygon needs at least three points")
        points_bounds(local)
        return local

    def _add_attached_shape(self, body, shape, density, friction, elasticity, fill_color, stroke_color, foreground=False):
        # Reject before density can change the compound body's mass/centre.
        check_bounds(shape_bounds(shape, self.origin), label=f"{type(shape).__name__} on body #{body.id}", owner=self._owner)
        shape.density = self._registry._number(density, "density", minimum=0)
        if shape.density == 0: raise ValueError("density must be greater than zero")
        shape.friction = self._registry._number(friction, "friction", minimum=0)
        shape.elasticity = self._registry._number(elasticity, "elasticity", minimum=0, maximum=1)
        raw_body = self._registry.resolve(self._owner, body)
        authored_position = raw_body.position
        handle = self._registry.add(self._owner, shape, ShapeHandle, body=body)
        self._registry.set_object_style(handle, fill_color, stroke_color, foreground)
        # Pymunk updates center of gravity as density-backed shapes are added.
        # Keep the contributor-facing body origin fixed while assembling it.
        raw_body.position = authored_position
        return handle

    def on_ball_contact(
        self,
        shape: ShapeHandle,
        *,
        begin: CollisionCallback | None = None,
        pre_solve: CollisionCallback | None = None,
        post_solve: ContactCallback | None = None,
        separate: ContactCallback | None = None,
    ) -> None:
        """Register Pymunk-style contact phases for balls touching an owned shape."""
        callbacks = ContactCallbacks(begin, pre_solve, post_solve, separate)
        if not any((begin, pre_solve, post_solve, separate)):
            raise ValueError("at least one contact callback is required")
        self._registry.on_contact(self._owner, shape, callbacks)

    def visual_segment(self, a: Point, b: Point, radius: float = 6, *, fill_color: Color | None = DEFAULT_SEGMENT_FILL, stroke_color: Color | None = DEFAULT_SEGMENT_STROKE, dynamic: bool = False, foreground: bool = False) -> VisualHandle:
        """Build a non-physical line. Use dynamic=True for moving cords, drawn without rebuilding the static tile cache.

        foreground=True draws the segment after balls, so it can occlude them."""
        # Visual-only primitives are owned and bounds-checked but never added to
        # Pymunk, so reference graphics cannot interfere with ball routing.
        _validate_flag(dynamic, "dynamic")
        _validate_flag(foreground, "foreground")
        local_a=(float(a[0]),float(a[1]));local_b=(float(b[0]),float(b[1]))
        return self._registry.add_visual(self._owner,VisualSegment(local_a,local_b,radius_value(radius),dynamic),fill_color,stroke_color,foreground)

    def visual_polygon(self, points: list[Point] | tuple[Point, ...], *, radius: float = 0, fill_color: Color | None = DEFAULT_SEGMENT_FILL, stroke_color: Color | None = DEFAULT_SEGMENT_STROKE, foreground: bool = False) -> VisualHandle:
        """Build a non-physical filled convex polygon from tile-local points.

        foreground=True draws the polygon after balls, so it can occlude them;
        a foreground plate is how a tile hides balls inside a housing."""
        local = self._polygon_points(points, radius)
        _validate_flag(foreground, "foreground")
        return self._registry.add_visual(self._owner, VisualPolygon(tuple(local), radius), fill_color, stroke_color, foreground)

    def visual_box(self, left: float, top: float, right: float, bottom: float, *, radius: float = 0, fill_color: Color | None = DEFAULT_SEGMENT_FILL, stroke_color: Color | None = DEFAULT_SEGMENT_STROKE, foreground: bool = False) -> VisualHandle:
        """Build a non-physical filled rectangle from tile-local extents; see visual_polygon."""
        return self.visual_polygon(
            ((left, top), (right, top), (right, bottom), (left, bottom)),
            radius=radius, fill_color=fill_color, stroke_color=stroke_color,
            foreground=foreground,
        )

    def remove(self, handle: ResourceHandle) -> None:
        """Remove an owned resource (e.g. a pin) from the simulation; the handle is dead afterwards."""
        self._registry.remove_resource(self._owner, handle)

    @property
    def visual_objects(self):
        return self._registry.owned_objects(self._owner) + self._registry.owned_visuals(self._owner)

    @property
    def visual_items(self):
        """Internal renderer view of (object, mutable style) pairs."""
        return self._registry.visual_items(self._owner)

    @property
    def visual_revision(self):
        return self._registry.visual_revision(self._owner)
