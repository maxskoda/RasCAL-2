import os
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from rascal2.config import EXAMPLES_PATH, LOGGER
from rascal2.core.worker import Worker
from rascal2.settings import update_recent_projects

# global variable for required project files
PROJECT_FILES = ["controls.json", "project.json"]
EXAMPLES = {
    "absorption": "Shows absorption (imaginary SLD) effect usually seen below the critical edge",
    "domains_custom_layers": "Incoherent summing ('domains') from custom layer model",
    "domains_custom_XY": "Incoherent summing ('domains') from custom XY model",
    "domains_standard_layers": "Incoherent summing ('domains') from standard layer model",
    "DSPC_custom_layers": "Reflectivity analysis of a floating bilayer of DSPC using custom layer model",
    "DSPC_custom_XY": "Reflectivity analysis of a floating bilayer of DSPC using custom XY model",
    "DSPC_standard_layers": "Reflectivity analysis of a floating bilayer of DSPC using standard layer model",
}


class StartupDialog(QtWidgets.QDialog):
    """Base class for startup dialogs."""

    folder_selector = QtWidgets.QFileDialog.getExistingDirectory

    def __init__(self, parent):
        """Initialize dialog.

        Parameters
        ----------
        parent: MainWindowView
            An instance of the MainWindowView
        """
        super().__init__(parent)

        self.setModal(True)
        self.setMinimumWidth(700)

        self.folder_path = ""

        self.compose_layout()

    def compose_layout(self):
        """Add widgets and layouts to the dialog's main layout."""
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setSpacing(20)

        form_layout = QtWidgets.QGridLayout()
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(0)
        main_layout.addLayout(form_layout)
        self.create_form(form_layout)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        buttons = self.create_buttons()
        for button in buttons:
            button_layout.addWidget(button)
        main_layout.addStretch(1)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.create_loading_bar())

        self.setLayout(main_layout)

    def create_loading_bar(self):
        """Create a non-deterministic progress bar."""
        self.loading_bar = QtWidgets.QProgressBar()
        self.loading_bar.setMinimum(0)
        self.loading_bar.setMaximum(0)
        self.loading_bar.setVisible(False)
        return self.loading_bar

    def create_buttons(self) -> list[QtWidgets.QWidget]:
        """Create buttons for the bottom of the dialog.

        This is kept as a separate method so that it can be reimplemented by subclasses.

        Returns
        -------
        list[QtWidgets.QWidget]
            A list of the widgets to be added to the bottom of the dialog, from left to right.
        """
        self.cancel_button = QtWidgets.QPushButton("Cancel", objectName="CancelButton")
        self.cancel_button.clicked.connect(self.reject)

        return [self.cancel_button]

    def create_form(self, form_layout):
        """Create the widgets and layout for the dialog form.

        This is kept as a separate method so that it can be reimplemented by subclasses.

        Parameters
        ----------
        form_layout : QtWidgets.QGridLayout
            A layout to add the form to.
        """
        self.project_folder_label = QtWidgets.QLabel("Project Folder:")
        self.project_folder_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        self.project_folder = QtWidgets.QLineEdit(self)
        self.project_folder.setReadOnly(True)
        self.project_folder.setPlaceholderText("Select project folder")
        self.project_folder.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        browse_button = QtWidgets.QPushButton("Browse", objectName="BrowseButton")
        browse_button.clicked.connect(self.open_folder_selector)

        self.project_folder_error = QtWidgets.QLabel("", objectName="ErrorLabel")
        self.project_folder_error.hide()

        num_rows = form_layout.rowCount()
        form_layout.addWidget(self.project_folder_label, num_rows, 0, 1, 1, QtCore.Qt.AlignmentFlag.AlignVCenter)
        form_layout.addWidget(self.project_folder, num_rows, 1, 1, 4)
        form_layout.addWidget(browse_button, num_rows, 5, 1, 1)
        form_layout.addWidget(self.project_folder_error, num_rows + 1, 1, 1, 4)

    def open_folder_selector(self) -> None:
        """Open folder selector."""
        folder_path = self.folder_selector(self, "Select Folder")
        if folder_path:
            try:
                self.verify_folder(folder_path)
            except ValueError as err:
                self.set_folder_error(str(err))
                self.project_folder.setText("")
            else:
                self.set_folder_error("")
                self.project_folder.setText(folder_path)

    def set_folder_error(self, msg: str):
        """Show or remove an error on the project folder dialog.

        Parameters
        ----------
        msg : str
            The message to show as the error. If blank, will remove the error.

        """
        if msg:
            self.project_folder_error.show()
            self.project_folder_error.setText(msg)
            self.project_folder.setProperty("error", True)
        else:
            self.project_folder_error.hide()
            self.project_folder.setProperty("error", False)
        self.project_folder.style().unpolish(self.project_folder)
        self.project_folder.style().polish(self.project_folder)

    @staticmethod
    def verify_folder(folder_path: str):
        """Verify that the path is valid for the current dialog, and raise an error otherwise.

        This is an empty method to be reimplemented by subclasses.

        Raises
        ------
        ValueError
            If the folder path is not valid for the current operation.

        """
        pass

    def showEvent(self, event):
        super().showEvent(event)
        self.cancel_button.setFocus()

    def reject(self):
        super().reject()
        if self.parent().centralWidget() is self.parent().startup_dlg:
            self.parent().startup_dlg.setVisible(True)

    def project_start_success(self):
        self.parent().presenter.initialise_ui()
        if not self.parent().toolbar.isEnabled():
            self.parent().toolbar.setEnabled(True)
        self.accept()

    def project_start_failed(self, exception, args):
        folder_name = args[0]
        error = str(exception).strip().replace("\n", "")
        message = f"The Project ({folder_name}) could not be opened because:\n\n{error}"
        LOGGER.error(message, exc_info=exception)
        QtWidgets.QMessageBox.critical(self, self.windowTitle(), message)


