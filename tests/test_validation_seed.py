import json
import random
from types import SimpleNamespace

import pytest

from ebm.validation_seed import MAX_VALIDATION_SEED, resolve_validation_seed, seeded_random


@pytest.mark.parametrize("value,expected", [(0, 0), (4294967295, 4294967295), (" 42 ", 42), ("0001", 1)])
def test_seed_accepts_explicit_decimal_values(value, expected):
    assert resolve_validation_seed(value) == expected


@pytest.mark.parametrize("value", [-1, 2**32, True, 1.2, "-1", "+1", "1.2", "1e3", "abc", "１２", "9"*100])
def test_invalid_seed_is_rejected(value):
    with pytest.raises(ValueError, match="Seed must be an integer"):
        resolve_validation_seed(value)


def test_blank_seed_is_generated_without_touching_global_random(monkeypatch):
    monkeypatch.setattr("ebm.validation_seed.secrets.randbits", lambda bits: MAX_VALIDATION_SEED)
    state = random.getstate()
    for blank in (None, "", "  "):
        assert resolve_validation_seed(blank) == MAX_VALIDATION_SEED
    assert random.getstate() == state


def test_seed_context_repeats_and_restores_after_exception():
    state = random.getstate()
    with seeded_random(17):
        first = [random.random() for _ in range(4)]
    assert random.getstate() == state
    with pytest.raises(RuntimeError):
        with seeded_random(17):
            assert [random.random() for _ in range(4)] == first
            raise RuntimeError("author failed")
    assert random.getstate() == state


def test_publication_resets_each_stage_and_tile_and_forwards_input_seed(monkeypatch):
    import ebm.publication as publication

    class Result:
        ok = True
        def __init__(self): self.draw = random.random()
        def to_dict(self): return {"ok": True, "draw": self.draw}

    seen = []
    def repeat(factory, *, seed):
        seen.append(seed)
        return Result()

    monkeypatch.setattr(publication, "validate_tile_flow", lambda factory, **kw: Result())
    monkeypatch.setattr(publication, "validate_repeated_flow", repeat)
    tiles = [SimpleNamespace(id=name, title=name, enabled=True, create=lambda: None) for name in ("a", "b")]
    state = random.getstate()
    report = publication.validate_publication(tiles, seed=42)
    assert random.getstate() == state
    assert report["seed"] == 42 and report["ok"]
    draws = [tile[stage]["draw"] for tile in report["tiles"] for stage in ("single", "repeat")]
    assert draws == [random.Random(42).random()] * 4
    assert seen == [42, 42]
    assert publication.validate_publication(tiles[::-1], seed=42)["tiles"] == report["tiles"][::-1]


def test_cli_seed_is_logged_and_bundled_even_on_exception(monkeypatch, capsys):
    from ebm.__main__ import main

    def fail(*, seed):
        assert seed == 123
        raise RuntimeError("tile error")

    monkeypatch.setattr("ebm.publication.validate_publication", fail)
    with pytest.raises(SystemExit) as error:
        main(["validate", "--json", "--seed", "123"])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "Validation seed: 123" in output.err
    report = json.loads(output.out)
    assert report["seed"] == 123 and not report["ok"]


def test_cli_omitted_seed_generates_and_passes_same_value(monkeypatch, capsys):
    from ebm.__main__ import main

    monkeypatch.setattr("ebm.validation_seed.secrets.randbits", lambda bits: 314)
    def validate(*, seed):
        assert seed == 314
        return {"ok": True, "seed": seed, "tiles": []}
    monkeypatch.setattr("ebm.publication.validate_publication", validate)
    with pytest.raises(SystemExit) as error:
        main(["validate", "--json"])
    assert error.value.code == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["seed"] == 314
    assert "Validation seed: 314" in output.err
