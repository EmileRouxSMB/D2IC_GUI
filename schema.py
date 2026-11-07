"""Versioned study settings and UI help for the local D2IC application."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Field:
    default: object
    view: str
    label: str
    help: str
    unit: str = ""
    choices: tuple[str, ...] = ()
    minimum: float | None = None


def _f(default, view, label, help, unit="", choices=(), minimum=None):
    return Field(default, view, label, help, unit, tuple(choices), minimum)


FIELDS = {
    "project": {
        "version": _f(1, "Système", "Version du schéma", "Version du format de l'étude ; fixée à 1."),
        "mode": _f("dic", "Global", "Parcours", "DIC seule ou DIC avec température.", choices=("dic", "dic_thermal")),
        "name": _f("Nouvelle étude", "Résultats", "Nom", "Nom lisible de l'étude."),
    },
    "paths": {
        "visible_dir": _f("", "VIS", "Dossier VIS", "Dossier des images VIS TIFF, BMP, PNG ou JPEG ; elles restent sur place."),
        "reference_image": _f("", "VIS", "Référence VIS", "Nom ou chemin de l'image de référence."),
        "visible_pattern": _f("*.tif", "VIS", "Motif VIS", "Motif de la série VIS ; la référence est exclue du calcul DIC."),
        "excluded_images": _f([], "VIS", "Images VIS désactivées", "Noms des images exclues de l’analyse ; sélection modifiable dans la table VIS."),
        "output_dir": _f("runs", "Résultats", "Dossier des runs", "Destination des calculs figés."),
    },
    "roi": {
        "initial_mask": _f("roi/mask_initial.tif", "ROI", "Fichier ROI", "Masque TIFF ou PNG dans les pixels de la VIS de référence ; le canal alpha est ignoré."),
        "final_mask": _f("roi/mask_final.tif", "ROI", "Masque final", "Masque binaire effectivement utilisé pour le maillage."),
        "operation": _f("none", "ROI", "Morphologie", "Dilate ou érode le masque initial avant maillage.", choices=("none", "dilation", "erosion")),
        "radius_px": _f(0, "ROI", "Rayon", "Rayon du disque morphologique ; zéro conserve le masque.", "px VIS", minimum=0),
        "kernel": _f("disk", "ROI", "Noyau", "Forme de l'élément structurant ; disque discret.", choices=("disk",)),
    },
    "mesh": {
        "element_size_px": _f(15.0, "ROI", "Taille de maille", "Taille cible des éléments du maillage superposé à la VIS.", "px VIS", minimum=0),
        "remove_islands": _f(True, "ROI", "Retirer les îlots", "Écarte les petites composantes séparées du masque."),
        "min_island_area_px": _f(64, "ROI", "Aire minimale d'îlot", "Aire sous laquelle une composante est écartée.", "px² VIS", minimum=0),
    },
    "dic": {
        "image_stride": _f(1, "DIC", "Pas des images", "Retient une image VIS sur ce nombre ; les temps restent ceux des acquisitions retenues.", minimum=1),
        "image_binning": _f(1, "DIC", "Binning", "Réduit la résolution du calcul ; les résultats reviennent aux pixels VIS d'origine.", minimum=1),
        "roi_erosion_px": _f(0.0, "ROI", "Érosion photométrique", "Rayon d’érosion euclidienne des pixels retenus dans le critère photométrique, autour des bords et des trous. En pixels VIS d’origine, même avec binning. Zéro désactive l’érosion. Le masque de maillage, les nœuds et les éléments restent inchangés.", "px VIS d’origine", minimum=0),
        "max_iters": _f(400, "DIC", "Itérations maximales", "Limite des itérations du solveur DIC.", minimum=1),
        "tol": _f(0.01, "DIC", "Tolérance", "Critère d'arrêt du solveur DIC.", minimum=0),
        "reg_strength": _f(0.01, "DIC", "Régularisation", "Poids de la régularisation ; dépend du cas étudié.", minimum=0),
        "regularization": _f("elastic", "DIC", "Modèle de régularisation", "Type de régularisation du champ de déplacement.", choices=("elastic", "spring")),
        "strain_gauge_length": _f(80.0, "DIC", "Longueur de jauge", "Échelle spatiale d'estimation des déformations.", "px VIS", minimum=0),
        "interpolation": _f("cubic", "DIC", "Interpolation VIS", "Interpolation des niveaux de gris aux positions déformées.", choices=("cubic", "linear")),
    },
    "scale": {
        "mm_per_pixel": _f(1.0, "DIC", "Facteur d'échelle", "Millimètres par pixel VIS d'origine ; confirmé explicitement avant sortie en mm.", "mm/px", minimum=0),
        "method": _f("manual", "DIC", "Méthode d'échelle", "Saisie directe ou segment mesuré sur la référence VIS.", choices=("manual", "segment")),
        "confirmed": _f(False, "DIC", "Échelle confirmée", "Confirme que la mesure d'échelle a été vérifiée."),
        "segment_xy_px": _f([], "DIC", "Extrémités du segment", "Deux points [x,y] dans la VIS d'origine.", "px VIS"),
        "segment_length_mm": _f(0.0, "DIC", "Longueur du segment", "Longueur physique connue entre les deux points.", "mm", minimum=0),
    },
    "time": {
        "visible_source": _f("filename", "DIC", "Source des temps VIS", "Numéros du nom de fichier ou horodatages des métadonnées.", choices=("filename", "metadata")),
        "visible_frame_regex": _f(r"(\d+)", "DIC", "Expression VIS", "Capture le numéro d'acquisition dans le nom de fichier."),
        "visible_fps": _f(10.0, "DIC", "Cadence VIS", "Convertit les numéros d'image en secondes.", "Hz", minimum=0),
    },
    "output": {
        "export_vtu": _f(True, "Export", "Exporter VTU", "Un fichier de champs par temps VIS."),
        "export_pvd": _f(True, "Export", "Exporter PVD", "Série ParaView datée par les temps VIS ; exige VTU."),
        "save_npz": _f(True, "Export", "Conserver les résultats DIC", "Conserve le magasin DIC par image et ses chemins sources pour la reprise ; archive globale sur demande."),
        "export_png": _f(False, "Export", "Exporter PNG", "Figures par image, qui augmentent le volume du run."),
        "compute_residual_map": _f(False, "Export", "Cartes de résidu", "Calcule une carte photométrique par image VIS ; augmente le volume du magasin DIC."),
        "paraview_length_unit": _f("px", "Export", "Unité de longueur", "mm exige une échelle confirmée ; coordonnées et déplacements changent ensemble.", choices=("px", "mm")),
        "series_name": _f("dic", "Export", "Nom de série", "Nom de base des fichiers VTU/PVD."),
    },
    "runtime": {
        "jax_preferred": _f("gpu", "DIC", "Dispositif préféré", "Dispositif JAX demandé pour le processus de calcul.", choices=("gpu", "cpu")),
        "jax_fallback": _f("cpu", "DIC", "Dispositif de repli", "Utilisé si le dispositif préféré est indisponible.", choices=("cpu", "gpu")),
        "jax_enable_x64": _f(False, "DIC", "Précision 64 bits", "Active les flottants 64 bits avant l'initialisation JAX."),
    },
    "thermal": {
        "image_dir": _f("", "Thermique", "Dossier TH", "Dossier des TIFF contenant déjà des températures."),
        "image_pattern": _f("*.tif", "Thermique", "Motif TH", "Motif des acquisitions thermiques."),
        "unit": _f("degC", "Thermique", "Unité TH", "Unité physique des valeurs TIFF ; aucune correction radiométrique."),
        "time_source": _f("filename", "Thermique", "Source des temps TH", "Numéros du nom ou horodatages des métadonnées.", choices=("filename", "metadata")),
        "frame_regex": _f(r"(\d+)", "Thermique", "Expression TH", "Capture le numéro d'acquisition thermique."),
        "thermal_fps": _f(50.0, "Thermique", "Cadence TH", "Convertit les numéros TH en secondes ; souvent 50 Hz.", "Hz", minimum=0),
        "excluded_images": _f([], "Thermique", "Images TH désactivées", "Noms des TIFF TH exclus de l'analyse et de toute interpolation."),
    },
    "registration": {
        "file": _f("calibration/visible_thermal.json", "Thermique", "Calibration", "Transformation VIS vers TH issue de points homologues."),
        "approved": _f(False, "Thermique", "Correspondance approuvée", "Validation manuelle liée au fichier exact et à ses dimensions."),
    },
    "synchronization": {
        "method": _f("timestamps", "Temps", "Alignement des horloges", "Horodatages communs ou événement vu par les deux caméras.", choices=("timestamps", "event_frames")),
        "visible_event_frame": _f(0, "Temps", "Événement VIS", "Numéro de trame VIS de l'événement commun.", minimum=0),
        "thermal_event_frame": _f(0, "Temps", "Événement TH", "Numéro de trame TH du même événement.", minimum=0),
        "thermal_interpolation": _f("linear", "Temps", "Interpolation TH", "Interpolation linéaire des températures seulement.", choices=("linear",)),
        "thermal_offset_s": _f(0.0, "Temps", "Décalage TH", "Décalage explicite de l'horloge TH vers les temps VIS.", "s"),
    },
}

THERMAL_SECTIONS = {"thermal", "registration", "synchronization"}


def defaults(mode="dic"):
    """Return independent default settings, omitting thermal tables in DIC mode."""
    if mode not in ("dic", "dic_thermal"):
        raise ValueError("project.mode doit être 'dic' ou 'dic_thermal'")
    sections = (section for section in FIELDS if mode == "dic_thermal" or section not in THERMAL_SECTIONS)
    result = {section: {key: field.default if not isinstance(field.default, list) else list(field.default)
                        for key, field in FIELDS[section].items()} for section in sections}
    result["project"]["mode"] = mode
    return result


def describe_fields(mode="dic_thermal"):
    """Return UI metadata for every applicable TOML key."""
    return {f"{section}.{key}": {"view": field.view, "label": field.label,
            "default": field.default, "unit": field.unit, "help": field.help,
            "choices": field.choices, "minimum": field.minimum}
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
            result[section] = {key: field.default for key, field in FIELDS[section].items()}
    for section, values in data.items():
        if section not in result:
            raise ValueError(f"Table inconnue ou inapplicable : [{section}]")
        if not isinstance(values, dict):
            raise ValueError(f"[{section}] doit être une table")
        for key, value in values.items():
            if key not in FIELDS[section]:
                raise ValueError(f"Clé inconnue : {section}.{key}")
            field = FIELDS[section][key]
            expected = type(field.default)
            if expected is float and type(value) in (int, float):
                value = float(value)
            elif type(value) is not expected:
                raise ValueError(f"{section}.{key} : type attendu {expected.__name__}")
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                if not isfinite(value) or (field.minimum is not None and value < field.minimum):
                    raise ValueError(f"{section}.{key} : valeur hors domaine")
            if field.choices and value not in field.choices:
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
