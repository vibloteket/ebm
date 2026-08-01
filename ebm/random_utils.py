from __future__ import annotations

import hashlib
import random


def stable_seed(*parts: object) -> int:
    data = ":".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big")


def stable_rng(*parts: object) -> random.Random:
    return random.Random(stable_seed(*parts))
