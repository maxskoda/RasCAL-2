from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from rascal2.config import EXAMPLES_PATH, EXAMPLES_TEMP_PATH, path_for
from rascal2.core.enums import UnsavedReply
from rascal2.dialogs.about_dialog import AboutDialog
from rascal2.dialogs.settings_dialog import SettingsDialog
from rascal2.dialogs.startup_dialog import PROJECT_FILES, LoadDialog, LoadR1Dialog, NewProjectDialog, StartupDialog, ImportORTDialog
from rascal2.settings import MDIGeometries, Settings, get_global_settings
from rascal2.widgets import ControlsWidget, PlotWidget, TerminalWidget
from rascal2.widgets.project import ProjectWidget
from rascal2.widgets.startup import StartUpWidget

from .presenter import MainWindowPresenter

MAIN_WINDOW_TITLE = "RasCAL-2"


class MainWindowView(QtWidgets.QMainWindow):
    """Creates the main view for the RasCAL application."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle(MAIN_WINDOW_TITLE)
        window_icon = QtGui.QIcon(path_for("logo.png"))

        self.undo_stack = QtGui.QUndoStack(self)
        self.undo_view = QtWidgets.QUndoView(self.undo_stack)
        self.undo_view.setWindowTitle("Undo History")
        self.undo_view.setWindowIcon(window_icon)
        self.undo_view.setAttribute(QtCore.Qt.WidgetAttribute.WA_QuitOnClose, False)

        self.presenter = MainWindowPresenter(self)
        self.mdi = QtWidgets.QMdiArea()

        self.plot_widget = PlotWidget(self)
        self.terminal_widget = TerminalWidget()
        self.controls_widget = ControlsWidget(self)
        self.project_widget = ProjectWidget(self)

        self.disabled_elements = []

        self.create_actions()
        self.create_menus()
        self.create_toolbar()
        self.create_status_bar()

        self.setMinimumSize(1024, 800)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)

        self.settings = Settings()
        self.startup_dlg = StartUpWidget(self)
        self.setCentralWidget(self.startup_dlg)

        self.about_dialog = AboutDialog(self)
        self.restoreGeometry(get_global_settings().value("window_geometry", bytearray(b"")))

    def closeEvent(self, event):
        if self.presenter.ask_to_save_project():
            event.accept()
        else:
            event.ignore()

    def show_project_dialog(self, dialog: StartupDialog):
        """Show a startup dialog of a given type.

        Parameters
        ----------
        dialog : StartupDialog
            The dialog to show.
        """
        if self.startup_dlg.isVisible():
            self.startup_dlg.hide()

        if self.presenter.ask_to_save_project():
            project_dlg = dialog(self)
            project_dlg.show()

    def show_settings_dialog(self, tab_name=""):
        """Show the settings dialog and makes tab with given name active.

        Parameters
        ----------
        tab_name : str, default ""
            The name of tab to make active.
        """
        settings_dlg = SettingsDialog(self)
        if tab_name:
            for i in range(settings_dlg.tab_widget.count()):
                if settings_dlg.tab_widget.tabText(i).lower() == tab_name.lower():
                    settings_dlg.tab_widget.setCurrentIndex(i)
                    break
        settings_dlg.show()

    def create_actions(self):
        """Create the menu and toolbar actions."""
        self.new_project_action = QtGui.QAction("&New Project", self)
        self.new_project_action.setStatusTip("Create a new project")
        self.new_project_action.setIcon(QtGui.QIcon(path_for("new-project.png")))
        self.new_project_action.triggered.connect(lambda: self.show_project_dialog(NewProjectDialog))
        self.new_project_action.setShortcut(QtGui.QKeySequence.StandardKey.New)

        self.open_project_action = QtGui.QAction("&Open Project", self)
        self.open_project_action.setStatusTip("Open an existing project")
        self.open_project_action.setIcon(QtGui.QIcon(path_for("browse-dark.png")))
        self.open_project_action.triggered.connect(lambda: self.show_project_dialog(LoadDialog))
        self.open_project_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)

        self.open_r1_action = QtGui.QAction("Open &RasCAL-1 Project")
        self.open_r1_action.setStatusTip("Open a RasCAL-1 project")
        self.open_r1_action.triggered.connect(lambda: self.show_project_dialog(LoadR1Dialog))

        self.actionImportORT = QtGui.QAction("Import ORSO (.ort)…", self)
        self.actionImportORT.setStatusTip("Import an ORSO .ort file (data + model)")
        self.actionImportORT.triggered.connect(lambda: self.show_project_dialog(ImportORTDialog))

        self.save_project_action = QtGui.QAction("&Save", self)
        self.save_project_action.setStatusTip("Save project")
        self.save_project_action.setIcon(QtGui.QIcon(path_for("save-project.png")))
        self.save_project_action.triggered.connect(lambda: self.presenter.save_project())
        self.save_project_action.setShortcut(QtGui.QKeySequence.StandardKey.Save)
        self.save_project_action.setEnabled(False)
        self.disabled_elements.append(self.save_project_action)

        self.save_as_action = QtGui.QAction("Save To &Folder...", self)
        self.save_as_action.setStatusTip("Save project to a specified folder.")
        self.save_as_action.setIcon(QtGui.QIcon(path_for("save-project.png")))
        self.save_as_action.triggered.connect(lambda: self.presenter.save_project(save_as=True))
        self.save_as_action.setShortcut(QtGui.QKeySequence.StandardKey.SaveAs)
        self.disabled_elements.append(self.save_project_action)

        self.undo_action = self.undo_stack.createUndoAction(self, "&Undo")
        self.undo_action.setStatusTip("Undo the last action")
        self.undo_action.setIcon(QtGui.QIcon(path_for("undo.png")))
        self.undo_action.setShortcut(QtGui.QKeySequence.StandardKey.Undo)

        self.redo_action = self.undo_stack.createRedoAction(self, "&Redo")
        self.redo_action.setStatusTip("Redo the last undone action")
        self.redo_action.setIcon(QtGui.QIcon(path_for("redo.png")))
        self.redo_action.setShortcut(QtGui.QKeySequence.StandardKey.Redo)

        self.undo_view_action = QtGui.QAction("Undo &History", self)
        self.undo_view_action.setStatusTip("View undo history")
        self.undo_view_action.triggered.connect(self.show_undo_view)
        self.undo_view_action.setEnabled(False)
        self.disabled_elements.append(self.undo_view_action)

        self.export_fits_action = QtGui.QAction("Export Fits", self)
        self.export_fits_action.setStatusTip("Export Result Data as CSV in a zip file.")
        self.export_fits_action.triggered.connect(self.presenter.export_fits)
        self.export_fits_action.setEnabled(False)
        self.disabled_elements.append(self.export_fits_action)

        self.settings_action = QtGui.QAction("Settings", self)
        self.settings_action.setStatusTip("Settings")
        self.settings_action.setIcon(QtGui.QIcon(path_for("settings.png")))
        self.settings_action.triggered.connect(lambda: self.show_settings_dialog())
        self.settings_action.setEnabled(False)
        self.disabled_elements.append(self.settings_action)

        self.open_help_action = QtGui.QAction("&Help", self)
        self.open_help_action.setStatusTip("Open Documentation")
        self.open_help_action.setIcon(QtGui.QIcon(path_for("help.png")))
        self.open_help_action.triggered.connect(self.open_docs)

        self.toggle_slider_action = QtGui.QAction("Show &Sliders", self)
        self.toggle_slider_action.setProperty("show_text", "Show &Sliders")
        self.toggle_slider_action.setProperty("hide_text", "Hide &Sliders")
        self.toggle_slider_action.setStatusTip("Show or Hide Sliders")
        self.toggle_slider_action.triggered.connect(self.toggle_sliders)
        self.toggle_slider_action.setEnabled(False)
        self.disabled_elements.append(self.toggle_slider_action)

        self.open_about_action = QtGui.QAction("&About", self)
        self.open_about_action.setStatusTip("Report RAT version&info")
        self.open_about_action.triggered.connect(self.open_about_info)

        self.exit_action = QtGui.QAction("E&xit", self)
        self.exit_action.setStatusTip(f"Quit {MAIN_WINDOW_TITLE}")
        self.exit_action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        self.exit_action.triggered.connect(self.close)

        # Window menu actions
        self.tile_windows_action = QtGui.QAction("Tile Windows", self)
        self.tile_windows_action.setStatusTip("Arrange windows in the default grid.")
        self.tile_windows_action.setIcon(QtGui.QIcon(path_for("tile.png")))
        self.tile_windows_action.triggered.connect(self.mdi.tileSubWindows)
        self.tile_windows_action.setEnabled(False)
        self.disabled_elements.append(self.tile_windows_action)

        self.reset_windows_action = QtGui.QAction("Reset to Default")
        self.reset_windows_action.setStatusTip("Reset the windows to their default arrangement.")
        self.reset_windows_action.triggered.connect(self.reset_mdi_layout)
        self.reset_windows_action.setEnabled(False)
        self.disabled_elements.append(self.reset_windows_action)

        self.save_default_windows_action = QtGui.QAction("Save Current Window Positions")
        self.save_default_windows_action.setStatusTip("Set the current window positions as default.")
        self.save_default_windows_action.triggered.connect(self.save_mdi_layout)
        self.save_default_windows_action.setEnabled(False)
        self.disabled_elements.append(self.save_default_windows_action)

        # Terminal menu actions
        self.clear_terminal_action = QtGui.QAction("Clear Terminal", self)
        self.clear_terminal_action.setStatusTip("Clear text in the terminal")
        self.clear_terminal_action.triggered.connect(self.terminal_widget.clear)

        self.setup_matlab_action = QtGui.QAction("Setup MATLAB", self)
        self.setup_matlab_action.setStatusTip("Set the path of the MATLAB executable")
        self.setup_matlab_action.triggered.connect(lambda: self.show_settings_dialog(tab_name="Matlab"))

    def create_menus(self):
        """Add sub menus to the main menu bar."""
        main_menu = self.menuBar()
        main_menu.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)

        file_menu = main_menu.addMenu("&File")
        file_menu.addAction(self.new_project_action)
        file_menu.addSeparator()
        file_menu.addAction(self.open_project_action)
        file_menu.addAction(self.open_r1_action)
        file_menu.addAction(self.actionImportORT)
        file_menu.addSeparator()
        file_menu.addAction(self.save_project_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_fits_action)
        file_menu.addSeparator()
        file_menu.addAction(self.settings_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        edit_menu = main_menu.addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addAction(self.undo_view_action)

        windows_menu = main_menu.addMenu("&Windows")
        windows_menu.addAction(self.tile_windows_action)
        windows_menu.addAction(self.reset_windows_action)
        windows_menu.addAction(self.save_default_windows_action)
        windows_menu.setEnabled(False)
        self.disabled_elements.append(windows_menu)

        tools_menu = main_menu.addMenu("&Tools")
        tools_menu.addAction(self.toggle_slider_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.clear_terminal_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.setup_matlab_action)

        help_menu = main_menu.addMenu("&Help")
        help_menu.addAction(self.open_about_action)
        help_menu.addAction(self.open_help_action)

    def toggle_sliders(self):
        """Toggle sliders for the fitted parameters in project class view."""
        show_text = self.toggle_slider_action.property("show_text")
        if self.toggle_slider_action.text() == show_text:
            hide_text = self.toggle_slider_action.property("hide_text")
            self.toggle_slider_action.setText(hide_text)
            self.project_widget.show_slider_view()
        else:
            self.toggle_slider_action.setText(show_text)
            self.project_widget.show_project_view()

    def open_about_info(self):
        """Open about dialog containing information about RASCAL."""
        self.about_dialog.update_rascal_info()
        self.about_dialog.show()

    def show_undo_view(self):
        """Show and raise undo view to top of parent."""
        self.undo_view.showNormal()
        self.undo_view.raise_()

    def open_docs(self):
        """Open the documentation."""
        url = QtCore.QUrl("https://rascalsoftware.github.io/RAT-Docs/dev/index.html")
        QtGui.QDesktopServices.openUrl(url)

    def create_toolbar(self):
        """Create the toolbar."""
        self.toolbar = self.addToolBar("ToolBar")
        self.toolbar.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        self.toolbar.setMovable(False)

        self.toolbar.addAction(self.new_project_action)
        self.toolbar.addAction(self.open_project_action)
        self.toolbar.addAction(self.save_project_action)
        self.toolbar.addAction(self.undo_action)
        self.toolbar.addAction(self.redo_action)
        self.toolbar.addAction(self.settings_action)
        self.toolbar.addAction(self.open_help_action)

    def create_status_bar(self):
        """Create the status bar."""
        sb = QtWidgets.QStatusBar()
        self.setStatusBar(sb)

    def setup_mdi(self):
        """Create the multi-document interface."""
        # if windows are already created, don't set them up again,
        # just refresh the widget data
        if len(self.mdi.subWindowList()) == 4:
            self.setup_mdi_widgets()
            return

        widgets = {
            "Plots": self.plot_widget,
            "Project": self.project_widget,
            "Terminal": self.terminal_widget,
            "Fitting Controls": self.controls_widget,
        }
        self.setup_mdi_widgets()

        for title, widget in reversed(widgets.items()):
            widget.setWindowTitle(title)
            window = self.mdi.addSubWindow(
                widget, QtCore.Qt.WindowType.WindowMinMaxButtonsHint | QtCore.Qt.WindowType.WindowTitleHint
            )
            window.setWindowTitle(title)
        self.reset_mdi_layout()
        self.startup_dlg = self.takeCentralWidget()
        self.setCentralWidget(self.mdi)

    def setup_mdi_widgets(self):
        """Perform initialization of MDI widgets that rely on the Project being defined."""
        self.controls_widget.setup_controls()
        self.project_widget.show_project_view()
        self.plot_widget.clear()
        self.terminal_widget.clear()
        self.terminal_widget.write_startup()

    def reset_mdi_layout(self):
        """Reset MDI layout to the default."""
        try:
            mdi_defaults = get_global_settings().value("mdi_defaults")
        except TypeError:
            mdi_defaults = None
        if mdi_defaults is None:
            for window in self.mdi.subWindowList():
                window.showNormal()
            self.mdi.tileSubWindows()
        else:
            for window in self.mdi.subWindowList():
                # get corresponding MDIGeometries entry for the widget
                widget_name = window.windowTitle().lower().split(" ")[-1]
                x, y, width, height, minimized = getattr(mdi_defaults, widget_name)
                if minimized:
                    window.showMinimized()
                else:
                    window.showNormal()
                window.setGeometry(x, y, width, height)

    def save_mdi_layout(self):
        """Set current MDI geometries as the default."""
        geoms = {}
        for window in self.mdi.subWindowList():
            # get corresponding MDIGeometries entry for the widget
            widget_name = window.windowTitle().lower().split(" ")[-1]
            geom = window.geometry()
            geoms[widget_name] = (geom.x(), geom.y(), geom.width(), geom.height(), window.isMinimized())

        global_setting = get_global_settings()
        global_setting.setValue("mdi_defaults", MDIGeometries.model_validate(geoms))
        global_setting.setValue("window_geometry", self.saveGeometry())
        global_setting.sync()

    def enable_elements(self):
        """Enable the elements that are disabled on startup."""
        for element in self.disabled_elements:
            element.setEnabled(True)
        self.disabled_elements = []

    def handle_results(self, results=None):
        """Handle the results of a RAT run.

        Parameters
        ----------
        results : Optional[Union[ratapi.outputs.Results, ratapi.outputs.BayesResults]]
            The calculation results.

        """
        self.controls_widget.run_button.setChecked(False)
        if results is not None:
            self.controls_widget.chi_squared.setText(f"{results.calculationResults.sumChi:.6g}")

    def set_editing_enabled(self, enabled: bool):
        """Disable or enable project editing, for example during a run.

        Parameters
        ----------
        enabled : bool
            indicates if project editing is enabled.

        """
        self.controls_widget.fit_settings.setEnabled(enabled)
        self.controls_widget.procedure_dropdown.setEnabled(enabled)
        self.undo_action.setEnabled(enabled and self.undo_stack.canUndo())
        self.redo_action.setEnabled(enabled and self.undo_stack.canRedo())
        self.project_widget.set_editing_enabled(enabled)

    def get_project_folder(self) -> str | None:
        """Get a specified folder from the user.

        Returns
        -------
        str
            The chosen project folder.
        """
        project_folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder")
        if project_folder:
            while self.check_save_blacklist(project_folder):
                project_folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder")

            if any(Path(project_folder, file).exists() for file in PROJECT_FILES):
                overwrite = self.show_confirm_dialog(
                    "Confirm Overwrite", "A project already exists in this folder, do you want to replace it?"
                )
                if not overwrite:
                    # return to file selection
                    project_folder = self.get_project_folder()
                    return project_folder  # must manually return else all the rejected overwrites will save at once!!

            return project_folder

        return None

    def get_save_file(self, caption, directory, file_filter) -> str:
        """Get a specified file to save to from the user.

        Parameters
        ----------
        caption : str
            The caption used for the save dialog.
        directory : str
            The working directory of the save dialog.
        file_filter : str
            The file types selected in the dialog.

        Returns
        -------
        str
            The chosen file.
        """
        save_file, _ = QtWidgets.QFileDialog.getSaveFileName(self, caption, directory, QtCore.QObject.tr(file_filter))
        while self.check_save_blacklist(save_file):
            save_file, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, caption, directory, QtCore.QObject.tr(file_filter)
            )

        return save_file

    def show_confirm_dialog(self, title: str, message: str) -> bool:
        """Ask the user to confirm an action.

        Parameters
        ----------
        title : str
            The title of the confirm dialog.
        message : str
            The message to ask the user.

        Returns
        -------
        bool
            Whether the confirmation was affirmative.
        """
        buttons = QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Cancel
        reply = QtWidgets.QMessageBox.question(
            self, title, message, buttons, QtWidgets.QMessageBox.StandardButton.Cancel
        )

        return reply == QtWidgets.QMessageBox.StandardButton.Ok

    def show_confirm_stop_calculation_dialog(self) -> bool:
        """Ask the user to confirm stopping the calculation.

        Returns
        -------
        bool
            Whether the confirmation was affirmative.
        """
        if not self.settings.show_stop_calculation_warning:
            return True

        message_box = QtWidgets.QMessageBox(self)
        message_box.setWindowTitle("Confirm Stop?")
        message_box.setText("For Bayesian procedures, stopping will lose all progress. Confirm Stop?")
        message_box.setIcon(QtWidgets.QMessageBox.Icon.Question)

        yes_button = message_box.addButton("Stop", QtWidgets.QMessageBox.ButtonRole.YesRole)
        no_button = message_box.addButton(QtWidgets.QMessageBox.StandardButton.Cancel)
        message_box.setDefaultButton(no_button)

        no_show_check_box = QtWidgets.QCheckBox("Do not show this again")
        message_box.setCheckBox(no_show_check_box)
        no_show_check_box.toggled.connect(lambda val: setattr(self.settings, "show_stop_calculation_warning", not val))
        message_box.exec()
        self.settings.set_global_settings()
        return message_box.clickedButton() == yes_button

    def show_unsaved_dialog(self, message: str) -> UnsavedReply:
        """Warn the user of unsaved changes, and ask whether to save those changes.

        Parameters
        ----------
        message : str
            The message to inform the user of unsaved changes.

        Returns
        -------
        rascal2.core.enums.UnsavedReply
            The user's response to the warning.
        """
        buttons = (
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel
        )
        reply = QtWidgets.QMessageBox.warning(
            self, MAIN_WINDOW_TITLE, message, buttons, QtWidgets.QMessageBox.StandardButton.Cancel
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Save:
            return UnsavedReply.Save
        elif reply == QtWidgets.QMessageBox.StandardButton.Discard:
            return UnsavedReply.Discard
        else:
            return UnsavedReply.Cancel

    def check_save_blacklist(self, save_path):
        """Check if user selected save path is invalid i.e. in the examples or tmp directory.

        Parameters
        ----------
        save_path : str
            The user selected save path.

        Returns
        -------
        bool
            Whether the save path is invalid.
        """
        if Path(save_path).is_relative_to(EXAMPLES_PATH):
            message = "Files cannot be saved in the examples directory. Please select another directory to save in."
        elif Path(save_path).is_relative_to(EXAMPLES_TEMP_PATH):
            message = "It is not recommended to save in the tmp directory. Please select another directory to save in."
        else:
            return False

        QtWidgets.QMessageBox.warning(
            self, "Warning", message, QtWidgets.QMessageBox.StandardButton.Ok, QtWidgets.QMessageBox.StandardButton.Ok
        )
        return True
