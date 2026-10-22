"""Models and widgets for project fields."""

import contextlib
import re
from enum import Enum
from pathlib import Path

import pydantic
import ratapi
from PyQt6 import QtCore, QtGui, QtWidgets
from ratapi.utils.enums import Languages, Procedures, TypeOptions

import rascal2.widgets.delegates as delegates
from rascal2.config import EXAMPLES_PATH, path_for
from rascal2.dialogs.custom_file_editor import edit_file, edit_file_matlab


class ClassListTableModel(QtCore.QAbstractTableModel):
    """Table model for a project ClassList field.

    Parameters
    ----------
    classlist : ClassList
        The initial classlist to represent in this model.
    field : str
        The name of the field represented by this model.
    parent : QtWidgets.QWidget
        The parent widget for the model.

    """

    def __init__(self, classlist: ratapi.ClassList, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.parent = parent

        self.classlist: ratapi.ClassList
        self.item_type: type
        self.headers: list[str]

        self.setup_classlist(classlist)
        self.edit_mode = False
        self.col_offset = 1

    def setup_classlist(self, classlist: ratapi.ClassList):
        """Set up the ClassList, type and headers for the model."""
        self.classlist = classlist
        self.item_type = classlist._class_handle
        if not issubclass(self.item_type, pydantic.BaseModel):
            raise NotImplementedError("ClassListTableModel only works for classlists of Pydantic models!")
        self.headers = list(self.item_type.model_fields)

    def rowCount(self, parent=None) -> int:
        return len(self.classlist)

    def columnCount(self, parent=None) -> int:
        return len(self.headers) + self.col_offset

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        param = self.index_header(index)

        if param is None:
            return None

        data = getattr(self.classlist[index.row()], param)

        if role == QtCore.Qt.ItemDataRole.DisplayRole and self.index_header(index) != "fit":
            data = getattr(self.classlist[index.row()], param)
            # pyqt can't automatically coerce enums to strings...
            if isinstance(data, Enum):
                return str(data)
            if isinstance(data, list):
                return ", ".join(data)
            return data
        elif role == QtCore.Qt.ItemDataRole.CheckStateRole and self.index_header(index) == "fit":
            return QtCore.Qt.CheckState.Checked if data else QtCore.Qt.CheckState.Unchecked

    def setData(self, index, value, role=QtCore.Qt.ItemDataRole.EditRole) -> bool:
        """Set the data of a given index in the table model.

        Parameters
        ----------
        index: QtCore.QModelIndex
            The model index indicates which cells to change
        value: Any
            The new data value
        role: QtCore.Qt.ItemDataRole
            Indicates the role of the Data.
        """
        if role == QtCore.Qt.ItemDataRole.EditRole or role == QtCore.Qt.ItemDataRole.CheckStateRole:
            row = index.row()
            param = self.index_header(index)
            if param == "fit":
                value = QtCore.Qt.CheckState(value) == QtCore.Qt.CheckState.Checked
            if param is not None:
                current_value = getattr(self.classlist[index.row()], param)
                if current_value == value:
                    # No change
                    return False
                try:
                    with contextlib.suppress(UserWarning):
                        setattr(self.classlist[row], param, value)
                except pydantic.ValidationError:
                    return False
                if not self.edit_mode:
                    # recalculate plots if value was changed
                    recalculate = self.index_header(index) == "value"
                    self.parent.update_project(recalculate)
                self.dataChanged.emit(index, index)
                return True
        return False

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
            and section >= self.col_offset
        ):
            header = self.headers[section - self.col_offset]
            if "SLD" in header:
                header = header.replace("_", " ")
            else:
                header = header.replace("_", " ").title()
            return header
        return None

    def append_item(self):
        """Append an item to the ClassList."""
        self.classlist.append(self.item_type())
        self.endResetModel()

    def delete_item(self, row: int):
        """Delete an item in the ClassList.

        Parameters
        ----------
        row : int
            The row containing the item to delete.

        """
        self.classlist.pop(row)
        self.endResetModel()

    def index_header(self, index):
        """Get the header for an index.

        Parameters
        ----------
        index : QModelIndex
            The model index for the header.

        Returns
        -------
        str or None
            Either the name of the header, or None if none exists.

        """
        col = index.column()
        if col < self.col_offset:
            return None
        return self.headers[col - self.col_offset]


