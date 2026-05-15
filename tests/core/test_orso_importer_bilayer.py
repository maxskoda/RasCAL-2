"""Tests for bilayer-aware ORSO import."""

import importlib.util
from types import SimpleNamespace

import ratapi as rat

from rascal2.core import orso_importer


class _Quantity:
    def __init__(self, value):
        self._value = value

    def as_unit(self, _):
        return self._value


class _Material:
    def __init__(self, name, sld):
        self.name = name
        self.formula = name
        self._sld = sld

    def get_sld(self):
        return complex(self._sld, 0)


class _Layer:
    def __init__(self, name, thickness, roughness, sld):
        self.original_name = name
        self.material = _Material(name, sld)
        self.thickness = _Quantity(thickness)
        self.roughness = _Quantity(roughness)


class _Model:
    def __init__(self):
        self.stack = "Air | bilayer(inner=DPPC, outer=DPPC) | D2O"

    def resolve_to_layers(self):
        return [
            _Layer("Air", 0.0, 3.0, 0.0),
            _Layer("Oxide", 10.0, 3.0, 3.0e-6),
            _Layer("D2O", 0.0, 3.0, 6.35e-6),
        ]


class _Dataset:
    def __init__(self):
        self.info = SimpleNamespace(
            data_source=SimpleNamespace(sample=SimpleNamespace(name="C1", model=_Model()))
        )
        self.data = [[0.01, 1.0, 0.1]]


def test_import_ort_to_project_switches_to_custom_layers_for_bilayer(tmp_path, monkeypatch):
    ort_file = tmp_path / "test.ort"
    ort_file.write_text("dummy")
    monkeypatch.setattr(orso_importer, "load_orso", lambda *_: [_Dataset()])

    project = rat.Project(name="test")
    out_project, out_controls = orso_importer.import_ort_to_project(
        str(ort_file), project, str(tmp_path / "proj")
    )

    assert out_controls is None
    assert out_project.model == "custom layers"
    assert out_project.custom_files[0].name == "ORSO Bilayer Model"
    assert out_project.custom_files[0].path == str((tmp_path / "proj").resolve())
    assert out_project.contrasts[0].model == ["ORSO Bilayer Model"]
    assert [p.name for p in out_project.parameters[:4]] == [
        "Substrate Roughness",
        "Oxide thickness",
        "Oxide rough",
        "Oxide SLD",
    ]
    assert any(p.name == "Bilayer1 APM" for p in out_project.parameters)
    assert (tmp_path / "proj" / "orso_bilayer_model.py").exists()


def test_write_bilayer_custom_model_converts_scattering_lengths_to_slds(tmp_path):
    function_name = orso_importer._write_bilayer_custom_model(
        tmp_path,
        "generated_model.py",
        [],
        [
            {
                "v_head_inner": 100.0,
                "sl_head_inner": 4.0e-4,
                "v_tail_inner": 200.0,
                "sl_tail_inner": -2.0e-4,
                "v_head_outer": 100.0,
                "sl_head_outer": 5.0e-4,
                "v_tail_outer": 200.0,
                "sl_tail_outer": -4.0e-4,
            }
        ],
    )
    spec = importlib.util.spec_from_file_location("generated_model", tmp_path / "generated_model.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    layers, sub_rough = getattr(module, function_name)(
        [3.0, 50.0, 0.25, 0.5, 0.1, 4.0], [], [6.0e-6], 0
    )

    assert sub_rough == 3.0
    assert layers[0, 1] == (0.25 * 6.0e-6) + (0.75 * (4.0e-4 / 100.0))
    assert layers[1, 1] == (0.1 * 6.0e-6) + (0.9 * (-2.0e-4 / 200.0))
    assert layers[2, 1] == (0.1 * 6.0e-6) + (0.9 * (-4.0e-4 / 200.0))
    assert layers[3, 1] == (0.5 * 6.0e-6) + (0.5 * (5.0e-4 / 100.0))


def test_write_bilayer_custom_model_uses_fit_params_for_base_layers(tmp_path):
    function_name = orso_importer._write_bilayer_custom_model(
        tmp_path,
        "generated_model.py",
        [
            {
                "name": "Oxide",
                "thickness": 10.0,
                "thickness_param": "Oxide thickness",
                "sld": 2.0e-6,
                "sld_param": "Oxide SLD",
                "roughness": 3.0,
                "roughness_param": "Oxide rough",
            }
        ],
        [
            {
                "v_head_inner": 100.0,
                "sl_head_inner": 4.0e-4,
                "v_tail_inner": 200.0,
                "sl_tail_inner": -2.0e-4,
                "v_head_outer": 100.0,
                "sl_head_outer": 5.0e-4,
                "v_tail_outer": 200.0,
                "sl_tail_outer": -4.0e-4,
            }
        ],
    )
    spec = importlib.util.spec_from_file_location("generated_model", tmp_path / "generated_model.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    layers, _ = getattr(module, function_name)(
        [3.0, 12.0, 4.0, 3.0e-6, 50.0, 0.25, 0.5, 0.1, 4.0], [], [6.0e-6], 0
    )

    assert layers[0].tolist() == [12.0, 3.0e-6, 4.0]
    assert layers[1, 1] == (0.25 * 6.0e-6) + (0.75 * (4.0e-4 / 100.0))
