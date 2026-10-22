import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pydantic
import pytest
import ratapi
from PyQt6 import QtCore, QtWidgets
from ratapi.utils.enums import Languages

import rascal2.widgets.delegates as delegates
from rascal2.widgets.project.tables import (
    BackgroundsModel,
    ClassListTableModel,
    CustomFileModel,
    CustomFileWidget,
    DomainContrastWidget,
    DomainsModel,
    LayerFieldWidget,
    LayersModel,
    ParameterFieldWidget,
    ParametersModel,
    ProjectFieldWidget,
    ResolutionsModel,
)


class MockMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.presenter = MagicMock()
        self.update_project = MagicMock()


class DataModel(pydantic.BaseModel, validate_assignment=True):
    """Test Pydantic model."""

    name: str = "Test Model"
    value: int = 15


@pytest.fixture
def classlist():
    """Test ClassList."""
    return ratapi.ClassList(
        [
            DataModel(name="A", value=1),
            DataModel(name="B", value=6),
            DataModel(name="C", value=18),
        ]
    )


@pytest.fixture
def table_model(classlist):
    """Test ClassListTableModel."""
    return ClassListTableModel(classlist, parent)


@pytest.fixture
def param_classlist():
    def _classlist(protected_indices):
        return ratapi.ClassList(
            [
                ratapi.models.ProtectedParameter(name=str(i)) if i in protected_indices else ratapi.models.Parameter()
                for i in [0, 1, 2]
            ]
        )

    return _classlist


@pytest.fixture
def domains_classlist():
    return ratapi.ClassList(
        [
            ratapi.models.DomainContrast(name="A", model=["LA"]),
            ratapi.models.DomainContrast(name="B", model=["LB", "LB2", "LB3"]),
            ratapi.models.DomainContrast(name="C", model=["LC", "LC2"]),
        ]
    )


@pytest.fixture
def param_model(param_classlist):
    def _param_model(protected_indices):
        model = ParametersModel(param_classlist(protected_indices), parent)
        return model

    return _param_model


parent = MockMainWindow()


def test_model_init(table_model, classlist):
    """Test that initialisation works correctly for ClassListTableModels."""
    model = table_model

    assert model.classlist == classlist
    assert model.item_type == DataModel
    assert model.headers == ["name", "value"]
    assert not model.edit_mode


def test_model_layout_data(table_model):
    """Test that the model layout and data is as expected."""
    model = table_model

    assert model.rowCount() == 3
    assert model.columnCount() == 3

    expected_data = [[None, "A", 1], [None, "B", 6], [None, "C", 18]]
    headers = [None, "Name", "Value"]

    for row in [0, 1, 2]:
        for column in [0, 1, 2]:
            assert model.data(model.index(row, column)) == expected_data[row][column]

    for column in [0, 1, 2]:
        assert model.headerData(column, QtCore.Qt.Orientation.Horizontal) == headers[column]


def test_model_set_data(table_model):
    """Test that data can be set successfully, but is thrown out if it breaks the Pydantic model rules."""
    model = table_model

    assert model.setData(model.index(1, 2), 4)
    assert model.classlist[1].value == 4

    assert model.setData(model.index(1, 1), "D")
    assert model.classlist[1].name == "D"

    assert not model.setData(model.index(2, 2), 19.4)
    assert model.classlist[2].value == 18


def test_append(table_model):
    """Test that append_item successfully adds an item of the relevant type."""
    model = table_model

    model.append_item()

    assert len(model.classlist) == 4
    assert model.classlist[-1].name == "Test Model"
    assert model.classlist[-1].value == 15


def test_delete(table_model):
    """Test that delete_item deletes the item at the desired index."""
    model = table_model

    model.delete_item(1)

    assert len(model.classlist) == 2
    assert [m.name for m in model.classlist] == ["A", "C"]
    assert [m.value for m in model.classlist] == [1, 18]


def test_project_field_init():
    """Test that the ProjectFieldWidget is initialised correctly."""
    widget = ProjectFieldWidget("test", parent)

    assert widget.table.model() is None
    assert widget.add_button.isHidden()


