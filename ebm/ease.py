"""Standard easing curves: normalized time in [0, 1] to interpolation progress.

Back and elastic curves overshoot; outputs are deliberately not clamped.
Use ``from ebm import ease`` and, for example, ``ease.in_out_sine``.
"""
import math

__all__ = ["linear"] + [f"{direction}_{family}"
    for family in ("sine", "quad", "cubic", "quart", "quint", "expo", "circ", "back", "elastic", "bounce")
    for direction in ("in", "out", "in_out")]


def linear(t: float) -> float:
    return t


def in_sine(t: float) -> float:
    return 1 - math.cos(t * math.pi / 2)


def out_sine(t: float) -> float:
    return math.sin(t * math.pi / 2)


def in_out_sine(t: float) -> float:
    return (1 - math.cos(math.pi * t)) / 2


def in_quad(t: float) -> float:
    return t * t


def out_quad(t: float) -> float:
    return 1 - (1 - t) ** 2


def in_out_quad(t: float) -> float:
    return 2 * t * t if t < .5 else 1 - (-2 * t + 2) ** 2 / 2


def in_cubic(t: float) -> float:
    return t ** 3


def out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def in_out_cubic(t: float) -> float:
    return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def in_quart(t: float) -> float:
    return t ** 4


def out_quart(t: float) -> float:
    return 1 - (1 - t) ** 4


def in_out_quart(t: float) -> float:
    return 8 * t ** 4 if t < .5 else 1 - (-2 * t + 2) ** 4 / 2


def in_quint(t: float) -> float:
    return t ** 5


def out_quint(t: float) -> float:
    return 1 - (1 - t) ** 5


def in_out_quint(t: float) -> float:
    return 16 * t ** 5 if t < .5 else 1 - (-2 * t + 2) ** 5 / 2


def in_expo(t: float) -> float:
    return 0.0 if t == 0 else 2 ** (10 * t - 10)


def out_expo(t: float) -> float:
    return 1.0 if t == 1 else 1 - 2 ** (-10 * t)


def in_out_expo(t: float) -> float:
    if t == 0 or t == 1:
        return t
    return 2 ** (20 * t - 10) / 2 if t < .5 else (2 - 2 ** (-20 * t + 10)) / 2


def in_circ(t: float) -> float:
    return 1 - math.sqrt(1 - t * t)


def out_circ(t: float) -> float:
    return math.sqrt(1 - (t - 1) ** 2)


def in_out_circ(t: float) -> float:
    return ((1 - math.sqrt(1 - (2 * t) ** 2)) / 2 if t < .5
            else (math.sqrt(1 - (-2 * t + 2) ** 2) + 1) / 2)


def in_back(t: float) -> float:
    c = 1.70158
    return (c + 1) * t ** 3 - c * t * t


def out_back(t: float) -> float:
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def in_out_back(t: float) -> float:
    c = 1.70158 * 1.525
    return ((2 * t) ** 2 * ((c + 1) * 2 * t - c) / 2 if t < .5
            else ((2 * t - 2) ** 2 * ((c + 1) * (2 * t - 2) + c) + 2) / 2)


def in_elastic(t: float) -> float:
    if t == 0 or t == 1:
        return t
    return -(2 ** (10 * t - 10)) * math.sin((10 * t - 10.75) * (2 * math.pi / 3))


def out_elastic(t: float) -> float:
    if t == 0 or t == 1:
        return t
    return 2 ** (-10 * t) * math.sin((10 * t - .75) * (2 * math.pi / 3)) + 1


def in_out_elastic(t: float) -> float:
    if t == 0 or t == 1:
        return t
    wave = math.sin((20 * t - 11.125) * (2 * math.pi / 4.5))
    return -(2 ** (20 * t - 10) * wave) / 2 if t < .5 else 2 ** (-20 * t + 10) * wave / 2 + 1


def out_bounce(t: float) -> float:
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        return n * (t - 1.5 / d) ** 2 + .75
    if t < 2.5 / d:
        return n * (t - 2.25 / d) ** 2 + .9375
    return n * (t - 2.625 / d) ** 2 + .984375


def in_bounce(t: float) -> float:
    return 1 - out_bounce(1 - t)


def in_out_bounce(t: float) -> float:
    return (1 - out_bounce(1 - 2 * t)) / 2 if t < .5 else (1 + out_bounce(2 * t - 1)) / 2