class ProjectFieldWidget(QtWidgets.QWidget):
    """Widget to show a project ClassList.

    Parameters
    ----------
    field : str
        The field of the project represented by this widget.
    parent : ProjectTabWidget
        The tab this field belongs to.

    """

    classlist_model = ClassListTableModel

    # the model can change and disconnect, so we re-connect it
    # to a signal here on each change
    edited = QtCore.pyqtSignal()

    def __init__(self, field: str, parent):
        super().__init__(parent)
        self.field = field
        header = field.replace("_", " ").title()
        self.parent = parent
        self.project_widget = parent.parent
        self.table = QtWidgets.QTableView(parent)

        self.table.horizontalHeader().setCascadingSectionResizes(True)
        self.table.setMinimumHeight(100)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        topbar = QtWidgets.QHBoxLayout()
        topbar.addWidget(QtWidgets.QLabel(header, objectName="ProjectFieldWidgetLabel"))
        self.add_button = QtWidgets.QPushButton(
            f"Add new {header[:-1] if header[-1] == 's' else header}", objectName="ProjectFieldWidgetButton"
        )
        self.add_button.setHidden(True)
        self.add_button.pressed.connect(self.append_item)
        topbar.addStretch(1)
        topbar.addWidget(self.add_button)

        layout.addLayout(topbar)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def resizeEvent(self, event):
        self.resize_columns()
        super().resizeEvent(event)

    def resize_columns(self):
        """Resize the columns of the tableview to avoid truncating content."""
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        main_col = "filename" if self.model.headers[1] == "filename" else "name"
        index = self.model.headers.index(main_col) + self.model.col_offset
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        if self.model.headers[0] == "fit" or self.model.headers[1] == "filename":
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.table.resizeColumnsToContents()

        total_content_width = 0
        visible_non_fixed_count = 0
        for i in range(0, self.model.columnCount()):
            total_content_width += self.table.columnWidth(i)
            if not header.isSectionHidden(i) and header.sectionResizeMode(i) != QtWidgets.QHeaderView.ResizeMode.Fixed:
                visible_non_fixed_count += 1

        # 20 is fudge value to account for content being smaller than table by few pixels
        width = self.table.width() - total_content_width - 20
        if width > 0:
            # if the table width is larger than the content, the extra space is shared
            # between the other visible, non-fixed columns then the final column is stretched.
            large_width = round(width * 0.4)
            remain_width = round((width - large_width) / (visible_non_fixed_count - 1))
            for i in range(0, self.model.columnCount() - 1):
                if header.isSectionHidden(i) or header.sectionResizeMode(i) == QtWidgets.QHeaderView.ResizeMode.Fixed:
                    continue
                width_offset = large_width if i == index else remain_width
                self.table.setColumnWidth(i, self.table.columnWidth(i) + width_offset)

        header.setStretchLastSection(True)

    def update_model(self, classlist: ratapi.classlist.ClassList):
        """Update the table model to synchronise with the project field."""
        self.model = self.classlist_model(classlist, self)

        self.table.setModel(self.model)
        self.model.dataChanged.connect(lambda: self.edited.emit())
        self.model.modelReset.connect(lambda: self.edited.emit())
        self.table.hideColumn(0)
        if self.model.headers[1] == "filename":
            self.table.hideColumn(1)

        self.set_item_delegates()
        self.resize_columns()

    def set_item_delegates(self):
        """Set item delegates and open persistent editors for the table."""
        for i, header in enumerate(self.model.headers):
            self.table.setItemDelegateForColumn(
                i + self.model.col_offset,
                delegates.ValidatedInputDelegate(self.model.item_type.model_fields[header], self.table),
            )

    def append_item(self):
        """Append an item to the model if the model exists."""
        self.model.rowCount()
        if self.model is not None:
            self.model.append_item()

        # call edit again to recreate delete buttons
        self.edit()
        self.table.scrollToBottom()

    def delete_item(self, index):
        """Delete an item at the index if the model exists.

        Parameters
        ----------
        index : int
            The row to be deleted.

        """
        if self.model is not None:
            self.model.delete_item(index)

        # call edit again to recreate delete buttons
        self.edit()

    def edit(self):
        """Change the widget to be in edit mode."""
        self.model.edit_mode = True
        self.add_button.setHidden(False)
        self.table.showColumn(0)
        self.set_item_delegates()
        for i in range(0, self.model.rowCount()):
            self.table.setIndexWidget(self.model.index(i, 0), self.make_delete_button(i))
        self.resize_columns()

    def make_delete_button(self, index):
        """Make a button that deletes index `index` from the list."""
        button = QtWidgets.QPushButton(icon=QtGui.QIcon(path_for("delete-dark.png")))
        button.resize(button.sizeHint().width(), button.sizeHint().width())
        button.pressed.connect(lambda: self.delete_item(index))

        return button

    def update_project(self, recalculate: bool):
        """Update the field in the parent Project.

        Parameters
        ----------
        recalculate : bool
            Whether to recalculate the plots when the project updates.
        """
        presenter = self.parent.parent.parent.presenter
        presenter.model.blockSignals(True)
        presenter.edit_project(
            {self.field: self.model.classlist}, preview=recalculate and presenter.view.settings.live_recalculate
        )
        presenter.model.blockSignals(False)
        if presenter.view.settings.live_recalculate:
            presenter.view.plot_widget.update_plots()