def test_project_field_update_model(classlist):
    """Test that the correct changes are made when the model is updated in the ProjectFieldWidget."""
    widget = ProjectFieldWidget("test", parent)
    widget.update_model(classlist)

    assert widget.table.isColumnHidden(0)

    assert widget.model.classlist == classlist
    assert isinstance(
        widget.table.itemDelegateForColumn(1).createEditor(None, None, widget.model.index(1, 1)),
        QtWidgets.QLineEdit,
    )
    assert isinstance(
        widget.table.itemDelegateForColumn(2).createEditor(None, None, widget.model.index(1, 2)),
        QtWidgets.QSpinBox,
    )


def test_edit_mode(classlist):
    """Test that edit mode makes the expected changes."""
    widget = ProjectFieldWidget("test", parent)
    widget.update_model(classlist)
    widget.edit()

    assert widget.model.edit_mode
    assert not widget.add_button.isHidden()
    assert not widget.table.isColumnHidden(0)

    for row in [0, 1, 2]:
        assert isinstance(widget.table.indexWidget(widget.model.index(row, 0)), QtWidgets.QPushButton)


def test_delete_button(classlist):
    """Test that delete buttons work as expected."""
    widget = ProjectFieldWidget("Test", parent)
    widget.update_model(classlist)

    delete_button = widget.make_delete_button(1)
    delete_button.click()

    assert len(widget.model.classlist) == 2
    assert [m.name for m in widget.model.classlist] == ["A", "C"]
    assert [m.value for m in widget.model.classlist] == [1, 18]


def test_parameter_edit_mode(param_classlist):
    """Test that parameter tab edit mode makes the expected changes."""
    widget = ProjectFieldWidget("Test", parent)
    widget.update_model(param_classlist([]))
    widget.edit()

    assert widget.model.edit_mode
    assert not widget.add_button.isHidden()
    assert not widget.table.isColumnHidden(0)

    for row in [0, 1, 2]:
        assert isinstance(widget.table.indexWidget(widget.model.index(row, 0)), QtWidgets.QPushButton)


@pytest.mark.parametrize("protected", ([], [0, 2], [1]))
@pytest.mark.parametrize("prior_type", ("uniform", "gaussian"))
def test_parameter_flags(param_model, prior_type, protected):
    """Test that protected parameters are successfully recorded and flagged, and parameter flags are set correctly."""
    model = param_model(protected)
    for param in model.classlist:
        param.prior_type = prior_type

    assert model.protected_indices == protected

    model.edit_mode = True

    for row in [0, 1, 2]:
        for column in range(1, model.columnCount()):
            item_flags = model.flags(model.index(row, column))
            match model.headers[column - 1]:
                case "name":
                    if row in protected:
                        assert not item_flags & QtCore.Qt.ItemFlag.ItemIsEditable
                    else:
                        assert item_flags & QtCore.Qt.ItemFlag.ItemIsEditable
                case "fit":
                    assert item_flags & QtCore.Qt.ItemFlag.ItemIsUserCheckable
                case "mu" | "sigma":
                    if prior_type == "uniform":
                        assert item_flags == QtCore.Qt.ItemFlag.NoItemFlags
                    else:
                        assert item_flags & QtCore.Qt.ItemFlag.ItemIsEditable


def test_param_item_delegates(param_classlist):
    """Test that parameter models have the expected item delegates."""
    widget = ParameterFieldWidget("Test", parent)
    widget.parent = MagicMock()
    widget.update_model(param_classlist([]))

    for column, header in enumerate(widget.model.headers, start=1):
        if header in ["min", "value", "max"]:
            assert isinstance(widget.table.itemDelegateForColumn(column), delegates.ValueSpinBoxDelegate)
        else:
            assert isinstance(widget.table.itemDelegateForColumn(column), delegates.ValidatedInputDelegate)


def test_hidden_bayesian_columns(param_classlist):
    """Test that Bayes columns are hidden when procedure is not Bayesian."""
    widget = ParameterFieldWidget("Test", parent)
    widget.parent = MagicMock()
    widget.update_model(param_classlist([]))
    mock_controls = widget.parent.parent.parent_model.controls = MagicMock()
    mock_controls.procedure = "calculate"
    bayesian_columns = ["prior_type", "mu", "sigma"]

    widget.handle_bayesian_columns("calculate")

    for item in bayesian_columns:
        index = widget.model.headers.index(item)
        assert widget.table.isColumnHidden(index + 1)

    widget.handle_bayesian_columns("dream")

    for item in bayesian_columns:
        index = widget.model.headers.index(item)
        assert not widget.table.isColumnHidden(index + 1)


