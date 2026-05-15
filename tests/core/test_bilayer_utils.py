"""Tests for bilayer stack parsing utilities."""

from rascal2.core.bilayer_utils import (
    _flatten_lipid,
    build_bilayer_specs,
    extract_bilayers_from_model,
)


class _Model:
    def __init__(self, stack):
        self.stack = stack


def test_extract_bilayers_from_model_removes_tokens_from_stack():
    model = _Model("air | bilayer(inner=DPPC, outer=POPC) | Si")

    found = extract_bilayers_from_model(model)

    assert found == [{"inner": "DPPC", "outer": "POPC"}]
    assert model.stack == "air | Si"


def test_extract_bilayers_from_model_ignores_non_matching_tokens():
    model = _Model("air | bilayer(inner=DPPC outer=POPC) | Si")

    found = extract_bilayers_from_model(model)

    assert found == [{"inner": "DPPC", "outer": "POPC"}]
    assert model.stack == "air | Si"


def test_extract_bilayers_from_model_finds_embedded_and_case_insensitive_tokens():
    model = _Model("air | BILAYER(inner=POPC, outer=DPPC) | Si")
    found = extract_bilayers_from_model(model)
    assert found == [{"inner": "POPC", "outer": "DPPC"}]
    assert model.stack == "air | Si"


def test_extract_bilayers_from_model_supports_quoted_values_and_key_order():
    model = _Model("air | bilayer(outer='POPC-d31', inner=\"d-DMPC\") | Si")
    found = extract_bilayers_from_model(model)
    assert found == [{"inner": "d-DMPC", "outer": "POPC-d31"}]
    assert model.stack == "air | Si"


def test_extract_bilayers_from_model_accepts_raw_stack_string():
    found = extract_bilayers_from_model("Si | bilayer(inner=POPC, outer=POPC) | D2O")
    assert found == [{"inner": "POPC", "outer": "POPC"}]


def test_flatten_lipid_defaults_when_missing_constants():
    flat = _flatten_lipid("inner", None)

    assert flat["v_head_inner"] == 300.0
    assert flat["v_tail_inner"] == 800.0
    assert flat["sl_head_inner"] == 300.0e-6
    assert flat["sl_tail_inner"] == 800.0e-6
    assert flat["sld_head_inner"] == 300.0e-6
    assert flat["sld_tail_inner"] == 800.0e-6


def test_flatten_lipid_uses_scattering_length_values_from_constants():
    consts = {
        "head_vol": 321.0,
        "head_sl": 1.2e-5,
        "tail_vol": 934.5,
        "tail_sl": -2.3e-5,
    }
    flat = _flatten_lipid("inner", consts)

    assert flat["v_head_inner"] == 321.0
    assert flat["sl_head_inner"] == 1.2e-5
    assert flat["v_tail_inner"] == 934.5
    assert flat["sl_tail_inner"] == -2.3e-5
    assert flat["sld_head_inner"] == 1.2e-5
    assert flat["sld_tail_inner"] == -2.3e-5


def test_build_bilayer_specs_uses_fallback_constants_without_molgroups():
    specs = build_bilayer_specs([{"inner": "DPPC", "outer": "POPC"}])
    assert len(specs) == 1
    assert specs[0]["inner"] == "DPPC"
    assert specs[0]["outer"] == "POPC"
    assert specs[0]["v_head_inner"] > 0.0