class ParametersModel(ClassListTableModel):
    """Classlist model for Parameters."""

    def __init__(self, classlist: ratapi.ClassList, parent: QtWidgets.QWidget):
        super().__init__(classlist, parent)
        self.headers.insert(0, self.headers.pop(self.headers.index("fit")))
        self.headers.pop(self.headers.index("show_priors"))

        self.protected_indices = []
        if self.item_type is ratapi.models.Parameter:
            for i, item in enumerate(classlist):
                if isinstance(item, ratapi.models.ProtectedParameter):
                    self.protected_indices.append(i)

    def flags(self, index):
        flags = super().flags(index)
        header = self.index_header(index)
        # disable editing on the delete widget column
        # and disable mu, sigma if prior type is not Gaussian
        if (index.column() == 0) or (
            self.classlist[index.row()].prior_type != "gaussian" and header in ["mu", "sigma"]
        ):
            return QtCore.Qt.ItemFlag.NoItemFlags
        # never allow name editing for protected parameters, allow everything else to be edited by default
        if header == "fit":
            flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable
        elif header != "name" or (self.edit_mode and index.row() not in self.protected_indices):
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable

        return flags

    def setData(self, index, value, role=QtCore.Qt.ItemDataRole.EditRole) -> bool:
        param = self.index_header(index)
        if param == "min":
            min_value = value
            value_model_index = index.siblingAtColumn(index.column() + 1)
            max_model_index = index.siblingAtColumn(index.column() + 2)

            if min_value > max_model_index.data(QtCore.Qt.ItemDataRole.DisplayRole):
                super().setData(max_model_index, min_value, role)
            if min_value > value_model_index.data(QtCore.Qt.ItemDataRole.DisplayRole):
                super().setData(value_model_index, min_value, role)

        elif param == "value":
            min_model_index = index.siblingAtColumn(index.column() - 1)
            actual_value = value
            max_model_index = index.siblingAtColumn(index.column() + 1)
            if actual_value < min_model_index.data(QtCore.Qt.ItemDataRole.DisplayRole):
                super().setData(min_model_index, actual_value, role)
            if actual_value > max_model_index.data(QtCore.Qt.ItemDataRole.DisplayRole):
                super().setData(max_model_index, actual_value, role)

        elif param == "max":
            min_model_index = index.siblingAtColumn(index.column() - 2)
            value_model_index = index.siblingAtColumn(index.column() - 1)
            max_value = value
            if max_value < min_model_index.data(QtCore.Qt.ItemDataRole.DisplayRole):
                super().setData(min_model_index, max_value, role)
            if max_value < value_model_index.data(QtCore.Qt.ItemDataRole.DisplayRole):
                super().setData(value_model_index, max_value, role)

        return super().setData(index, value, role)


