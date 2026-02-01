from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from numba.core.types import NoneType
from orsopy.fileio import load_orso
import ratapi as rat

# ✅ Data is not at ratapi.Data; it's in ratapi.models
try:
    from ratapi.models import Data
except Exception:
    # very defensive fallback (depending on ratapi version)
    try:
        from ratapi.models.data import Data  # type: ignore
    except Exception as e:
        raise ImportError(
            "Could not import ratapi.models.Data. "
            "Check your ratapi installation/version."
        ) from e


KNOWN_BULKS = ["D2O", "H2O", "AuMW", "SiMW", "SMW", "Si", "Air"]


def _sanitize_name(s: str, fallback: str) -> str:
    s = str(s or "").strip()
    s = " ".join(s.split())
    return s if s else fallback


def _infer_bulk_name_from_layer(layer_obj, fallback: str) -> str:
    """
    Infer a bulk name from an orsopy Layer, using:
      material.name, original_name, formula (very light heuristics).
    """
    mat = getattr(layer_obj, "material", None)

    # material.name
    mat_name = getattr(mat, "name", None)
    if isinstance(mat_name, str) and mat_name.strip():
        for kb in KNOWN_BULKS:
            if kb.lower() in mat_name.lower():
                return kb

    # layer original_name
    orig = getattr(layer_obj, "original_name", None)
    if isinstance(orig, str) and orig.strip():
        for kb in KNOWN_BULKS:
            if kb.lower() in orig.lower():
                return kb

    # formula heuristics
    formula = getattr(mat, "formula", None)
    if isinstance(formula, str) and formula.strip():
        f = formula.lower()
        if "d2o" in f:
            return "D2O"
        if "h2o" in f:
            return "H2O"

    return fallback


def _safe_get_sld(material) -> float:
    try:
        if material is not None and hasattr(material, "get_sld"):
            return float(material.get_sld().real)
    except Exception:
        pass
    return 0.0


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _ensure_bulk_parameter_exists(project: rat.Project, which: str, bulk_name: str, sld_value: float | None) -> str:
    """
    Ensure a bulk parameter exists and return the reference name used by contrasts (e.g. "SLD D2O").

    Key rule: if sld_value is None, do NOT modify existing parameters (prevents out-of-range errors).
    """
    ref_name = bulk_name
    if not ref_name.lower().startswith("sld "):
        ref_name = f"SLD {ref_name}"

    # Find the parameter container on the project
    if which.lower() in ("in", "bulkin", "bulk_in"):
        attr_candidates = ["bulk_in", "bulkIn"]
    else:
        attr_candidates = ["bulk_out", "bulkOut"]

    target = None
    for a in attr_candidates:
        if hasattr(project, a):
            target = getattr(project, a)
            break

    # If we can't find the table, still return the name (contrasts may still work)
    if target is None:
        return ref_name

    # If row exists, only update when we have a real SLD
    try:
        for row in target:
            if getattr(row, "name", None) == ref_name:
                if sld_value is None:
                    return ref_name  # keep whatever is already in the project

                v = float(sld_value)
                lo = min(v * 0.95, v * 1.05)
                hi = max(v * 0.95, v * 1.05)

                if hasattr(row, "min"):
                    row.min = lo
                if hasattr(row, "max"):
                    row.max = hi
                if hasattr(row, "value"):
                    row.value = v
                return ref_name
    except Exception:
        pass

    # Row doesn't exist → only create if we actually know the SLD
    if sld_value is None:
        return ref_name

    try:
        Param = getattr(rat, "Parameter", None)
        if Param is not None:
            v = float(sld_value)
            lo = min(v * 0.95, v * 1.05)
            hi = max(v * 0.95, v * 1.05)
            target.append(Param(name=ref_name, min=lo, value=v, max=hi, fit=False))
    except Exception:
        pass

    return ref_name