def test_layer_model_init():
    """Test that LayersModels have the correct absorption value based on the initial input."""
    init_list = ratapi.ClassList()
    init_list._class_handle = ratapi.models.Layer

    model = LayersModel(init_list, parent)
    assert not model.absorption

    init_list._class_handle = ratapi.models.AbsorptionLayer
    model = LayersModel(init_list, parent)
    assert model.absorption


def test_layer_model_append():
    """Test that LayersModels appends the correct item based on absorption value."""
    init_list = ratapi.ClassList()
    init_list._class_handle = ratapi.models.Layer
    model = LayersModel(init_list, parent)
    model.parent = MagicMock()

    model.append_item()

    assert isinstance(model.classlist[0], ratapi.models.Layer)

    del model.classlist[0]
    model.set_absorption(True)
    model.append_item()

    assert isinstance(model.classlist[0], ratapi.models.AbsorptionLayer)


def test_layer_model_set_absorption():
    """Test that the layer model layers are converted when set_absorption is called."""
    init_list = ratapi.ClassList(
        [
            ratapi.models.Layer(name="A", thickness="AT", SLD="AS", roughness="AR", hydrate_with="bulk in"),
            ratapi.models.Layer(name="B", thickness="BT", SLD="BS", roughness="BR"),
            ratapi.models.Layer(name="C", thickness="CT", SLD="CS", roughness="CR", hydration="CH"),
        ]
    )

    model = LayersModel(init_list, parent)
    model.parent = MagicMock()

    model.set_absorption(True)
    for expected, actual in zip(init_list, model.classlist, strict=False):
        assert isinstance(actual, ratapi.models.AbsorptionLayer)
        assert expected.name == actual.name
        assert expected.thickness == actual.thickness
        assert expected.SLD == actual.SLD_real  # noqa: SIM300  (false positive)
        assert expected.roughness == actual.roughness

    model.classlist[1].SLD_imaginary = "BSI"

    model.set_absorption(False)
    assert model.classlist == init_list
    assert model.SLD_imags == {"A": "", "B": "BSI", "C": ""}

    model.set_absorption(True)
    assert model.classlist[1].SLD_imaginary == "BSI"


@pytest.mark.parametrize(
    "init_list",
    [
        ratapi.ClassList(
            [
                ratapi.models.Layer(thickness="AT", SLD="AS", roughness="AR"),
                ratapi.models.Layer(thickness="BT", SLD="BS", roughness="BR"),
                ratapi.models.Layer(thickness="CT", SLD="CS", roughness="CR"),
            ]
        ),
        ratapi.ClassList(
            [
                ratapi.models.AbsorptionLayer(thickness="AT", SLD_real="AS", SLD_imaginary="ASI", roughness="AR"),
                ratapi.models.AbsorptionLayer(thickness="BT", SLD_real="BS", SLD_imaginary="BSI", roughness="BR"),
                ratapi.models.AbsorptionLayer(thickness="CT", SLD_real="CS", SLD_imaginary="CSI", roughness="CR"),
            ]
        ),
    ],
)
def test_layer_widget_delegates(init_list):
    """Test that the LayerFieldWidget has the expected delegates."""
    expected_delegates = {
        "name": delegates.ValidatedInputDelegate,
        "thickness": delegates.ProjectFieldDelegate,
        "SLD": delegates.ProjectFieldDelegate,
        "SLD_real": delegates.ProjectFieldDelegate,
        "SLD_imaginary": delegates.ProjectFieldDelegate,
        "roughness": delegates.ProjectFieldDelegate,
        "hydration": delegates.ProjectFieldDelegate,
        "hydrate_with": delegates.ValidatedInputDelegate,
    }

    widget = LayerFieldWidget("test", parent)
    widget.update_model(init_list)

    for i, header in enumerate(widget.model.headers):
        assert isinstance(widget.table.itemDelegateForColumn(i + 1), expected_delegates[header])


@pytest.mark.parametrize("edit_mode", [True, False])
def test_domains_model_flags(edit_mode, domains_classlist):
    """Test that the DomainsModel flags are set correctly."""
    model = DomainsModel(domains_classlist, parent)
    model.edit_mode = edit_mode
    for row in [0, 1, 2]:
        for column in [1, 2]:
            assert bool(model.flags(model.index(row, column)) & QtCore.Qt.ItemFlag.ItemIsEditable) == edit_mode