class ParameterFieldWidget(ProjectFieldWidget):
    """Subclass of field widgets for parameters."""

    classlist_model = ParametersModel

    def set_item_delegates(self):
        for i, header in enumerate(self.model.headers):
            if header in ["min", "value", "max"]:
                delegate = delegates.ValueSpinBoxDelegate(header, self.table)
                self.table.setItemDelegateForColumn(i + 1, delegate)
            else:
                self.table.setItemDelegateForColumn(
                    i + 1, delegates.ValidatedInputDelegate(self.model.item_type.model_fields[header], self.table)
                )

    def update_model(self, classlist: ratapi.classlist.ClassList):
        super().update_model(classlist)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            self.model.headers.index("fit") + 1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )

    def handle_bayesian_columns(self, procedure: Procedures):
        """Hide or show Bayes-related columns based on procedure.

        Parameters
        ----------
        procedure : Procedure
            The procedure in Controls.
        """
        is_bayesian = procedure in ["ns", "dream"]
        bayesian_columns = ["prior_type", "mu", "sigma"]
        for item in bayesian_columns:
            index = self.model.headers.index(item)
            if is_bayesian:
                self.table.showColumn(index + 1)
            else:
                self.table.hideColumn(index + 1)
        self.resize_columns()

    def edit(self):
        super().edit()
        for i in range(0, self.model.rowCount()):
            if i in self.model.protected_indices:
                self.table.setIndexWidget(self.model.index(i, 0), None)


class LayersModel(ClassListTableModel):
    """Classlist model for Layers."""

    def __init__(self, classlist: ratapi.ClassList, parent: QtWidgets.QWidget):
        super().__init__(classlist, parent)
        self.absorption = classlist._class_handle == ratapi.models.AbsorptionLayer
        self.SLD_imags = {}

    def flags(self, index):
        flags = super().flags(index)
        if self.edit_mode:
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
        return flags

    def append_item(self):
        kwargs = {"thickness": "", "SLD": "", "roughness": ""}
        if self.absorption:
            kwargs["SLD_imaginary"] = ""
        self.classlist.append(self.item_type(**kwargs))
        self.endResetModel()

    def set_absorption(self, absorption: bool):
        """Set whether the project is using absorption or not.

        Parameters
        ----------
        absorption : bool
            Whether the project is using absorption.

        """
        if self.absorption != absorption:
            self.beginResetModel()
            self.absorption = absorption
            if absorption:
                classlist = ratapi.ClassList(
                    [
                        ratapi.models.AbsorptionLayer(
                            **dict(layer),
                            SLD_imaginary=self.SLD_imags.get(layer.name, ""),
                        )
                        for layer in self.classlist
                    ]
                )
                # set handle manually for if classlist is empty
                classlist._class_handle = ratapi.models.AbsorptionLayer
            else:
                # we save the SLD_imaginary values so that they aren't lost if the
                # user accidentally toggles absorption off and on!
                self.SLD_imags = {layer.name: layer.SLD_imaginary for layer in self.classlist}
                classlist = ratapi.ClassList(
                    [
                        ratapi.models.Layer(
                            name=layer.name,
                            thickness=layer.thickness,
                            SLD=layer.SLD_real,
                            roughness=layer.roughness,
                            hydration=layer.hydration,
                            hydrate_with=layer.hydrate_with,
                        )
                        for layer in self.classlist
                    ]
                )
                classlist._class_handle = ratapi.models.Layer
            self.setup_classlist(classlist)
            self.parent.parent.parent.update_draft_project({"layers": classlist})
            self.endResetModel()


