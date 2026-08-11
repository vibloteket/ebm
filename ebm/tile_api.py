from __future__ import annotations

from dataclasses import dataclass, field
import sys
import traceback
from typing import Any, Callable
from weakref import WeakKeyDictionary

from .ports import TILE_SIZE

BUILD_MARGIN = 20.0
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
    if not isinstance(color, (tuple, list)) or len(color) != 4:
        raise ValueError("color must be an RGBA tuple of four integers")
    if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255 for value in color):
        raise ValueError("RGBA color components must be integers from 0 to 255")
    return tuple(color)


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
    def set_fill_color(self, color: Color) -> None:
        """Set this object's fill RGBA tuple (four integers from 0 to 255)."""
        self._registry.set_style(self._owner, self, fill_color=color)

    def set_stroke_color(self, color: Color) -> None:
        """Set this object's outline RGBA tuple (four integers from 0 to 255)."""
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
        """Current tile-local body position."""
        return self._registry.body_position(self._owner, self)

    @property
    def velocity(self) -> Vector:
        """Current world-space linear velocity."""
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
    pass


@dataclass
class VisualStyle:
    fill_color: Color
    stroke_color: Color


@dataclass(frozen=True)
class VisualSegment:
    a: Point
    b: Point
    radius: float


@dataclass(frozen=True)
class BallHandle:
    """Tile-bound handle to one logical ball."""

    _owner: int = field(repr=False, compare=False)
    _registry: Any = field(repr=False, compare=False)
    _body: Any = field(repr=False)
    _generation: int = field(repr=False)

    @property
    def position(self) -> Point:
        """Current tile-local position."""
        return self._registry.ball_position(self)

    @property
    def velocity(self) -> Vector:
        """Current world-space velocity."""
        return self._registry.ball_velocity(self)

    @property
    def radius(self) -> float:
        """Ball radius."""
        return self._registry.ball_radius(self)

    @property
    def paused(self) -> bool:
        """Whether the ball is outside physics and normal rendering."""
        return self._registry.ball_paused(self)

    def set_fill_color(self, color: Color) -> None:
        self._registry.set_ball_style(self, fill_color=color)

    def set_stroke_color(self, color: Color) -> None:
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
        self._install_dispatcher()

    @classmethod
    def for_space(cls, space):
        registry = cls._by_space.get(space)
        if registry is None:
            registry = cls(space)
            cls._by_space[space] = registry
        return registry

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
            except Exception as error:
                # Never let an authoring error escape through CFFI as
                # "Exception ignored". Report it once through the normal
                # captured stderr stream and disable this registration.
                self._callbacks.pop(owned, None)
                arbiter.process_collision = False
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
                point = (
                    (float(contact.point_a.x) + float(contact.point_b.x)) / 2 - ox,
                    (float(contact.point_a.y) + float(contact.point_b.y)) / 2 - oy,
                )
        normal = (float(arbiter.normal.x), float(arbiter.normal.y))
        impulse = None
        kinetic_energy = None
        if phase == "post_solve":
            impulse = (float(arbiter.total_impulse.x), float(arbiter.total_impulse.y))
            kinetic_energy = float(arbiter.total_ke)
        return ContactEvent(handle, ball, point, normal, impulse, kinetic_energy)

    def register_owner(self, owner: int, origin: tuple[float, float]) -> None:
        self._origins[owner] = tuple(map(float, origin))

    def add(self, owner: int, obj: Any, handle_type, *, body: BodyHandle | None = None):
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
        body.position = ox + x, oy + y

    def body_position(self, owner: int, handle) -> Point:
        body = self.resolve(owner, handle); ox, oy = self._origins[owner]
        return float(body.position.x - ox), float(body.position.y - oy)

    def body_velocity(self, owner: int, handle) -> Vector:
        body = self.resolve(owner, handle)
        return float(body.velocity.x), float(body.velocity.y)

    def body_angle(self, owner: int, handle) -> float:
        return float(self.resolve(owner, handle).angle)

    def body_angular_velocity(self, owner: int, handle) -> float:
        return float(self.resolve(owner, handle).angular_velocity)

    def set_body_velocity(self, owner: int, handle, velocity):
        body = self.resolve(owner, handle)
        body.velocity = tuple(map(float, velocity))

    def set_body_angle(self, owner: int, handle, angle):
        self.resolve(owner, handle).angle = self._number(angle, "angle")

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
        if resource_id in self._body_members:
            return {resource_id, *self._body_members[resource_id]}
        return {resource_id}

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
        removable = [key for key in group if key not in self._visuals.get(owner, ())]
        try:
            for key in sorted(removable, key=lambda item: self._removal_priority(self._objects[item])):
                self.space.remove(self._objects[key])
        except Exception as exc:
            raise RuntimeError("object cannot be paused independently") from exc
        self._paused_resources.update(group)
        self._resource_resumes.pop(handle.id, None)
        self._visual_revisions[owner] = self._visual_revisions.get(owner, 0) + 1

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

    def set_style(self, owner: int, handle, *, fill_color=None, stroke_color=None):
        self.resolve(owner, handle)
        style = self._styles.get(handle.id)
        if style is None:
            raise TypeError("resource has no visual style")
        changed = False
        if fill_color is not None:
            value = _validate_color(fill_color)
            if style.fill_color != value: style.fill_color = value; changed = True
        if stroke_color is not None:
            value = _validate_color(stroke_color)
            if style.stroke_color != value: style.stroke_color = value; changed = True
        if changed:
            self._visual_revisions[owner] = self._visual_revisions.get(owner, 0) + 1

    def add_visual(self, owner: int, visual: Any, fill_color: Color, stroke_color: Color):
        handle = VisualHandle(self._next, owner, self)
        self._next += 1
        self._objects[handle.id] = visual
        self._owner[handle.id] = owner
        self._styles[handle.id] = VisualStyle(_validate_color(fill_color), _validate_color(stroke_color))
        self._visuals.setdefault(owner, []).append(handle.id)
        return handle

    def set_object_style(self, handle, fill_color: Color, stroke_color: Color):
        self._styles[handle.id] = VisualStyle(_validate_color(fill_color), _validate_color(stroke_color))

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
        return float(record["body"].position.x - ox), float(record["body"].position.y - oy)

    def ball_velocity(self, handle):
        body = self._ball_record(handle)["body"]
        return float(body.velocity.x), float(body.velocity.y)

    def ball_radius(self, handle):
        return float(self._ball_record(handle)["shape"].radius)

    def ball_paused(self, handle):
        return bool(self._ball_record(handle)["paused"])

    def set_ball_style(self, handle, *, fill_color=None, stroke_color=None):
        record = self._ball_record(handle); shape = record["shape"]
        if fill_color is not None: shape.ebm_fill_color = _validate_color(fill_color)
        if stroke_color is not None: shape.ebm_stroke_color = _validate_color(stroke_color)

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
        # Contact can begin while an incoming ball still straddles a port edge.
        # Ownership already prevents another tile from claiming it, so allow
        # capture as long as some part of the ball overlaps this tile.
        x, y = self.ball_position(handle)
        radius = float(record["shape"].radius)
        if not (-radius < x < TILE_SIZE + radius and -radius < y < TILE_SIZE + radius):
            raise ValueError("ball must overlap the tile before it can be paused")
        self.space.remove(record["shape"], record["body"])
        record["paused"] = True; record["resume"] = None

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

    def _release_ball(self, record):
        if record["paused"]:
            self._restore_ball(record)
        friction, elasticity, fill, stroke = record["snapshot"]
        shape = record["shape"]
        shape.friction, shape.elasticity = friction, elasticity
        shape.ebm_fill_color, shape.ebm_stroke_color = fill, stroke
        record["owner"] = None; record["generation"] += 1

    def ball_is_paused(self, body) -> bool:
        record = self._balls.get(body)
        return bool(record and record["paused"])

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
        if not (-BUILD_MARGIN <= x <= TILE_SIZE + BUILD_MARGIN and -BUILD_MARGIN <= y <= TILE_SIZE + BUILD_MARGIN):
            raise ValueError(f"point outside tile build bounds: {(x, y)}")
        return self.origin[0] + x, self.origin[1] + y

    def static_segment(self, a: Point, b: Point, radius: float = 2, *, friction: float = .8, elasticity: float = .2, surface_velocity: Vector = (0, 0), fill_color: Color = DEFAULT_SEGMENT_FILL, stroke_color: Color = DEFAULT_SEGMENT_STROKE) -> ShapeHandle:
        """Build a fixed physical rail from local point a to b; return its ShapeHandle."""
        import pymunk

        if radius < 0 or radius > BUILD_MARGIN:
            raise ValueError("segment radius outside build budget")
        shape = pymunk.Segment(self._registry.space.static_body, self._point(a), self._point(b), radius)
        shape.friction, shape.elasticity = friction, elasticity
        shape.surface_velocity = surface_velocity
        handle = self._registry.add(self._owner, shape, ShapeHandle)
        self._registry.set_object_style(handle, fill_color, stroke_color)
        return handle

    def static_circle(self, center: Point, radius: float, *, friction: float = .4, elasticity: float = .75, fill_color: Color = DEFAULT_CIRCLE_FILL, stroke_color: Color = DEFAULT_CIRCLE_STROKE) -> ShapeHandle:
        """Build a fixed physical circle in local coordinates; return its ShapeHandle."""
        import pymunk

        x, y = map(float, center)
        self._point((x-radius, y-radius)); self._point((x+radius, y+radius))
        body = pymunk.Body(body_type=pymunk.Body.STATIC); body.position = self._point(center)
        body_handle = self._registry.add(self._owner, body, BodyHandle)
        shape = pymunk.Circle(body, radius); shape.friction, shape.elasticity = friction, elasticity
        handle = self._registry.add(self._owner, shape, ShapeHandle)
        self._registry.set_object_style(handle, fill_color, stroke_color)
        return handle

    def static_polygon(self, points: list[Point] | tuple[Point, ...], *, radius: float = 0, friction: float = .8, elasticity: float = .2, fill_color: Color = DEFAULT_SEGMENT_FILL, stroke_color: Color = DEFAULT_SEGMENT_STROKE) -> ShapeHandle:
        """Build a fixed convex polygon from tile-local points."""
        import pymunk

        local = self._polygon_points(points, radius)
        shape = pymunk.Poly(self._registry.space.static_body, [self._point(point) for point in local], radius=radius)
        shape.friction, shape.elasticity = friction, elasticity
        handle = self._registry.add(self._owner, shape, ShapeHandle)
        self._registry.set_object_style(handle, fill_color, stroke_color)
        return handle

    def dynamic_body(self, position: Point, *, angle: float = 0) -> BodyHandle:
        """Create a dynamic body; attach one or more shapes to define its mass."""
        import pymunk

        body = pymunk.Body()
        body.position = self._point(position)
        body.angle = self._registry._number(angle, "angle")
        return self._registry.add(self._owner, body, BodyHandle)

    def circle_shape(self, body: BodyHandle, center: Point, radius: float, *, density: float = .01, friction: float = .8, elasticity: float = .2, fill_color: Color = DEFAULT_CIRCLE_FILL, stroke_color: Color = DEFAULT_CIRCLE_STROKE) -> ShapeHandle:
        """Attach a physical circle to a body using body-local coordinates."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        radius = self._registry._number(radius, "radius", minimum=0)
        self._check_attached_bounds(raw, ((center[0]-radius, center[1]-radius), (center[0]+radius, center[1]+radius)))
        shape = pymunk.Circle(raw, radius, tuple(map(float, center)))
        return self._add_attached_shape(body, shape, density, friction, elasticity, fill_color, stroke_color)

    def segment_shape(self, body: BodyHandle, a: Point, b: Point, radius: float = 2, *, density: float = .01, friction: float = .8, elasticity: float = .2, surface_velocity: Vector = (0, 0), fill_color: Color = DEFAULT_SEGMENT_FILL, stroke_color: Color = DEFAULT_SEGMENT_STROKE) -> ShapeHandle:
        """Attach a physical segment to a body using body-local coordinates."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        radius = self._registry._number(radius, "radius", minimum=0, maximum=BUILD_MARGIN)
        a, b = tuple(map(float, a)), tuple(map(float, b))
        self._check_attached_bounds(raw, ((a[0]-radius,a[1]-radius),(a[0]+radius,a[1]+radius),(b[0]-radius,b[1]-radius),(b[0]+radius,b[1]+radius)))
        shape = pymunk.Segment(raw, a, b, radius); shape.surface_velocity = tuple(map(float, surface_velocity))
        return self._add_attached_shape(body, shape, density, friction, elasticity, fill_color, stroke_color)

    def polygon_shape(self, body: BodyHandle, points: list[Point] | tuple[Point, ...], *, radius: float = 0, density: float = .01, friction: float = .8, elasticity: float = .2, fill_color: Color = DEFAULT_SEGMENT_FILL, stroke_color: Color = DEFAULT_SEGMENT_STROKE) -> ShapeHandle:
        """Attach a convex polygon to a body using body-local points."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        local = self._polygon_points(points, radius)
        expanded = [(x+dx*radius,y+dy*radius) for x,y in local for dx,dy in ((-1,-1),(1,1))]
        self._check_attached_bounds(raw, expanded)
        shape = pymunk.Poly(raw, local, radius=radius)
        return self._add_attached_shape(body, shape, density, friction, elasticity, fill_color, stroke_color)

    def pivot(self, body: BodyHandle, anchor: Point) -> ConstraintHandle:
        """Pin a body to the static world at a tile-local pivot point."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        constraint = pymunk.PivotJoint(self._registry.space.static_body, raw, self._point(anchor))
        return self._registry.add(self._owner, constraint, ConstraintHandle, body=body)

    def motor(self, body: BodyHandle, *, rate: float, max_force: float) -> MotorHandle:
        """Drive a body relative to the static world at a target angular rate."""
        import pymunk

        raw = self._registry.resolve(self._owner, body)
        constraint = pymunk.SimpleMotor(self._registry.space.static_body, raw, self._registry._number(rate, "rate"))
        constraint.max_force = self._registry._number(max_force, "max_force", minimum=0)
        return self._registry.add(self._owner, constraint, MotorHandle, body=body)

    def _polygon_points(self, points, radius):
        radius = self._registry._number(radius, "radius", minimum=0, maximum=BUILD_MARGIN)
        local = [tuple(map(float, point)) for point in points]
        if len(local) < 3: raise ValueError("polygon needs at least three points")
        for x, y in local:
            self._point((x-radius,y-radius)); self._point((x+radius,y+radius))
        return local

    def _check_attached_bounds(self, body, points):
        ox, oy = self.origin
        for point in points:
            world = body.local_to_world(point)
            self._point((world.x-ox, world.y-oy))

    def _add_attached_shape(self, body, shape, density, friction, elasticity, fill_color, stroke_color):
        shape.density = self._registry._number(density, "density", minimum=0)
        if shape.density == 0: raise ValueError("density must be greater than zero")
        shape.friction = self._registry._number(friction, "friction", minimum=0)
        shape.elasticity = self._registry._number(elasticity, "elasticity", minimum=0, maximum=1)
        raw_body = self._registry.resolve(self._owner, body)
        authored_position = raw_body.position
        handle = self._registry.add(self._owner, shape, ShapeHandle, body=body)
        # Pymunk updates center of gravity as density-backed shapes are added.
        # Keep the contributor-facing body origin fixed while assembling it.
        raw_body.position = authored_position
        self._registry.set_object_style(handle, fill_color, stroke_color)
        return handle

    def sensor_box(self, left: float, top: float, right: float, bottom: float) -> ShapeHandle:
        """Build an invisible, non-colliding rectangular sensor; return its ShapeHandle."""
        import pymunk

        points=[self._point(p) for p in ((left,top),(right,top),(right,bottom),(left,bottom))]
        shape=pymunk.Poly(self._registry.space.static_body,points);shape.sensor=True;shape.ebm_hidden=True
        return self._registry.add(self._owner,shape,ShapeHandle)

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

    def visual_segment(self, a: Point, b: Point, radius: float = 6, *, fill_color: Color = DEFAULT_SEGMENT_FILL, stroke_color: Color = DEFAULT_SEGMENT_STROKE) -> VisualHandle:
        """Build a styled non-physical line; return its VisualHandle."""
        # Visual-only primitives are owned and bounds-checked but never added to
        # Pymunk, so reference graphics cannot interfere with ball routing.
        local_a=(float(a[0]),float(a[1]));local_b=(float(b[0]),float(b[1]))
        self._point(local_a);self._point(local_b)
        return self._registry.add_visual(self._owner,VisualSegment(local_a,local_b,float(radius)),fill_color,stroke_color)

    def body_position(self, body: BodyHandle) -> Point:
        """Return the current tile-local position of an owned body."""
        return self._registry.body_position(self._owner, body)

    def remove(self, handle: ResourceHandle) -> None:
        """Remove an owned resource from the simulation before normal cleanup."""
        obj=self._registry.resolve(self._owner,handle)
        self._registry.space.remove(obj)

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
