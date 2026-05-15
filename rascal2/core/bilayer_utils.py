"""Utilities for parsing bilayer(...) stack tokens in ORSO models."""

from __future__ import annotations

import re

try:
    import numpy as np
    import molgroups.lipids as lipids

    HAS_MOLGROUPS = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_MOLGROUPS = False
    np = None
    lipids = None


RE_BILAYER_BLOCK = re.compile(r"""bilayer\s*\((.*?)\)""", flags=re.IGNORECASE)
RE_BILAYER_KV = re.compile(
    r"""\b(inner|outer)\b\s*=\s*(".*?"|'.*?'|[^,\s\)]+)""",
    flags=re.IGNORECASE,
)


def scalar_nsl(x):
    """Convert molgroups nSLs (scalar or array) to a single float."""
    if np is None:
        try:
            return float(x)
        except Exception:
            return 0.0
    try:
        arr = np.array(x)
        return float(arr.sum())
    except Exception:
        try:
            return float(x)
        except Exception:
            return 0.0


def get_lipid_constants(lipid_name: str):
    """Get head/tail volumes and scattering lengths for a lipid from molgroups.lipids."""
    if not HAS_MOLGROUPS:
        return None

    obj = getattr(lipids, lipid_name, None)
    if obj is None:
        obj = getattr(lipids, "DPPC")

    try:
        head_components = obj.headgroup[1]["components"]
        head_vol = sum(getattr(c, "cell_volume", 0.0) for c in head_components)
        head_nsl = scalar_nsl([getattr(c, "nSLs", 0.0) for c in head_components])
    except Exception:
        head_vol = 0.0
        head_nsl = 0.0

    if head_vol <= 0:
        head_vol = float(getattr(obj, "headgroup_volume", 0.0) or 0.0)
    if head_vol <= 0:
        head_vol = 330.0

    head_sl = head_nsl * 1e-5 if head_nsl != 0 else 0.0

    try:
        tail = obj.tails
        tail_vol = float(getattr(tail, "cell_volume", 0.0) or 0.0)
        tail_nsl = scalar_nsl(getattr(tail, "nSLs", 0.0))
    except Exception:
        tail_vol = 0.0
        tail_nsl = 0.0
    if tail_vol <= 0:
        tail_vol = 800.0

    tail_sl = tail_nsl * 1e-5 if tail_nsl != 0 else 0.0

    return {
        "name": lipid_name,
        "head_vol": float(head_vol),
        "head_sl": float(head_sl),
        "tail_vol": float(tail_vol),
        "tail_sl": float(tail_sl),
    }


def extract_bilayers_from_model(model):
    """Extract bilayer(inner=XXX, outer=YYY) tokens from model.stack."""
    if isinstance(model, str):
        stack = model
        can_rewrite_stack = False
    else:
        stack = getattr(model, "stack", "")
        can_rewrite_stack = hasattr(model, "stack")
    bilayers = []
    for block in RE_BILAYER_BLOCK.finditer(stack):
        kv = {}
        for m in RE_BILAYER_KV.finditer(block.group(1)):
            key = m.group(1).lower()
            value = m.group(2).strip().strip("\"'")
            kv[key] = value
        if "inner" in kv and "outer" in kv:
            bilayers.append({"inner": kv["inner"], "outer": kv["outer"]})

    cleaned = RE_BILAYER_BLOCK.sub("", stack)
    # Normalize separators that may be left behind after removing bilayer tokens.
    parts = [p.strip() for p in cleaned.split("|") if p.strip()]
    if can_rewrite_stack:
        model.stack = " | ".join(parts)
    return bilayers


def _flatten_lipid(prefix: str, consts):
    """Expand molgroups lipid constants into flat keys with fallback."""
    if consts is None:
        return {
            f"v_head_{prefix}": 300.0,
            f"v_tail_{prefix}": 800.0,
            f"sl_head_{prefix}": 300.0e-6,
            f"sl_tail_{prefix}": 800.0e-6,
            # Legacy key names retained for generated-model compatibility.
            f"sld_head_{prefix}": 300.0e-6,
            f"sld_tail_{prefix}": 800.0e-6,
        }
    return {
        f"v_head_{prefix}": consts["head_vol"],
        f"sl_head_{prefix}": consts["head_sl"],
        f"v_tail_{prefix}": consts["tail_vol"],
        f"sl_tail_{prefix}": consts["tail_sl"],
        # Legacy key names retained for generated-model compatibility.
        f"sld_head_{prefix}": consts["head_sl"],
        f"sld_tail_{prefix}": consts["tail_sl"],
    }


def build_bilayer_specs(bilayer_specs_raw):
    """Build enriched bilayer constants from parsed bilayer stack tokens."""
    bilayer_specs = []
    if not bilayer_specs_raw:
        return bilayer_specs

    for spec in bilayer_specs_raw:
        inner = spec["inner"]
        outer = spec["outer"]
        inner_consts = get_lipid_constants(inner) if HAS_MOLGROUPS else None
        outer_consts = get_lipid_constants(outer) if HAS_MOLGROUPS else None
        bilayer_specs.append(
            {
                "inner": inner,
                "outer": outer,
                **_flatten_lipid("inner", inner_consts),
                **_flatten_lipid("outer", outer_consts),
            }
        )
    return bilayer_specs