class LayerFieldWidget(ProjectFieldWidget):
    """Project field widget for Layer objects."""

    classlist_model = LayersModel

    def set_item_delegates(self):
        for i in range(1, self.model.columnCount()):
            if i in [1, self.model.columnCount() - 1]:
                header = self.model.headers[i - 1]
                self.table.setItemDelegateForColumn(
                    i, delegates.ValidatedInputDelegate(self.model.item_type.model_fields[header], self.table)
                )
            else:
                blank_option = self.model.headers[i - 1] == "hydration"
                self.table.setItemDelegateForColumn(
                    i, delegates.ProjectFieldDelegate(self.project_widget, "parameters", self.table, blank_option)
                )

    def set_absorption(self, absorption: bool):
        """Set whether the classlist uses AbsorptionLayers.

        Parameters
        ----------
        absorption : bool
            Whether the classlist should use AbsorptionLayers.

        """
        self.model.set_absorption(absorption)
        if self.model.edit_mode:
            self.edit()


class DomainsModel(ClassListTableModel):
    """Classlist model for domain contrasts."""

    def flags(self, index):
        flags = super().flags(index)
        if self.edit_mode:
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
        return flags


class DomainContrastWidget(ProjectFieldWidget):
    """Subclass of field widgets for domain contrasts."""

    classlist_model = DomainsModel

    def __init__(self, field, parent):
        super().__init__(field, parent)
        self.project_widget = parent.parent

    def update_model(self, classlist):
        super().update_model(classlist)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)

    def set_item_delegates(self):
        self.table.setItemDelegateForColumn(
            1, delegates.ValidatedInputDelegate(self.model.item_type.model_fields["name"], self.table)
        )
        self.table.setItemDelegateForColumn(2, delegates.MultiSelectLayerDelegate(self.project_widget, self.table))