class NewProjectDialog(StartupDialog):
    """The dialog to create a new project."""

    def create_form(self, form_layout):
        self.setWindowTitle("New Project")

        # Project name widgets
        self.project_name_label = QtWidgets.QLabel("Project Name:")
        self.project_name_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        self.project_name = QtWidgets.QLineEdit(self)
        self.project_name.setPlaceholderText("Enter project name")
        self.project_name.textChanged.connect(self.verify_name)

        self.project_name_error = QtWidgets.QLabel("Project name needs to be specified.", objectName="ErrorLabel")
        self.project_name_error.hide()

        num_rows = form_layout.rowCount()
        form_layout.addWidget(self.project_name_label, num_rows, 0, 1, 1)
        form_layout.addWidget(self.project_name, num_rows, 1, 1, 5)
        form_layout.addWidget(self.project_name_error, num_rows + 1, 1, 1, 5)
        super().create_form(form_layout)

    def create_buttons(self) -> list[QtWidgets.QWidget]:
        create_button = QtWidgets.QPushButton("Create", objectName="CreateButton")
        create_button.clicked.connect(self.create_project)

        return [create_button] + super().create_buttons()

    @staticmethod
    def verify_folder(folder_path: str) -> None:
        if not os.access(folder_path, os.W_OK) and os.access(folder_path, os.R_OK):
            raise ValueError("You do not have permission to access this folder.")
        if any(Path(folder_path, file).exists() for file in PROJECT_FILES):
            raise ValueError("Folder already contains a project.")

    def verify_name(self) -> None:
        if self.project_name.text() == "":
            self.project_name_error.show()
            self.project_name.setProperty("error", True)
        else:
            self.project_name_error.hide()
            self.project_name.setProperty("error", False)
        self.project_name.style().unpolish(self.project_name)
        self.project_name.style().polish(self.project_name)

    def create_project(self) -> None:
        """Create project if inputs are valid."""
        self.verify_name()
        if self.project_folder.text() == "":
            self.set_folder_error("Please specify a project folder.")
        if self.project_name_error.isHidden() and self.project_folder_error.isHidden():
            self.parent().presenter.create_project(self.project_name.text(), self.project_folder.text())
            self.accept()



