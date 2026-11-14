"""Shared seed selection and temporary global randomness for validation."""
from contextlib import contextmanager
import random
import secrets

MAX_VALIDATION_SEED = 2**32 - 1


def resolve_validation_seed(seed=None):
    """Blank selects a fresh seed; explicit seeds are unsigned 32-bit decimals."""
    if seed is None or isinstance(seed, str) and not seed.strip():
        return secrets.randbits(32)
    if isinstance(seed, str):
        seed = seed.strip()
        if not seed.isascii() or not seed.isdecimal():
            raise ValueError(f"Seed must be an integer from 0 to {MAX_VALIDATION_SEED}.")
        # Check length before conversion to reject enormous pasted values cheaply.
        seed = seed.lstrip("0") or "0"
        if len(seed) > 10:
            raise ValueError(f"Seed must be an integer from 0 to {MAX_VALIDATION_SEED}.")
        seed = int(seed)
    if type(seed) is not int or not 0 <= seed <= MAX_VALIDATION_SEED:
        raise ValueError(f"Seed must be an integer from 0 to {MAX_VALIDATION_SEED}.")
    return seed


@contextmanager
def seeded_random(seed):
    """Seed tile calls to module-level random; restore preview state even on error."""
    state = random.getstate()
    try:
        random.seed(seed)
        yield
    finally:
        random.setstate(state)
