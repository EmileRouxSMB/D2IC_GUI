"""Study configuration and atomic, reproducible project operations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import tomllib

from .schema import defaults, validate


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"Valeur TOML non prise en charge : {type(value).__name__}")


def dump_toml(settings):
    """Serialize the fixed flat-table study schema as valid TOML."""
    settings = validate(settings)
    return "\n".join(
        f"[{section}]\n" + "\n".join(f"{key} = {_toml_value(value)}" for key, value in values.items())
        for section, values in settings.items()
    ) + "\n"


def load_project(folder):
    """Read a study config, filling explicit schema defaults for absent keys."""
    path = Path(folder).expanduser().resolve() / "config.toml"
    with path.open("rb") as stream:
        return validate(tomllib.load(stream))


def save_project(folder, settings):
    """Atomically replace config.toml after schema validation."""
    folder = Path(folder).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    content = dump_toml(settings)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder,
                                     prefix=".config.", suffix=".tmp", delete=False) as stream:
        temp_path = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
    os.replace(temp_path, folder / "config.toml")
    return folder / "config.toml"


def create_project(folder, name="Nouvelle étude", mode="dic"):
    """Create an empty study whose missing scientific inputs remain visible."""
    folder = Path(folder).expanduser().resolve()
    if (folder / "config.toml").exists():
        raise FileExistsError(f"Étude déjà présente : {folder}")
    settings = defaults(mode)
    settings["project"]["name"] = name
    save_project(folder, settings)
    return settings


def resolve_path(folder, path):
    """Resolve an image or small project asset from the config directory."""
    return (Path(folder).expanduser().resolve() / path).resolve()


def copy_project(source, target, name=None, settings=None):
    """Copy current or supplied settings and small assets without changing the source."""
    source = Path(source).expanduser().resolve()
    target = Path(target).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Destination non vide : {target}")
    settings = validate(settings) if settings is not None else load_project(source)
    if name is not None:
        settings["project"]["name"] = name
    for section, key in (("paths", "visible_dir"), ("thermal", "image_dir")):
        if section in settings and settings[section][key]:
            settings[section][key] = str(resolve_path(source, settings[section][key]))
    reference = settings["paths"]["reference_image"]
    if reference and Path(reference).is_absolute():
        settings["paths"]["reference_image"] = str(Path(reference).resolve())
    target.mkdir(parents=True, exist_ok=True)
    for asset in ("roi", "calibration"):
        origin = source / asset
        if origin.is_dir():
            shutil.copytree(origin, target / asset, dirs_exist_ok=True)
    # Asset paths may be relative outside the conventional subdirectories or
    # absolute. Copy the actual file and rewrite each setting to its new copy.
    for section, key, subdir in (("roi", "initial_mask", "roi"),
                                 ("roi", "final_mask", "roi"),
                                 ("registration", "file", "calibration")):
        if section not in settings or not settings[section][key]:
            continue
        source_asset = resolve_path(source, settings[section][key])
        if source_asset.is_file():
            destination = target / subdir / source_asset.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source_asset != destination:
                shutil.copy2(source_asset, destination)
            settings[section][key] = str(destination.relative_to(target))
            if section == 'registration':
                approval = source_asset.parent / 'approval.json'
                if approval.is_file():
                    shutil.copy2(approval, destination.parent / 'approval.json')
                else:
                    settings['registration']['approved'] = False
        elif Path(settings[section][key]).is_absolute():
            # An unavailable absolute asset remains visible as an absolute path.
            settings[section][key] = str(source_asset)
            if section == 'registration':
                settings['registration']['approved'] = False
    save_project(target, settings)
    return settings


def missing_sources(folder, settings=None):
    """List missing configured image folders and reference without changing runs."""
    settings = settings or load_project(folder)
    missing = []
    visible = settings["paths"]["visible_dir"]
    if visible and not resolve_path(folder, visible).is_dir():
        missing.append(str(resolve_path(folder, visible)))
    reference = settings["paths"]["reference_image"]
    if reference and visible:
        ref = Path(reference) if Path(reference).is_absolute() else resolve_path(folder, visible) / reference
        if not ref.is_file():
            missing.append(str(ref))
    if "thermal" in settings and settings["thermal"]["image_dir"]:
        thermal = resolve_path(folder, settings["thermal"]["image_dir"])
        if not thermal.is_dir():
            missing.append(str(thermal))
    return missing


def relink_sources(folder, *, visible_dir=None, thermal_dir=None):
    """Move an existing study to relocated image directories after source checks.

    Checks all files recorded by the latest run when available; past run
    manifests remain immutable records of the paths used for those runs.
    """
    folder = Path(folder).expanduser().resolve()
    settings = load_project(folder)
    from .imaging import read_image

    root = resolve_path(folder, settings['paths']['output_dir'])
    manifests = sorted(root.glob('*/manifest.json'), reverse=True) if root.is_dir() else []
    latest = json.loads(manifests[0].read_text(encoding='utf-8')) if manifests else {}
    checked = {}
    for key, directory, rows in (
        ('visible_dir', visible_dir,
         [latest['visible_reference'], *latest.get('visible_images', [])]
         if 'visible_reference' in latest else []),
        ('image_dir', thermal_dir, latest.get('thermal_images', [])),
    ):
        if directory is None:
            continue
        target = Path(directory).expanduser().resolve()
        if not target.is_dir():
            raise ValueError(f'Dossier image introuvable : {target}')
        if not rows and key == 'visible_dir':
            reference = settings['paths']['reference_image']
            if not (target / Path(reference).name).is_file():
                raise ValueError(f'Image de référence introuvable : {target / Path(reference).name}')
        for row in rows:
            candidate = target / Path(row['path']).name
            if not candidate.is_file():
                raise ValueError(f'Image attendue introuvable : {candidate}')
            if candidate.stat().st_size != row['size']:
                raise ValueError(f'Taille différente de la source du run : {candidate}')
            if list(read_image(candidate, visible=key == 'visible_dir').shape) != row['shape']:
                raise ValueError(f'Dimensions différentes de la source du run : {candidate}')
        checked[key] = (target, len(rows))
    if not checked:
        raise ValueError('Indiquer au moins un nouveau dossier VIS ou TH')
    if 'visible_dir' in checked:
        settings['paths']['visible_dir'] = str(checked['visible_dir'][0])
        settings['paths']['reference_image'] = Path(settings['paths']['reference_image']).name
    if 'image_dir' in checked:
        settings['thermal']['image_dir'] = str(checked['image_dir'][0])
    save_project(folder, settings)
    return settings, {key: count for key, (_, count) in checked.items()}