def test_domains_widget_item_delegates(domains_classlist):
    """Test that the domains widget has the expected item delegates."""
    widget = DomainContrastWidget("Test", parent)
    widget.update_model(domains_classlist)
    assert isinstance(widget.table.itemDelegateForColumn(1), delegates.ValidatedInputDelegate)
    assert isinstance(widget.table.itemDelegateForColumn(2), delegates.MultiSelectLayerDelegate)


def test_file_model_filename_data():
    """Tests the display data for the CustomFileModel `filename` field is as expected."""
    init_list = ratapi.ClassList(
        [
            ratapi.models.CustomFile(filename="myfile.m", path=Path(".").resolve()),
            ratapi.models.CustomFile(filename="", path="/"),
        ]
    )

    model = CustomFileModel(init_list, parent)

    filename_col = model.headers.index("filename") + model.col_offset

    assert model.data(model.index(0, filename_col)) == "myfile.m"
    assert model.data(model.index(1, filename_col)) == ""

    model.edit_mode = True

    assert Path(model.data(model.index(0, filename_col))) == (Path(".") / "myfile.m").resolve()
    assert model.data(model.index(1, filename_col)) == "Browse..."


@pytest.mark.parametrize(
    "filename, expected_lang, expected_filenames",
    (
        ["myfile.m", Languages.Matlab, None],
        ["myfile.py", Languages.Python, ["func1", "func2", "func3"]],
        ["myfile.dll", Languages.Cpp, None],
        ["myfile.so", Languages.Cpp, None],
        ["myfile.dylib", Languages.Cpp, None],
    ),
)
def test_file_model_set_filename(filename, expected_lang, expected_filenames):
    """Test the custom file row autocompletes when a filename is set."""
    init_list = ratapi.ClassList([ratapi.models.CustomFile(filename="", path=".")])
    python_file = "def func1(): pass \ndef func2(): pass \ndef func3(): pass"

    model = CustomFileModel(init_list, parent)

    filename_col = model.headers.index("filename") + model.col_offset
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "myfile.py").write_text(python_file)
        filepath = Path(tmp, filename)
        model.setData(model.index(0, filename_col), filepath)
        assert model.classlist[0].path == Path(tmp).resolve()
        assert model.classlist[0].filename == filename
        assert model.classlist[0].language == expected_lang

        if expected_lang == Languages.Python:
            assert model.func_names[filepath] == expected_filenames
            assert model.classlist[0].function_name == "func1"


