"""Versioned study settings and UI help for the local D2IC application."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy
import re
import tomllib
from math import isfinite
from pathlib import Path


SCHEMA_VERSION = 1


# Semantic path types also choose the appropriate filesystem browser.
DATA_TYPES = {"string": str, "integer": int, "float": float, "boolean": bool,
              "array": list, "directory": str, "file": str}
VIEWS = {"Global", "VIS", "ROI", "Échelle", "Réglages DIC", "Thermique",
         "Synchro", "Job Manager", "Résultats", "Export"}


@dataclass(frozen=True)
class Field:
    default: object
    view: str
    label: str
    help: str
    type: str
    unit: str = ""
    choices: tuple = ()
    minimum: float | None = None
    hidden: bool = False
    readonly: bool = False
    picker: str = ""
    group: str = ""
    view_dic: str = ""
    order: int = 0


def load_catalog(path):
    """Read the declarative UI catalogue, rejecting ambiguous keys and types."""
    with Path(path).open("rb") as stream:
        catalog = tomllib.load(stream)
    if catalog.get("catalog_version") != 1:
        raise ValueError("Version du catalogue de paramètres non prise en charge")
    fields = {}
    for entry in catalog["parameters"]:
        entry = dict(entry)
        key = entry.pop("key")
        if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", key):
            raise ValueError(f"Clé du catalogue invalide : {key}")
        section, name = key.split(".")
        if name in fields.get(section, {}):
            raise ValueError(f"Clé du catalogue dupliquée : {key}")
        if "choices" in entry:
            entry["choices"] = tuple(entry["choices"])
        field = Field(**entry)
        expected = DATA_TYPES.get(field.type)
        if expected is None or type(field.default) is not expected:
            raise ValueError(f"{key} : type ou défaut invalide dans le catalogue")
        if field.view not in VIEWS or (field.view_dic and field.view_dic not in VIEWS):
            raise ValueError(f"{key} : onglet inconnu")
        if field.picker not in ("", "directory", "image", "mask", "registration", "file"):
            raise ValueError(f"{key} : navigateur inconnu")
        if field.picker and (field.type not in ("directory", "file") or
                (field.type == "directory") != (field.picker == "directory")):
            raise ValueError(f"{key} : navigateur incompatible avec le type")
        if field.choices and field.type in ("directory", "file"):
            raise ValueError(f"{key} : un chemin ne peut pas avoir de choix prédéfinis")
        if field.choices and (expected not in (str, list) or
                any(type(choice) is not str for choice in field.choices)):
            raise ValueError(f"{key} : les choix doivent être des chaînes")
        if field.choices and (any(v not in field.choices for v in field.default)
                if expected is list else field.default not in field.choices):
            raise ValueError(f"{key} : défaut absent des choix")
        if expected in (int, float) and (not isfinite(field.default) or
                (field.minimum is not None and field.default < field.minimum)):
            raise ValueError(f"{key} : défaut hors domaine")
        fields.setdefault(section, {})[name] = field
    thermal_sections = set(catalog.get("thermal_sections", []))
    if not thermal_sections <= fields.keys():
        raise ValueError("Sections thermiques inconnues dans le catalogue")
    return fields, thermal_sections


FIELDS, THERMAL_SECTIONS = load_catalog(Path(__file__).with_name("parameters.toml"))


def defaults(mode="dic"):
    """Return independent default settings, omitting thermal tables in DIC mode."""
    if mode not in ("dic", "dic_thermal"):
        raise ValueError("project.mode doit être 'dic' ou 'dic_thermal'")
    sections = (section for section in FIELDS if mode == "dic_thermal" or section not in THERMAL_SECTIONS)
    result = {section: {key: deepcopy(field.default)
                        for key, field in FIELDS[section].items()} for section in sections}
    result["project"]["mode"] = mode
    return result


def describe_fields(mode="dic_thermal"):
    """Return UI metadata for every applicable TOML key."""
    return {f"{section}.{key}": {"key": f"{section}.{key}", **asdict(field)}
            for section, fields in FIELDS.items()
            if mode == "dic_thermal" or section not in THERMAL_SECTIONS
            for key, field in fields.items()}


def validate(data):
    """Merge defaults, retaining saved thermal settings when mode is DIC."""
    if not isinstance(data, dict):
        raise ValueError("config.toml doit contenir des tables")
    mode = data.get("project", {}).get("mode", "dic")
    result = defaults(mode)
    # A temporary switch to DIC preserves existing TH settings in the TOML.
    # The DIC run adapter ignores these optional tables.
    if mode == "dic":
        for section in THERMAL_SECTIONS.intersection(data):
            result[section] = {key: deepcopy(field.default) for key, field in FIELDS[section].items()}
    for section, values in data.items():
        if section not in result:
            raise ValueError(f"Table inconnue ou inapplicable : [{section}]")
        if not isinstance(values, dict):
            raise ValueError(f"[{section}] doit être une table")
        for key, value in values.items():
            if key not in FIELDS[section]:
                raise ValueError(f"Clé inconnue : {section}.{key}")
            field = FIELDS[section][key]
            expected = DATA_TYPES[field.type]
            if expected is float and type(value) in (int, float):
                value = float(value)
            elif type(value) is not expected:
                raise ValueError(f"{section}.{key} : type attendu {expected.__name__}")
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                if not isfinite(value) or (field.minimum is not None and value < field.minimum):
                    raise ValueError(f"{section}.{key} : valeur hors domaine")
            if field.choices and (any(v not in field.choices for v in value) if expected is list else value not in field.choices):
                raise ValueError(f"{section}.{key} : choisir {', '.join(field.choices)}")
            result[section][key] = value
    if result["project"]["version"] != SCHEMA_VERSION:
        raise ValueError("Version de config.toml non prise en charge")
    if result["scale"]["mm_per_pixel"] <= 0:
        raise ValueError("scale.mm_per_pixel doit être positif")
    if result["mesh"]["element_size_px"] <= 0:
        raise ValueError("mesh.element_size_px doit être positif")
    excluded = result["paths"]["excluded_images"]
    if (any(not isinstance(name, str) or not name or Path(name).name != name or name in (".", "..") for name in excluded)
            or len(set(excluded)) != len(excluded)):
        raise ValueError("paths.excluded_images doit contenir des noms de fichiers uniques")
    excluded = result.get("thermal", {}).get("excluded_images", [])
    if (any(not isinstance(name, str) or not name or Path(name).name != name or '/' in name or '\\' in name or name in (".", "..") for name in excluded)
            or len(set(excluded)) != len(excluded)):
        raise ValueError("thermal.excluded_images doit contenir des noms de fichiers uniques")
    series_name = result["output"]["series_name"]
    if not series_name or Path(series_name).name != series_name or series_name in (".", ".."):
        raise ValueError("output.series_name doit être un nom de fichier simple")
    if not result["output"]["save_npz"]:
        raise ValueError("output.save_npz doit rester actif pour la reprise des champs DIC")
    if result["output"]["export_pvd"] and not result["output"]["export_vtu"]:
        raise ValueError("output.export_pvd exige output.export_vtu")
    if result["output"]["paraview_length_unit"] == "mm" and not result["scale"]["confirmed"]:
        raise ValueError("Une sortie mm exige scale.confirmed = true")
    if result["scale"]["method"] == "segment" and result["scale"]["confirmed"]:
        points = result["scale"]["segment_xy_px"]
        if (len(points) != 2 or any(len(p) != 2 for p in points)
                or any(type(v) not in (int, float) or not isfinite(v) for p in points for v in p)
                or sum((a-b)**2 for a, b in zip(*points)) <= 0
                or result["scale"]["segment_length_mm"] <= 0):
            raise ValueError("Segment d'échelle confirmé invalide")
        result["scale"]["mm_per_pixel"] = (result["scale"]["segment_length_mm"]
            / sum((a-b)**2 for a, b in zip(*points))**0.5)
    return result
