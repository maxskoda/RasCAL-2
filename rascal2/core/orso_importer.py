from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from orsopy.fileio import load_orso

import ratapi as rat
from ratapi.models import Data, Parameter, Layer


# -----------------------------------------------------------------------------
# Constants / helpers
# -----------------------------------------------------------------------------

KNOWN_BULKS = ["D2O", "H2O", "AuMW", "SiMW", "SMW", "Si", "Air"]


def _sanitize_name(s: str, fallback: str) -> str:
    s = str(s or "").strip()
    s = " ".join(s.split())
    return s if s else fallback


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_get_sld(material) -> float:
    if material is None:
        return 0.0
    try:
        if hasattr(material, "get_sld"):
            return float(material.get_sld().real)
    except Exception:
        pass
    return 0.0


def _infer_bulk_name_from_layer(layer, fallback: str) -> str:
    mat = getattr(layer, "material", None)
    for src in (
        getattr(mat, "name", None),
        getattr(layer, "original_name", None),
        getattr(mat, "formula", None),
    ):
        if isinstance(src, str):
            for kb in KNOWN_BULKS:
                if kb.lower() in src.lower():
                    return kb
    return fallback


def _infer_bulk_name_from_text(text: str, fallback: str) -> str:
    s = (text or "").lower()
    for kb in KNOWN_BULKS:
        if kb.lower() in s:
            return kb
    return fallback


def _ensure_bulk_parameter_exists(
    project: rat.Project,
    which: str,
    bulk_name: str,
    sld_value: float,
) -> str:
    ref = bulk_name if bulk_name.lower().startswith("sld ") else f"SLD {bulk_name}"
    table = project.bulk_in if which == "in" else project.bulk_out

    for row in table:
        if row.name == ref:
            if sld_value != 0.0:
                v = float(sld_value)
                row.min = min(float(row.min), v)
                row.max = max(float(row.max), v)
                row.value = v
            return ref

    RowCls = table[0].__class__ if table else None
    if RowCls is None:
        return ref

    if sld_value != 0.0:
        v = float(sld_value)
        mn, mx = v * 0.95, v * 1.05
    else:
        v, mn, mx = 0.0, -1e-6, 1e-6

    payload = dict(name=ref, min=mn, value=v, max=mx, fit=False)
    allowed = getattr(RowCls, "model_fields", {}).keys()
    payload = {k: v for k, v in payload.items() if k in allowed}

    table.append(RowCls(**payload))
    return ref


def _span(val: float, frac: float = 0.25, floor: float | None = None):
    if abs(val) < 1e-12:
        return -1e-6, 0.0, 1e-6
    lo = val * (1 - frac)
    hi = val * (1 + frac)
    if floor is not None:
        lo = max(lo, floor)
    return min(lo, hi), val, max(lo, hi)


def _ensure_parameter(
    project: rat.Project,
    name: str,
    value: float,
    frac: float = 0.25,
    floor: float | None = None,
) -> str:
    pmin, pval, pmax = _span(value, frac, floor)
    for p in project.parameters:
        if p.name == name:
            p.min = min(float(p.min), pmin)
            p.max = max(float(p.max), pmax)
            p.value = pval
            return name

    project.parameters.append(
        Parameter(name=name, min=pmin, value=pval, max=pmax, fit=True)
    )
    return name


# -----------------------------------------------------------------------------
# Main importer
# -----------------------------------------------------------------------------

def import_ort_to_project(
    ort_path: str,
    base_project: rat.Project,
    project_folder: str,
) -> tuple[rat.Project, Optional[rat.Controls]]:
    """
    Import ORSO (.ort) into RasCAL-2 standard-layers project.
    """

    ort_file = Path(ort_path).resolve()
    proj_dir = Path(project_folder).resolve()

    _ensure_dir(proj_dir)
    _ensure_dir(proj_dir / "data")

    copied_ort = proj_dir / "data" / ort_file.name
    if copied_ort != ort_file:
        shutil.copy2(ort_file, copied_ort)

    project = base_project

    # Clear defaults safely
    project.contrasts.clear()
    project.data.clear()
    project.layers.clear()

    project.model = "standard layers"

    orso = load_orso(str(copied_ort))

    default_background = "Background 1"
    default_resolution = "Resolution 1"
    default_scalefactor = "Scalefactor 1"

    # ------------------------------------------------------------
    # Resolve shared layer stack from first dataset
    # ------------------------------------------------------------

    bulk_in_ref = "SLD Air"
    bulk_out_ref_default = "SLD D2O"
    layer_name_stack: list[str] = []

    if orso:
        sample0 = orso[0].info.data_source.sample
        model0 = getattr(sample0, "model", None)

        if model0 is not None:
            try:
                resolved = model0.resolve_to_layers()
                if len(resolved) >= 2:
                    bulk_in = resolved[0]
                    bulk_out = resolved[-1]

                    bulk_in_ref = _ensure_bulk_parameter_exists(
                        project,
                        "in",
                        _infer_bulk_name_from_layer(bulk_in, "Air"),
                        _safe_get_sld(bulk_in.material),
                    )

                    bulk_out_ref_default = _ensure_bulk_parameter_exists(
                        project,
                        "out",
                        _infer_bulk_name_from_layer(bulk_out, "D2O"),
                        _safe_get_sld(bulk_out.material),
                    )

                    for li in resolved[1:-1]:
                        lname = _sanitize_name(
                            getattr(li, "original_name", None)
                            or getattr(li.material, "name", None),
                            "Layer",
                        )

                        t = float(li.thickness.as_unit("angstrom"))
                        r = float(li.roughness.as_unit("angstrom"))
                        s = _safe_get_sld(li.material)

                        t_p = _ensure_parameter(project, f"{lname} thickness", t, floor=0.0)
                        r_p = _ensure_parameter(project, f"{lname} rough", r, floor=0.0)
                        s_p = _ensure_parameter(project, f"{lname} SLD", s)

                        project.layers.append(
                            Layer(name=lname, thickness=t_p, roughness=r_p, SLD_real=s_p)
                        )
                        layer_name_stack.append(lname)
            except Exception as e:
                print("ORSO model resolution failed:", e)

    # ------------------------------------------------------------
    # Data + contrasts
    # ------------------------------------------------------------

    for i, ds in enumerate(orso, start=1):
        sample = ds.info.data_source.sample
        cname = _sanitize_name(getattr(sample, "name", None), f"Contrast {i}")

        arr = np.asarray(ds.data)
        if arr.shape[1] == 2:
            q, r = arr.T
            dr = np.maximum(1e-12, 0.05 * abs(r))
            arr = np.vstack([q, r, dr]).T
        else:
            arr = arr[:, :3]

        project.data.append(Data(name=cname, data=arr))

        bulk_out_ref = bulk_out_ref_default

        model = getattr(sample, "model", None)
        if model is not None:
            try:
                resolved = model.resolve_to_layers()
                bulk_out = resolved[-1]
                bulk_out_ref = _ensure_bulk_parameter_exists(
                    project,
                    "out",
                    _infer_bulk_name_from_layer(bulk_out, "D2O"),
                    _safe_get_sld(bulk_out.material),
                )
            except Exception:
                bulk = _infer_bulk_name_from_text(cname, "D2O")
                bulk_out_ref = _ensure_bulk_parameter_exists(project, "out", bulk, 0.0)

        project.contrasts.append(
            name=cname,
            background=default_background,
            resolution=default_resolution,
            scalefactor=default_scalefactor,
            bulk_in=bulk_in_ref,
            bulk_out=bulk_out_ref,
            data=cname,
            model=layer_name_stack,
        )

    return project, None
