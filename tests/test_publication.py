import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

import pytest

from ebm.publication import validate_publication
from ebm.tile_base import TileBase
from ebm.tile_catalog import TileRegistration, _load_registration, discover_tile_modules
from ebm.tiles.builtin.powered_channel import PoweredChannelTile


class GoodTile(PoweredChannelTile):
    author = "Tests"
    enabled = True


class DisabledBrokenTile(TileBase):
    author = "Tests"
    enabled = False

    def __init__(self):
        raise AssertionError("A disabled tile must never be instantiated by publication")


class BadTile(TileBase):
    author = "Tests"

    def build(self, b):
        b.static_segment((0, 100), (100, 100), 2)


def registration(cls):
    return TileRegistration(f"ebm.tiles.contributed.{cls.__name__}", cls, False)


def test_publication_skips_disabled_tiles_and_runs_both_checks_for_enabled_tiles():
    result = validate_publication([registration(GoodTile), registration(DisabledBrokenTile)])
    assert result['ok'], result
    assert result['tiles'][0]['single']['ok']
    assert result['tiles'][0]['repeat']['ok']
    assert result['tiles'][1]['status'] == 'skipped'
    assert 'single' not in result['tiles'][1]


def test_bad_active_tile_blocks_publication():
    result = validate_publication([registration(BadTile), registration(GoodTile)])
    assert not result['ok']
    assert result['tiles'][0]['status'] == 'failed'
    assert result['tiles'][0]['single']['runtime_errors'][0]['phase'] == 'build'
    assert result['tiles'][1]['status'] == 'passed'


@pytest.mark.parametrize('tiles', [[], [registration(DisabledBrokenTile)]])
def test_empty_active_catalog_does_not_publish(tiles):
    result = validate_publication(tiles)
    assert not result['ok']
    assert 'No enabled tiles' in result['error']


def test_discovery_is_recursive_sorted_and_ignores_helpers(tmp_path):
    for name in ['z.py', 'contributed/a.py', 'contributed/creator/new_tile.py', '__init__.py', '_helper.py', '_private/hidden.py']:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('')
    assert discover_tile_modules(tmp_path) == (
        'ebm.tiles.contributed.a', 'ebm.tiles.contributed.creator.new_tile', 'ebm.tiles.z',
    )
    (tmp_path / 'bad-name.py').write_text('')
    with pytest.raises(ValueError, match='identifiers'):
        discover_tile_modules(tmp_path)


@pytest.mark.parametrize('value', ['false', 0, None])
def test_enabled_metadata_must_be_boolean(monkeypatch, value):
    module = types.ModuleType('test_tile_metadata')
    module.Example = type('Example', (TileBase,), {'__module__': module.__name__, 'author': 'Tests', 'enabled': value})
    monkeypatch.setattr('ebm.tile_catalog.import_module', lambda name: module)
    with pytest.raises(ValueError, match='enabled'):
        _load_registration(module.__name__)


def test_new_disabled_file_is_automatically_packaged_and_never_selected(tmp_path):
    root = Path(__file__).parents[1]
    for folder in ('ebm', 'scripts', 'web'):
        shutil.copytree(root / folder, tmp_path / folder, ignore=shutil.ignore_patterns('__pycache__'))
    new_file = tmp_path / 'ebm/tiles/contributed/creator/fresh_tile.py'
    new_file.parent.mkdir()
    new_file.write_text('''from ebm import TileBase
class FreshTile(TileBase):
    author = "Tests"
    enabled = False
    def __init__(self):
        raise RuntimeError("disabled broken work in progress")
''')
    # A fresh interpreter proves discovery is not relying on cached imports.
    result = subprocess.run([sys.executable, '-c', '''import json
from ebm.tile_catalog import get_tile
from ebm.engine import MACHINE_TILE_IDS
r = get_tile("contributed.creator.fresh-tile")
print(json.dumps({"enabled": r.enabled, "selected": r.id in MACHINE_TILE_IDS}))
'''], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {'enabled': False, 'selected': False}
    env = {**os.environ, 'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')}
    subprocess.run(['bash', 'scripts/build-static-site.sh'], cwd=tmp_path, env=env, check=True, capture_output=True)
    site = tmp_path / 'dist/site'
    manifest = json.loads((site / 'tiles/manifest.json').read_text())
    item = next(tile for tile in manifest['tiles'] if tile['id'] == 'contributed.creator.fresh-tile')
    assert item['enabled'] is False
    assert (site / item['source']).read_text() == new_file.read_text()
    files = json.loads((site / 'python-files.json').read_text())
    assert files == sorted(files)
    assert 'tiles/contributed/creator/fresh_tile.py' in files
    assert all((site / 'ebm' / file).is_file() for file in files)
    assert {'ball_physics.py', 'geometry_bounds.py', 'tile_output.py', 'repeat_validation.py'} <= set(files)
    assert (site / '.nojekyll').exists()
    assert (site / 'python-package.js').exists()

    # Removing the opt-out automatically puts the new module into the machine
    # selection. Its broken constructor now blocks publication.
    new_file.write_text(new_file.read_text().replace('enabled = False', 'enabled = True'))
    result = subprocess.run([sys.executable, '-c', 'from ebm.engine import MACHINE_TILE_IDS; assert "contributed.creator.fresh-tile" in MACHINE_TILE_IDS'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([sys.executable, '-m', 'ebm', 'validate', '--json'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['ok'] is False