class DisplayWidget(QtWidgets.QWidget):
    """Fancy display widget for title and description items in a list."""

    def __init__(self, title, desc):
        super().__init__()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        title_widget = QtWidgets.QLabel(title)
        title_widget.setObjectName("title")
        desc_widget = QtWidgets.QLabel(desc)
        desc_widget.setObjectName("desc")
        layout.addWidget(title_widget)
        layout.addWidget(desc_widget)
        self.setLayout(layout)


class LoadDialog(StartupDialog):
    """Dialog to load an existing project."""

    def compose_layout(self):
        """Add widgets and layouts to the dialog's main layout."""
        self.setWindowTitle("Load Project")
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setSpacing(0)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setContentsMargins(0, 0, 0, 0)
        self.create_load_tab()
        self.create_recent_tab()
        self.create_example_tab()
        main_layout.addWidget(self.tabs)
        main_layout.addWidget(self.create_loading_bar())

        self.setLayout(main_layout)

    def create_load_tab(self):
        """Create the load project widget."""
        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(20)

        load_tab = QtWidgets.QWidget()
        load_tab.setLayout(layout)

        form_layout = QtWidgets.QGridLayout()
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(0)
        layout.addLayout(form_layout)
        super().create_form(form_layout)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        buttons = self.create_buttons()
        for button in buttons:
            button_layout.addWidget(button)
        layout.addStretch(1)
        layout.addLayout(button_layout)

        self.tabs.addTab(load_tab, "Load Project")

    def create_list_widget_tab(self, tab_name: str):
        """Create the list widget and add it to tab with given name.

        Parameters
        ----------
        tab_name : str
            The name of tab to add list to.
        """
        layout = QtWidgets.QVBoxLayout()

        new_tab = QtWidgets.QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        new_tab.setLayout(layout)

        list_widget = QtWidgets.QListWidget()
        list_widget.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        list_widget.setSpacing(0)

        list_widget.itemClicked.connect(self.load_project)
        layout.addWidget(list_widget)
        self.tabs.addTab(new_tab, tab_name)

        return list_widget

    def create_example_tab(self):
        """Create the example widget."""
        self.example_list_widget = self.create_list_widget_tab("Examples")

        for name, desc in EXAMPLES.items():
            item = QtWidgets.QListWidgetItem()
            self.example_list_widget.addItem(item)
            item_widget = DisplayWidget(name.replace("_", " "), desc)
            self.example_list_widget.setItemWidget(item, item_widget)

            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(EXAMPLES_PATH / name))
            item.setSizeHint(item_widget.sizeHint())

    def create_recent_tab(self):
        """Create the recent project widget."""
        recent_projects = update_recent_projects()
        recent_projects = recent_projects[:6]
        self.recent_list_widget = self.create_list_widget_tab("Recent Projects")

        for i in range(len(recent_projects)):
            path_name = Path(recent_projects[i]).name

            item = QtWidgets.QListWidgetItem()
            self.recent_list_widget.addItem(item)
            item_widget = DisplayWidget(path_name, recent_projects[i])
            self.recent_list_widget.setItemWidget(item, item_widget)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, recent_projects[i])
            item.setSizeHint(item_widget.sizeHint())

    def create_buttons(self) -> list[QtWidgets.QWidget]:
        load_button = QtWidgets.QPushButton("Load", objectName="LoadButton")
        load_button.clicked.connect(self.load_project)

        return [load_button] + super().create_buttons()

    @staticmethod
    def verify_folder(folder_path: str):
        if not os.access(folder_path, os.W_OK) and os.access(folder_path, os.R_OK):
            raise ValueError("You do not have permission to access this folder.")
        if not all(Path(folder_path, file).exists() for file in PROJECT_FILES):
            raise ValueError("No project found in this folder.")

    def load_project(self, item=None):
        """Load the project if inputs are valid.

        Parameters
        ----------
        item : Optional[QtWidgets.QListWidgetItem]
            item if load project was called from list widget.
        """
        if isinstance(item, QtWidgets.QListWidgetItem):
            path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        else:
            if self.project_folder.text() == "":
                self.set_folder_error("Please specify a project folder.")
            if not self.project_folder_error.isHidden():
                return
            path = self.project_folder.text()

        self.worker = Worker.call(
            self.parent().presenter.load_project,
            [path],
            self.project_start_success,
            self.project_start_failed,
            lambda: self.block_for_worker(False),
        )
        self.block_for_worker(True)

    def block_for_worker(self, disabled: bool):
        """Disable UI while worker is completing.

        Parameters
        ----------
        disabled : bool
            indicates if ui should be disabled.
        """
        self.recent_list_widget.setDisabled(disabled)
        self.example_list_widget.setDisabled(disabled)
        self.loading_bar.setVisible(disabled)


