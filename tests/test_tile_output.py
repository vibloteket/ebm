from ebm.tile_output import suppress_tile_output


def test_full_machine_suppresses_forgotten_tile_prints(capsys):
    with suppress_tile_output():
        print("debug noise")
    assert capsys.readouterr().out == ""
