"""Read-only checks that explain whether a study can start a new run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np

from .dic_run import _time_of, worker_alive
from .imaging import image_shape, inventory, morphology, read_mask, thermal_inventory
from .project import resolve_path
from .schema import validate


VIEWS = ("VIS", "ROI", "Échelle", "Réglages DIC", "Thermique", "Synchro",
         "Job Manager", "Résultats", "Export")


def _schema_view(message, config=None):
    match = re.search(r"([a-z_]+)\.([a-z_]+)", message)
    if not match:
        return "Job Manager"
    section, key = match.groups()
    if section == "project":
        return "Job Manager"
    if section == "paths":
        return "Job Manager" if key == "output_dir" else "VIS"
    if section in ("roi", "mesh") or section == "dic" and key == "roi_erosion_px":
        return "ROI"
    if section == "scale":
        return "Échelle"
    if section in ("thermal", "registration"):
        return "Synchro" if key == "thermal_fps" else "Thermique"
    if section == "synchronization" or section == "time" and key == "visible_fps" and not (
            isinstance(config, dict) and config.get("project", {}).get("mode", "dic") == "dic"):
        return "Synchro"
    if section == "output":
        return "Export"
    return "Réglages DIC"


def _snapshot_headers(folder, settings):
    """Apply run snapshot sequence rules using image headers, not pixel reads."""
    paths, time = settings["paths"], settings["time"]
    image_dir = resolve_path(folder, paths["visible_dir"])
    excluded = set(paths.get("excluded_images", []))
    available = {path.name for path in image_dir.glob(paths["visible_pattern"]) if path.is_file()}
    unknown = excluded - available
    if unknown:
        raise ValueError("Images VIS désactivées absentes de la série : " + ", ".join(sorted(unknown)))
    ref_path = Path(paths["reference_image"])
    ref_path = (ref_path if ref_path.is_absolute() else image_dir / ref_path).resolve()
    if ref_path.parent != image_dir:
        raise ValueError("La référence VIS doit être dans paths.visible_dir pour D2IC")
    rows = inventory(folder, paths["visible_dir"], paths["visible_pattern"],
        time["visible_source"], time["visible_frame_regex"], time["visible_fps"],
        reference=paths["reference_image"], visible=True, exclude_names=excluded,
        inspect_pixels=False)
    if not (available - excluded - {ref_path.name}):
        raise ValueError("Aucune image VIS déformée active pour le calcul")
    ref_shape = list(image_shape(ref_path, visible=True))
    if ref_shape != rows["images"][0]["shape"]:
        raise ValueError("Dimensions de la référence VIS différentes de la séquence")
    stat = ref_path.stat()
    reference = {"path": str(ref_path), "shape": ref_shape,
        "time_s": _time_of(ref_path, time["visible_source"], time["visible_frame_regex"], time["visible_fps"]),
        "time_source": time["visible_source"], "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    if not rows["images"] or not all(row["time_s"] > reference["time_s"] for row in rows["images"]):
        raise ValueError("Les images déformées doivent suivre le temps de référence VIS")
    return reference, rows["images"], rows["warnings"]


def _missing_frames_message(kind, frames):
    preview = ", ".join(map(str, frames[:10]))
    remainder = f" et {len(frames) - 10} autres" if len(frames) > 10 else ""
    return f"Trames {kind} manquantes : {preview}{remainder} (les trous sont autorisés)."


def evaluate_readiness(folder, config, *, check_active_run=True):
    """Evaluate setup without creating or modifying an immutable run.

    Image inventories use file headers; binary ROI masks are read to check
    geometry and photometric support. No run or project file is written.
    """
    folder = Path(folder).expanduser().resolve()
    messages = {view: {"required": [], "optional": []} for view in VIEWS}
    applicable = set(VIEWS)
    raw_mode = (config.get("project", {}).get("mode", "dic")
                if isinstance(config, dict) and isinstance(config.get("project", {}), dict) else "dic")
    if raw_mode == "dic":
        applicable -= {"Thermique", "Synchro"}
    checked = None
    try:
        checked = validate(config)
    except Exception as error:  # malformed form values are reported in their owning view
        error_view = _schema_view(str(error), config)
        messages[error_view]["required"].append(str(error))
        applicable = {error_view}

    if checked is not None:
        cfg = checked
        output = resolve_path(folder, cfg["paths"]["output_dir"])
        has_results = False
        active_run = False
        if output.is_dir():
            for status_path in output.glob("*/status.json"):
                try:
                    status_data = json.loads(status_path.read_text())
                except (OSError, ValueError):
                    continue
                has_results |= status_data.get("state") == "completed"
                if status_data.get("state") == "running" and worker_alive(status_data.get("pid")):
                    active_run = True
        if active_run and check_active_run:
            messages["Job Manager"]["required"].append("Un calcul est déjà en cours ; attendre ou annuler le run.")
        try:
            ref, vis, warnings = _snapshot_headers(folder, cfg)
            for warning in warnings:
                if warning.get("kind") == "missing_frames":
                    messages["VIS"]["optional"].append(
                        _missing_frames_message("VIS", warning["frames"]))
                elif warning.get("kind") == "reordered_by_time":
                    messages["VIS"]["optional"].append("La série VIS sera triée selon ses temps d’acquisition.")
        except Exception as error:
            messages["VIS"]["required"].append(str(error))
            ref, vis = None, []
            applicable.discard("ROI")

        if ref is not None:
            mask_path = resolve_path(folder, cfg["roi"]["final_mask"])
            try:
                if not mask_path.is_file():
                    raise ValueError(f"Masque final absent : {mask_path} ; préparer la ROI")
                mask = read_mask(mask_path)
                if not np.any(mask):
                    raise ValueError("Le masque final est vide ; corriger la ROI")
                if list(mask.shape) != ref["shape"]:
                    raise ValueError("Dimensions du masque final différentes de la référence VIS")
                source_mask = resolve_path(folder, cfg["roi"]["initial_mask"])
                if source_mask.is_file():
                    expected_mask, _ = morphology(read_mask(source_mask), cfg["roi"]["operation"],
                                                  cfg["roi"]["radius_px"])
                    if not np.array_equal(mask, expected_mask):
                        raise ValueError("Masque final périmé après modification de l’opération ou du rayon ROI")
                from d2ic.io.app_utils import erode_correlation_roi
                from d2ic.io.binning import bin_mask
                from d2ic.mesh.generation import _remove_small_components
                observation_mask = mask
                if cfg["mesh"]["remove_islands"]:
                    observation_mask = _remove_small_components(
                        observation_mask, cfg["mesh"]["min_island_area_px"])
                factor = cfg["dic"]["image_binning"]
                observation_mask = bin_mask(observation_mask, factor)
                height, width = ref["shape"]
                observation_mask = observation_mask[:height // factor, :width // factor]
                erode_correlation_roi(observation_mask, cfg["dic"]["roi_erosion_px"],
                                      image_binning=factor)
            except Exception as error:
                messages["ROI"]["required"].append(str(error))

            # This is the same identity check as validated_mesh_image: a preview
            # is current only for the exact masks and mesh controls that made it.
            try:
                preview = folder / "roi" / "mesh_preview.png"
                meta_path = folder / "roi" / "mesh_preview.json"
                source_mask = resolve_path(folder, cfg["roi"]["initial_mask"])
                final_mask = resolve_path(folder, cfg["roi"]["final_mask"])
                if not preview.is_file() or not meta_path.is_file() or not final_mask.is_file():
                    raise ValueError("Aperçu du maillage absent ; générer et inspecter le maillage")
                meta = json.loads(meta_path.read_text())
                expected = {
                    "mask_sha256": hashlib.sha256(final_mask.read_bytes()).hexdigest(),
                    "source_mask_sha256": hashlib.sha256(source_mask.read_bytes()).hexdigest() if source_mask.is_file() else None,
                    "element_size_px": cfg["mesh"]["element_size_px"],
                    "image_binning": cfg["dic"]["image_binning"],
                    "remove_islands": cfg["mesh"]["remove_islands"],
                    "min_island_area_px": cfg["mesh"]["min_island_area_px"],
                }
                if meta.get("image_binning") != expected["image_binning"]:
                    raise ValueError(
                        f"Aperçu du maillage périmé : binning {meta.get('image_binning')} → "
                        f"{expected['image_binning']} ; cliquer sur Mailler dans ROI / maillage")
                if any(meta.get(key) != value for key, value in expected.items()):
                    raise ValueError("Aperçu du maillage périmé après modification des masques ou paramètres ; "
                                     "cliquer sur Mailler dans ROI / maillage")
            except Exception as error:
                messages["ROI"]["required"].append(str(error))

        # Pixel scale remains optional in px outputs; output in mm is already
        # schema-blocked unless the calibration has been explicitly confirmed.
        if cfg["output"]["paraview_length_unit"] == "mm" and not cfg["scale"]["confirmed"]:
                    messages["Échelle"]["required"].append("Une sortie en mm exige une échelle confirmée (mm/px).")
        elif not cfg["scale"]["confirmed"]:
            messages["Échelle"]["optional"].append("Échelle en pixels : facultative. Confirmez mm/px avant une sortie physique en mm.")

        if cfg["project"]["mode"] == "dic_thermal":
            try:
                th = cfg["thermal"]
                rows = thermal_inventory(folder, th["image_dir"], th["image_pattern"],
                    th["time_source"], th["frame_regex"], th["thermal_fps"],
                    th.get("excluded_images", []), inspect_pixels=False)
                thermal = rows["images"]
                for warning in rows["warnings"]:
                    if warning.get("kind") == "missing_frames":
                        messages["Synchro"]["optional"].append(
                            _missing_frames_message("TH", warning["frames"]))
            except Exception as error:
                messages["Thermique"]["required"].append(str(error))
                thermal = []

            path = resolve_path(folder, cfg["registration"]["file"])
            try:
                if not cfg["registration"]["approved"]:
                    raise ValueError("Correspondance VIS–TH non approuvée")
                if not path.is_file():
                    raise ValueError(f"Calibration absente : {path}")
                approval_path = path.parent / "approval.json"
                if not approval_path.is_file():
                    raise ValueError("Approbation liée à la calibration absente ; réapprouver")
                approval = json.loads(approval_path.read_text())
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if approval.get("sha256") != digest:
                    raise ValueError("Calibration modifiée après approbation ; réapprouver")
                from DICTHFusion.registration import load_registration
                calibration, _ = load_registration(path)
                if ref is None or not thermal:
                    raise ValueError("Dimensions VIS/TH impossibles à vérifier")
                if calibration["visible_shape_hw"] != ref["shape"] or calibration["thermal_shape_hw"] != thermal[0]["shape"]:
                    raise ValueError("Dimensions VIS/TH différentes de celles de la calibration ; réajuster")
                if approval.get("visible_shape_hw") != ref["shape"] or approval.get("thermal_shape_hw") != thermal[0]["shape"]:
                    raise ValueError("Dimensions de l’approbation différentes des sources ; réapprouver")
            except Exception as error:
                messages["Thermique"]["required"].append(str(error))

            # Invalid/unbracketed thermal samples are represented as NaN by the
            # coupling path, so they are a guide warning rather than a blocker.
            if ref is not None and vis and thermal:
                try:
                    from .thermal import align_thermal_times, thermal_brackets
                    vis = vis[::cfg["dic"]["image_stride"]]
                    vis_times = [ref["time_s"], *(row["time_s"] for row in vis)]
                    aligned = align_thermal_times(vis_times, [row["time_s"] for row in thermal],
                        method=cfg["synchronization"]["method"],
                        # Match the immutable manifest consumed by worker.py:
                        # metadata-time rows have frame=None, and the reference
                        # row currently carries no frame field.
                        visible_frames=[ref.get("frame"), *(row.get("frame") for row in vis)],
                        thermal_frames=[row.get("frame") for row in thermal],
                        visible_event_frame=cfg["synchronization"]["visible_event_frame"],
                        thermal_event_frame=cfg["synchronization"]["thermal_event_frame"],
                        thermal_offset_s=cfg["synchronization"]["thermal_offset_s"])
                    brackets = thermal_brackets(vis_times, aligned,
                        None if thermal[0].get("frame") is None else [row["frame"] for row in thermal],
                        thermal_fps=cfg["thermal"]["thermal_fps"])
                    invalid = int((~np.asarray(brackets["valid"], dtype=bool)).sum())
                    if invalid:
                        messages["Synchro"]["optional"].append(
                            f"{invalid} instant(s) VIS sans encadrement TH valide ; la température sera NaN à ces instants.")
                except Exception as error:
                    messages["Synchro"]["required"].append(f"Synchronisation invalide : {error}")
        else:
            applicable -= {"Thermique", "Synchro"}

    steps, required, optional = [], [], []
    for view in VIEWS:
        req = messages[view]["required"]
        opt = messages[view]["optional"]
        if view not in applicable:
            status = "inactive"
        elif req:
            status = "blocked"
        elif opt:
            status = "warning"
        elif view == "Résultats":
            status = "inactive"
        else:
            status = "complete"
        steps.append({"view": view, "status": status, "messages": req + opt})
        required.extend({"view": view, "message": message} for message in req)
        optional.extend({"view": view, "message": message} for message in opt)
    ready = not required
    job_step = next(step for step in steps if step["view"] == "Job Manager")
    job_step["status"] = "complete" if ready and not optional else "warning" if ready else "blocked"
    for step in steps:
        if step["view"] in ("Résultats", "Export") and step["status"] != "blocked":
            step["status"] = "complete" if checked is not None and has_results else "inactive"
    return {"ready": ready, "steps": steps, "required": required, "optional": optional}