class CustomFileModel(ClassListTableModel):
    """Classlist model for custom files."""

    def __init__(self, classlist: ratapi.ClassList, parent: QtWidgets.QWidget):
        super().__init__(classlist, parent)
        self.func_names = {}
        self.headers.remove("path")
        self.col_offset = 2

    def flags(self, index):
        flags = super().flags(index)
        if index.column() in [1, self.columnCount()]:
            return QtCore.Qt.ItemFlag.NoItemFlags
        if self.edit_mode:
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
        return flags

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        data = super().data(index, role)
        if role == QtCore.Qt.ItemDataRole.DisplayRole and self.index_header(index) == "filename" and self.edit_mode:
            if data == "" or data == "Browse...":
                return "Browse..."
            return str(self.classlist[index.row()].path / data)

        return data

    def setData(self, index, value, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if self.index_header(index) == "filename" and value != "Browse...":
            file_path = Path(value)
            row = index.row()
            self.classlist[row].path = file_path.parent
            self.classlist[row].filename = str(file_path.name)

            # auto-set language from file extension if possible
            # & get file names for dropdown on Python
            extension = file_path.suffix
            match extension:
                case ".py":
                    language = Languages.Python
                    # the regex:
                    # (?:^|\n) means 'match start of the string (i.e. the file) or a newline'
                    # (\S+) means 'capture one or more non-whitespace characters'
                    # so the regex captures a word between 'def ' and '(', i.e. a function name
                    func_names = re.findall(r"(?:^|\n)def (\S+)\(", file_path.read_text())
                case ".m":
                    language = Languages.Matlab
                    func_names = None
                case ".dll" | ".so" | ".dylib":
                    language = Languages.Cpp
                    func_names = None
                case _:
                    language = None
                    func_names = None
            self.func_names[value] = func_names
            if func_names:
                self.classlist[row].function_name = func_names[0]
            if language is not None:
                self.classlist[row].language = language

            self.dataChanged.emit(index, index)
            return True

        return super().setData(index, value, role)

    def append_item(self):
        """Append an item to the ClassList."""
        self.classlist.append(self.item_type(filename="", path="/"))
        self.endResetModel()


class CustomFileWidget(ProjectFieldWidget):
    """Subclass of field widgets for custom file."""

    classlist_model = CustomFileModel

    def __init__(self, field, parent):
        super().__init__(field, parent)
        self.new_file_button = QtWidgets.QPushButton("New model file…", self)
        self.new_file_button.setHidden(True)
        self.new_file_button.clicked.connect(self.create_model_file)
        self.layout().itemAt(0).layout().addWidget(self.new_file_button)

    def create_model_file(self):
        """Create a new empty source file, register it and open the built-in editor."""
        filename, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "New custom model file", "", "Python model (*.py);;MATLAB model (*.m)"
        )
        if not filename:
            return
        file = Path(filename)
        if not file.suffix:
            file = file.with_suffix(".m" if "MATLAB" in selected_filter else ".py")
        if file.suffix not in (".py", ".m") or not file.stem.isidentifier():
            QtWidgets.QMessageBox.warning(self, "New model file", "Choose a .py or .m file with a valid function name.")
            return
        if file.resolve().is_relative_to(EXAMPLES_PATH.resolve()):
            QtWidgets.QMessageBox.warning(self, "New model file", "Choose a folder outside the bundled examples.")
            return
        language = Languages.Python if file.suffix == ".py" else Languages.Matlab
        name = file.stem
        names = {item.name for item in self.model.classlist}
        count = 2
        while name in names:
            name = f"{file.stem} {count}"
            count += 1
        item = self.model.item_type(
            name=name, filename=file.name, path=file.parent, language=language, function_name=file.stem
        )
        try:
            # Exclusive creation protects existing files, even if the save dialog confirmed overwrite.
            with file.open("x", encoding="utf-8"):
                pass
        except OSError as error:
            QtWidgets.QMessageBox.warning(self, "New model file", f"Could not create a new file:\n{error}")
            return
        self.model.beginResetModel()
        try:
            self.model.classlist.append(item)
        except (ValueError, TypeError) as error:
            QtWidgets.QMessageBox.warning(
                self, "New model file", f"The empty file was created, but could not be added to the project:\n{error}"
            )
            return
        finally:
            self.model.endResetModel()
        self.model.func_names[str(file)] = [] if language == Languages.Python else None
        self.edit()
        dialog = edit_file(file, language, self)
        if dialog is not None:
            with contextlib.suppress(TypeError):
                dialog.file_saved.disconnect(self.refresh_custom_file)
            dialog.file_saved.connect(self.refresh_custom_file)

    def refresh_custom_file(self, file):
        """Refresh function choices after a newly created model is saved."""
        for row, item in enumerate(self.model.classlist):
            if item.path / item.filename == file:
                column = self.model.headers.index("filename") + self.model.col_offset
                self.model.setData(self.model.index(row, column), str(file))
                break

    def edit(self):
        super().edit()
        self.new_file_button.setVisible(True)
        edit_file_column = 1
        self.table.showColumn(edit_file_column)
        # disconnect from old table's buttons so they don't create dangling references
        # if no connections currently exist (i.e. table empty), disconnect() raises a TypeError
        with contextlib.suppress(TypeError):
            self.model.dataChanged.disconnect()
        for i in range(0, self.model.rowCount()):
            self.table.setIndexWidget(self.model.index(i, edit_file_column), self.make_edit_button(i))
        self.resize_columns()

    def make_edit_button(self, index):
        button = QtWidgets.QPushButton("Edit File", self.table)
        q_scintilla_action = QtGui.QAction("Edit in RasCAL-2...", self.table)
        q_scintilla_action.triggered.connect(
            lambda: edit_file(
                self.model.classlist[index].path / self.model.classlist[index].filename,
                self.model.classlist[index].language,
                self,
            )
        )
        matlab_action = QtGui.QAction("Edit in MATLAB...", self.table)
        matlab_action.triggered.connect(
            lambda: edit_file_matlab(self.model.classlist[index].path / self.model.classlist[index].filename)
        )
        menu = QtWidgets.QMenu(self.table)
        menu.addActions([q_scintilla_action, matlab_action])

        def setup_button():
            """Check whether the button should be editable and set it up for the right language."""
            language = self.model.data(
                self.model.index(index, self.model.headers.index("language") + self.model.col_offset)
            )
            with contextlib.suppress(TypeError):
                button.pressed.disconnect()
            if language == Languages.Matlab:
                button.setMenu(menu)
                button.pressed.connect(button.showMenu)
            else:
                button.setMenu(None)
                button.pressed.connect(
                    lambda: edit_file(
                        self.model.classlist[index].path / self.model.classlist[index].filename,
                        self.model.classlist[index].language,
                        self,
                    )
                )

            editable = (language in [Languages.Matlab, Languages.Python]) and (
                self.model.data(self.model.index(index, self.model.headers.index("filename") + self.model.col_offset))
                != "Browse..."
            )
            button.setEnabled(editable)

        setup_button()
        self.model.dataChanged.connect(lambda: setup_button())

        return button

    def set_item_delegates(self):
        super().set_item_delegates()
        """Set item delegates and open persistent editors for the table."""
        for i, header in enumerate(self.model.headers):
            self.table.setItemDelegateForColumn(
                i + self.model.col_offset,
                delegates.ValidatedInputDelegate(self.model.item_type.model_fields[header], self.table),
            )

        filename_index = self.model.headers.index("filename") + self.model.col_offset
        function_index = self.model.headers.index("function_name") + self.model.col_offset
        self.table.setItemDelegateForColumn(
            filename_index,
            delegates.ValidatedInputDelegate(self.model.item_type.model_fields["path"], self.table, open_on_show=True),
        )
        self.table.setItemDelegateForColumn(function_index, delegates.CustomFileFunctionDelegate(self))