@pytest.mark.parametrize("filename", ["file.m", "file.py", "file.dll", ""])
def test_file_widget_edit(filename):
    """Test that the correct index widget is created in edit mode."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "file.py").touch()
        init_list = ratapi.ClassList([ratapi.models.CustomFile(filename="")])

        widget = CustomFileWidget("files", parent)
        widget.update_model(init_list)

        edit_col = 1
        assert widget.table.isColumnHidden(edit_col)

        widget.edit()

        assert not widget.table.isColumnHidden(edit_col)

        if filename != "":
            widget.model.setData(
                widget.model.index(0, widget.model.headers.index("filename") + widget.model.col_offset),
                Path(tmp, filename),
            )

        button = widget.table.indexWidget(widget.model.index(0, edit_col))
        assert isinstance(button, QtWidgets.QPushButton)

        if filename in ["file.m", "file.py"]:
            assert button.isEnabled()
        else:
            assert not button.isEnabled()

        if filename == "file.m":
            assert button.menu() is not None
            assert len(button.menu().actions()) == 2
        else:
            assert button.menu() is None


@pytest.mark.parametrize(
    "background_type, disabled_vals",
    [
        ("constant", ["value_1", "value_2", "value_3", "value_4", "value_5"]),
        ("data", ["value_2", "value_3", "value_4", "value_5"]),
        ("function", []),
    ],
)
def test_background_disable_values(background_type, disabled_vals):
    """Test that unnecessary values are disabled in the Background model."""
    classlist = ratapi.ClassList(ratapi.models.Background(name="Background", type=background_type))

    model = BackgroundsModel(classlist, parent)

    for column in range(0, model.columnCount()):
        index = model.index(0, column)
        if model.index_header(index) in disabled_vals:
            assert not model.flags(index) & QtCore.Qt.ItemFlag.ItemIsEnabled
        else:
            assert model.flags(index) & QtCore.Qt.ItemFlag.ItemIsEnabled


@pytest.mark.parametrize(
    "resolution_type, disabled_vals",
    [
        ("constant", ["value_1", "value_2", "value_3", "value_4", "value_5"]),
        ("data", ["source", "value_1", "value_2", "value_3", "value_4", "value_5"]),
    ],
)
def test_resolution_disable_values(resolution_type, disabled_vals):
    """Test that unnecessary values are disabled in the Background model."""
    classlist = ratapi.ClassList(ratapi.models.Resolution(name="Resolution", type=resolution_type))

    model = ResolutionsModel(classlist, parent)

    for column in range(0, model.columnCount()):
        index = model.index(0, column)
        if model.index_header(index) in disabled_vals:
            assert not model.flags(index) & QtCore.Qt.ItemFlag.ItemIsEnabled
        else:
            assert model.flags(index) & QtCore.Qt.ItemFlag.ItemIsEnabled


@pytest.mark.parametrize("suffix,language", [(".py", Languages.Python), (".m", Languages.Matlab)])
def test_create_empty_custom_model(tmp_path, suffix, language):
    from unittest.mock import patch

    file = tmp_path / f"new_model{suffix}"
    widget = CustomFileWidget("files", parent)
    widget.update_model(ratapi.ClassList([ratapi.models.CustomFile(name="existing", filename="")]))
    with (
        patch("rascal2.widgets.project.tables.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(file), "")),
        patch("rascal2.widgets.project.tables.edit_file") as edit,
    ):
        widget.create_model_file()
    assert file.read_text() == ""
    assert len(widget.model.classlist) == 2
    item = widget.model.classlist[-1]
    assert item.filename == file.name
    assert item.path == file.parent
    assert item.language == language
    assert item.function_name == "new_model"
    edit.assert_called_once_with(file, language, widget)
    # Saving AI-generated code refreshes the function name and dropdown.
    if suffix == ".py":
        file.write_text("def generated_model(params, bulk_in, bulk_out, contrast):\n    return [], 0\n")
        widget.refresh_custom_file(file)
        assert item.function_name == "generated_model"
        assert widget.model.func_names[str(file)] == ["generated_model"]


def test_create_custom_model_never_overwrites_existing_file(tmp_path):
    from unittest.mock import patch

    file = tmp_path / "existing.py"
    file.write_text("original model")
    widget = CustomFileWidget("files", parent)
    widget.update_model(ratapi.ClassList([ratapi.models.CustomFile(name="existing", filename="")]))
    with (
        patch("rascal2.widgets.project.tables.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(file), "")),
        patch("rascal2.widgets.project.tables.QtWidgets.QMessageBox.warning") as warning,
        patch("rascal2.widgets.project.tables.edit_file") as edit,
    ):
        widget.create_model_file()
    assert file.read_text() == "original model"
    assert len(widget.model.classlist) == 1
    warning.assert_called_once()
    edit.assert_not_called()


def test_cancel_new_model_changes_nothing():
    from unittest.mock import patch

    widget = CustomFileWidget("files", parent)
    widget.update_model(ratapi.ClassList([ratapi.models.CustomFile(name="existing", filename="")]))
    with patch("rascal2.widgets.project.tables.QtWidgets.QFileDialog.getSaveFileName", return_value=("", "")):
        widget.create_model_file()
    assert len(widget.model.classlist) == 1


def test_new_model_editor_ai_apply_save_and_function_refresh(tmp_path):
    from unittest.mock import patch

    from rascal2.dialogs.custom_file_editor import CustomFileEditorDialog

    file = tmp_path / "new_model.py"
    widget = CustomFileWidget("files", parent)
    widget.update_model(ratapi.ClassList([ratapi.models.CustomFile(name="existing", filename="")]))
    with patch("rascal2.widgets.project.tables.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(file), "")):
        widget.create_model_file()
    dialog = CustomFileEditorDialog._instance
    try:
        assert dialog.file == file
        assert dialog.editor.text() == ""
        assert widget.model.func_names[str(file)] == []
        dialog.assistant.snapshot = ""
        dialog.assistant.response = (
            "```python\ndef generated_model(params, bulk_in, bulk_out, contrast):\n    return [], 0\n```"
        )
        dialog.assistant.complete()
        dialog.assistant.apply.click()
        assert dialog.is_modified
        assert file.read_text() == ""
        dialog.save_file()
        assert "def generated_model" in file.read_text()
        assert widget.model.classlist[-1].function_name == "generated_model"
        assert widget.model.func_names[str(file)] == ["generated_model"]
    finally:
        dialog.reject()