class LoadR1Dialog(StartupDialog):
    """Dialog to load a RasCAL-1 project."""

    def __init__(self, parent):
        # our 'folder selector' is actually a .mat file selector in this case
        self.folder_selector = lambda p, _: QtWidgets.QFileDialog.getOpenFileName(
            p, "Select RasCAL-1 File", filter="*.mat"
        )[0]
        super().__init__(parent)

    def create_form(self, form_layout):
        self.setWindowTitle("Load RasCAL-1 Project")

        super().create_form(form_layout)
        self.project_folder_label.setText("RasCAL-1 file:")
        self.project_folder.setPlaceholderText("Select RasCAL-1 file")

    def create_buttons(self):
        load_button = QtWidgets.QPushButton("Load", objectName="LoadButton")
        load_button.clicked.connect(self.load_project)

        return [load_button] + super().create_buttons()

    @staticmethod
    def verify_folder(file_path: str):
        if not os.access(file_path, os.R_OK):
            raise ValueError("You do not have permission to read this RasCAL-1 project.")
        if not os.access(Path(file_path).parent, os.W_OK):
            raise ValueError("You do not have permission to create a project in this folder.")

    def load_project(self):
        """Load the project if inputs are valid."""
        if self.project_folder.text() == "":
            self.set_folder_error("Please specify a project file.")
        if self.project_folder_error.isHidden():
            self.worker = Worker.call(
                self.parent().presenter.load_r1_project,
                [self.project_folder.text()],
                self.project_start_success,
                self.project_start_failed,
                self.loading_bar.hide,
            )
            self.loading_bar.setVisible(True)


class ImportORTDialog(StartupDialog):
    """Dialog to import an ORSO .ort file into a new RasCAL-2 project."""

    def __init__(self, parent):
        # file selector instead of folder selector
        self.folder_selector = lambda p, _: QtWidgets.QFileDialog.getOpenFileName(
            p,
            "Select ORSO File",
            filter="ORSO (*.ort);;All files (*)",
        )[0]
        super().__init__(parent)

    def create_form(self, form_layout):
        self.setWindowTitle("Import ORSO (.ort)")
        super().create_form(form_layout)

        self.project_folder_label.setText("ORSO file:")
        self.project_folder.setPlaceholderText("Select ORSO .ort file")

    def create_buttons(self):
        import_button = QtWidgets.QPushButton("Import", objectName="ImportButton")
        import_button.clicked.connect(self.import_ort)
        return [import_button] + super().create_buttons()

    @staticmethod
    def verify_folder(file_path: str):
        # NOTE: 'verify_folder' naming is inherited; it's really "verify selection"
        if not file_path.lower().endswith(".ort"):
            raise ValueError("Please select a .ort file.")
        if not os.access(file_path, os.R_OK):
            raise ValueError("You do not have permission to read this .ort file.")
        if not os.access(Path(file_path).parent, os.W_OK):
            # optional: if importer will write a project folder beside it
            # if you import "in memory" only, you can drop this check
            raise ValueError("You do not have permission to write to this folder.")

    def import_ort(self):
        """Run ORT import via Worker (non-blocking)."""
        if self.project_folder.text() == "":
            self.set_folder_error("Please specify an ORSO .ort file.")
            return
        if not self.project_folder_error.isHidden():
            return

        ort_path = self.project_folder.text()

        self.worker = Worker.call(
            self.parent().presenter.import_ort_project,   # you implement this
            [ort_path],
            self.project_start_success,
            self.project_start_failed,
            lambda: self.block_for_worker(False),
        )
        self.block_for_worker(True)

    def block_for_worker(self, disabled: bool):
        self.loading_bar.setVisible(disabled)
        self.project_folder.setDisabled(disabled)
        self.cancel_button.setDisabled(disabled)