class AbstractSignalModel(ClassListTableModel):
    """Model for Signal objects (backgrounds and resolutions)."""

    def flags(self, index):
        flags = super().flags(index)
        if self.edit_mode:
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
        match self.classlist[index.row()].type:  # disable unused value fields
            case TypeOptions.Constant:
                disable_from_col = self.num_valid_values[0]
            case TypeOptions.Data:
                disable_from_col = self.num_valid_values[1]
            case TypeOptions.Function:
                disable_from_col = self.num_valid_values[2]
        if index.column() > disable_from_col + 3:  # +3 offset for name, type, source
            flags = QtCore.Qt.ItemFlag.NoItemFlags
        return flags

    @property
    def num_valid_values(self) -> tuple[int]:
        """The number of valid value fields for each type.

        Returns
        -------
        Tuple[int]
            The number of valid values for constant, data, and function signals respectively.

        """
        raise NotImplementedError


class BackgroundsModel(AbstractSignalModel):
    """Model for classlists of Backgrounds."""

    @property
    def num_valid_values(self) -> tuple[int]:
        return (0, 1, 5)


class ResolutionsModel(AbstractSignalModel):
    """Model for classlists of Resolutions."""

    @property
    def num_valid_values(self) -> tuple[int]:
        return (0, -1, 5)  # -1 to remove 'source' field for data resolutions


class AbstractSignalFieldWidget(ProjectFieldWidget):
    """Project field widget for 'signal' objects (backgrounds and resolutions)."""

    def set_item_delegates(self):
        super().set_item_delegates()
        source_index = self.model.headers.index("source") + 1
        self.table.setItemDelegateForColumn(
            source_index, delegates.SignalSourceDelegate(self.project_widget, self.parameter_field, self.table)
        )
        for column in range(source_index + 1, self.model.columnCount()):
            self.table.setItemDelegateForColumn(
                column, delegates.ProjectFieldDelegate(self.project_widget, self.parameter_field, self.table)
            )

    @property
    def parameter_field(self) -> str:
        """The relevant parameter field for the object.

        Returns
        -------
        str
            The name of the relevant parameter field for the object.

        """
        raise NotImplementedError


class BackgroundsFieldWidget(AbstractSignalFieldWidget):
    """Project field widget for backgrounds."""

    classlist_model = BackgroundsModel

    @property
    def parameter_field(self) -> str:
        return "background_parameters"


class ResolutionsFieldWidget(AbstractSignalFieldWidget):
    """Project field widget for resolutions."""

    classlist_model = ResolutionsModel

    def set_item_delegates(self):
        super().set_item_delegates()
        # workaround to remove function resolution option
        type_index = self.model.headers.index("type") + 1
        self.table.setItemDelegateForColumn(
            type_index,
            delegates.ValidatedInputDelegate(self.model.item_type.model_fields["type"], self.table, remove_items=[2]),
        )
        # hide unused value_2 through value_5
        for column in range(4, 9):
            self.table.setColumnHidden(column, True)

    @property
    def parameter_field(self) -> str:
        return "resolution_parameters"
