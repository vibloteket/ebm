from ebm import TileBase
from ebm.repeat_validation import validate_repeated_flow
from ebm.tile_catalog import create_tile
from ebm.validator import validate_tile_flow


class UpdateErrorTile(TileBase):
    author = "Tests"

    def build(self, builder):
        pass

    def update(self, builder, dt):
        raise RuntimeError("update exploded")


class CallbackErrorTile(TileBase):
    author = "Tests"

    def build(self, builder):
        sensor = builder.sensor_box(0, 0, 400, 400)

        def fail(_event):
            raise RuntimeError("callback exploded")

        builder.on_ball_contact(sensor, begin=fail)


def test_repeat_validator_passes_teleport_collector_handoffs():
    result = validate_repeated_flow(
        lambda: create_tile("contributed.teleport-collector"),
        duration=8,
    )
    assert result.ok, result.to_dict()
    assert result.exited > 0
    assert not result.runtime_errors


def test_update_exception_fails_single_and_repeat_validation():
    single = validate_tile_flow(UpdateErrorTile, balls=2)
    repeat = validate_repeated_flow(UpdateErrorTile, duration=1)
    for result in (single, repeat):
        assert not result.ok
        assert result.runtime_errors[0]["phase"] == "update"
        assert result.runtime_errors[0]["type"] == "RuntimeError"


def test_callback_exception_fails_single_and_repeat_validation():
    single = validate_tile_flow(CallbackErrorTile, balls=2)
    repeat = validate_repeated_flow(CallbackErrorTile, duration=1)
    for result in (single, repeat):
        assert not result.ok
        assert result.runtime_errors[0]["phase"] == "begin"
        assert result.runtime_errors[0]["message"] == "callback exploded"
