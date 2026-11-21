"""Catalogue-only extensions must reach defaults, API and saved study values."""
from pathlib import Path
import tomllib

import pytest
from fastapi.testclient import TestClient

from D2IC_GUI import schema
from D2IC_GUI.project import create_project, save_project, load_project
from D2IC_GUI.server import create_app

CATALOG = Path(schema.__file__).with_name('parameters.toml')
EXTENSION = '''
[[parameters]]
key = "dic.extra_tolerance"
label = "Tolérance supplémentaire"
type = "float"
default = 0.5
minimum = 0.0
view = "ROI"
help = "Paramètre ajouté uniquement au catalogue pour vérifier le formulaire."

[[parameters]]
key = "custom.channels"
label = "Canaux"
type = "array"
default = ["VIS"]
choices = ["VIS", "TH"]
view = "Export"
help = "Choix multiple."
'''


def test_catalog_extension_defaults_api_and_persistence(tmp_path, monkeypatch):
    path = tmp_path/'parameters.toml'
    path.write_text(CATALOG.read_text() + EXTENSION)
    fields, thermal = schema.load_catalog(path)
    monkeypatch.setattr(schema, 'FIELDS', fields)
    monkeypatch.setattr(schema, 'THERMAL_SECTIONS', thermal)
    folder = tmp_path/'study'
    config = create_project(folder)
    assert config['dic']['extra_tolerance'] == 0.5
    config['dic']['extra_tolerance'] = 0.25
    config['custom']['channels'] = ['VIS', 'TH']
    save_project(folder, config)
    assert load_project(folder) == config
    client = TestClient(create_app(folder))
    meta = client.get('/api/schema').json()['fields']
    assert meta['dic.extra_tolerance']['view'] == 'ROI'
    assert meta['dic.extra_tolerance']['type'] == 'float'
    assert meta['custom.channels']['choices'] == ['VIS', 'TH']
    with pytest.raises(ValueError, match='extra_tolerance'):
        schema.validate({'dic': {'extra_tolerance': -1}})
    with pytest.raises(ValueError, match='channels'):
        schema.validate({'custom': {'channels': ['unknown']}})
    with pytest.raises(ValueError, match='extra_tolerance'):
        schema.validate({'dic': {'extra_tolerance': True}})


@pytest.mark.parametrize('mutation, error', [
    (lambda text: text + EXTENSION + EXTENSION, 'dupliquée'),
    (lambda text: text.replace('type = "integer"', 'type = "unknown"', 1), 'type ou défaut'),
    (lambda text: text.replace('default = 400', 'default = "400"'), 'type ou défaut'),
    (lambda text: text.replace('view = "ROI"', 'view = "unknown"', 1), 'onglet'),
    (lambda text: text.replace('choices = ["elastic", "spring"]', 'choices = ["spring"]'), 'défaut absent'),
    (lambda text: text.replace('default = 400', 'default = -1'), 'hors domaine'),
    (lambda text: text.replace('type = "directory"', 'type = "string"', 1), 'incompatible'),
])
def test_invalid_catalog_is_rejected(tmp_path, mutation, error):
    path = tmp_path/'catalog.toml'
    path.write_text(mutation(CATALOG.read_text()))
    with pytest.raises(ValueError, match=error):
        schema.load_catalog(path)


def test_defaults_are_independent_and_catalog_is_complete():
    entries = tomllib.loads(CATALOG.read_text())['parameters']
    assert len(entries) == len(schema.describe_fields())
    assert all({'key', 'label', 'type', 'default', 'view', 'help'} <= entry.keys()
               for entry in entries)
    first = schema.defaults('dic_thermal')
    first['thermal']['excluded_images'].append('ignored.tif')
    assert schema.defaults('dic_thermal')['thermal']['excluded_images'] == []