def import_ort_to_project(
    ort_path: str,
    base_project: rat.Project,
    project_folder: str,
) -> tuple[rat.Project, Optional[rat.Controls]]:
    """
    Convert an ORSO .ort file into a ratapi.Project usable by RasCAL-2.

    - reads ORSO datasets into ratapi.models.Data objects
    - creates one Contrast per dataset
    - keeps existing background/resolution/scalefactor names from base_project
    - infers bulk_in/bulk_out names (and seeds SLD best-effort) from ORSO model resolve_to_layers()

    Returns
    -------
    (project, controls_or_none)
    """
    ort_file = Path(ort_path).expanduser().resolve()
    proj_dir = Path(project_folder).expanduser().resolve()

    _ensure_dir(proj_dir)
    _ensure_dir(proj_dir / "data")

    # Copy ORT into project folder for provenance
    copied_ort = proj_dir / "data" / ort_file.name
    if copied_ort.resolve() != ort_file:
        shutil.copy2(ort_file, copied_ort)

    # Start from base project so required defaults exist
    project = base_project

    # Clear defaults created by create_project()
    project.contrasts.clear()
    project.data.clear()

    orso = load_orso(str(copied_ort))

    default_background = "Background 1"
    default_resolution = "Resolution 1"
    default_scalefactor = "Scalefactor 1"

    fallback_bulk_in = "Air"
    fallback_bulk_out = "D2O"

    for i, ds in enumerate(orso, start=1):
        sample = ds.info.data_source.sample
        cname = _sanitize_name(getattr(sample, "name", None), f"Contrast {i}")

        data_arr = np.asarray(ds.data)
        if data_arr.ndim != 2 or data_arr.shape[1] < 2:
            raise ValueError(f"Dataset '{cname}' does not look like Nx2/Nx3 data.")

        # ensure Nx3
        if data_arr.shape[1] == 2:
            q = data_arr[:, 0]
            r = data_arr[:, 1]
            dr = np.maximum(1e-12, 0.05 * np.abs(r))
            data_arr = np.vstack([q, r, dr]).T
        else:
            data_arr = data_arr[:, :3]

        data_name = cname

        # Infer bulks from model if possible
        bulk_in_name = fallback_bulk_in
        bulk_out_name = fallback_bulk_out
        bulk_in_sld = None
        bulk_out_sld = None

        model = getattr(sample, "model", None)
        if model is not None:
            try:
                resolved_layers = model.resolve_to_layers()
                if resolved_layers and len(resolved_layers) >= 2:
                    bulk_in_layer = resolved_layers[0]
                    bulk_out_layer = resolved_layers[-1]
                    bulk_in_name = _infer_bulk_name_from_layer(bulk_in_layer, fallback_bulk_in)
                    bulk_out_name = _infer_bulk_name_from_layer(bulk_out_layer, fallback_bulk_out)
                    bulk_in_sld = _safe_get_sld(getattr(bulk_in_layer, "material", None))
                    bulk_out_sld = _safe_get_sld(getattr(bulk_out_layer, "material", None))
            except Exception:
                # resolve_to_layers can fail for custom tokens (e.g. bilayer)
                pass

        bulk_in_ref = _ensure_bulk_parameter_exists(project, "in", bulk_in_name, bulk_in_sld)
        bulk_out_ref = _ensure_bulk_parameter_exists(project, "out", bulk_out_name, bulk_out_sld)

        # ✅ Use ratapi.models.Data (NOT rat.Data)
        project.data.append(Data(name=data_name, data=data_arr))

        project.contrasts.append(
            name=cname,
            background=default_background,
            resolution=default_resolution,
            scalefactor=default_scalefactor,
            bulk_in=bulk_in_ref,
            bulk_out=bulk_out_ref,
            data=data_name,
        )

    # Defensive: fix any out-of-range parameter values before RAT tries to run
    _clamp_all_parameter_values(project)
    return project, None

def _clamp_all_parameter_values(project: rat.Project) -> None:
    """
    Defensive fix:
    Ensure every Parameter-like object in the project has value within [min, max].
    This prevents Pydantic validation errors during rat.run() if something ended up out-of-range
    (e.g. SLD D2O value accidentally 0.0 but min/max are ~6.3e-6).
    """
    def clamp_row(row) -> None:
        if not hasattr(row, "value") or not hasattr(row, "min") or not hasattr(row, "max"):
            return
        try:
            v = float(row.value)
            mn = float(row.min)
            mx = float(row.max)
        except Exception:
            return

        if mn > mx:
            # swap if corrupt
            mn, mx = mx, mn

        # If value is outside, clamp it (assignment triggers pydantic validation, so we must clamp)
        if v < mn:
            row.value = mn
        elif v > mx:
            row.value = mx

    # Scan common project containers (ratapi varies slightly by version, so be flexible)
    for attr in dir(project):
        if attr.startswith("_"):
            continue
        try:
            obj = getattr(project, attr)
        except Exception:
            continue

        # Many are lists of Parameter objects (bulk_in, bulk_out, backgrounds, parameters, scalefactors, etc.)
        if isinstance(obj, list) and obj:
            for row in obj:
                clamp_row(row)
