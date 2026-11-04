"""Small, manually advanced scalar animations; no clock or global manager."""
import math
from collections.abc import Callable

from .ease import linear


def _finite(value, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


class Tween:
    """Interpolate finite scalar values over simulation-time seconds.

    Construction stores start as value without calling apply. update(dt) applies
    and returns the new value; at completion the exact end value is applied
    before done becomes True. Completed updates do not call apply again.
    Back/elastic easing may overshoot: values are not clamped to the endpoints.
    """

    def __init__(self, start: float, end: float, *, duration: float,
                 apply: Callable[[float], None] | None = None,
                 easing: Callable[[float], float] = linear) -> None:
        self._start = _finite(start, "start")
        self._end = _finite(end, "end")
        self._duration = _finite(duration, "duration")
        if self._duration < 0:
            raise ValueError("duration must be nonnegative")
        if apply is not None and not callable(apply):
            raise TypeError("apply must be callable or None")
        if not callable(easing):
            raise TypeError("easing must be callable")
        self._apply = apply
        self._easing = easing
        self._elapsed = 0.0
        self._value = self._start
        self._done = False

    @property
    def value(self) -> float:
        """Current scalar value; initially start, finally the exact end value."""
        return self._value

    @property
    def done(self) -> bool:
        """True after the final value has been successfully applied."""
        return self._done

    def update(self, dt: float) -> float:
        """Advance by finite, nonnegative simulation seconds and return value.

        Zero duration completes on the first update, including update(0).
        Callback/easing errors propagate without advancing the tween's state;
        any external side effects already made by the callback cannot be undone.
        """
        dt = _finite(dt, "dt")
        if dt < 0:
            raise ValueError("dt must be nonnegative")
        if self._done:
            return self._value
        elapsed = min(self._elapsed + dt, self._duration)
        done = elapsed >= self._duration or math.isclose(elapsed, self._duration, rel_tol=1e-12, abs_tol=0)
        if done:
            elapsed = self._duration
            value = self._end
        elif elapsed == 0:
            value = self._start
        else:
            progress = _finite(self._easing(elapsed / self._duration), "easing result")
            # Weighted interpolation avoids overflow in end - start for large,
            # opposite-sign finite endpoints. Overshoot is intentionally allowed.
            value = _finite((1 - progress) * self._start + progress * self._end, "interpolated value")
        if self._apply is not None:
            self._apply(value)
        self._elapsed = elapsed
        self._value = value
        self._done = done
        return value
