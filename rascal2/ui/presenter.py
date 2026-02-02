import re
import warnings
from typing import Any

import ratapi as rat
import ratapi.wrappers

from rascal2.config import LOGGER, MatlabHelper
from rascal2.core import commands
from rascal2.core.enums import UnsavedReply
from rascal2.core.runner import LogData, RATRunner
from rascal2.core.writer import write_result_to_zipped_csvs
from rascal2.settings import update_recent_projects

from .model import MainWindowModel


class MainWindowPresenter:
    """Facilitates interaction between View and Model.

    Parameters
    ----------
    view : MainWindow
        An instance of the MainWindowView
    """

    def __init__(self, view):
        self.view = view
        self.model = MainWindowModel()
        self.worker = None

    def create_project(self, name: str, save_path: str):
        """Create a new RAT project and controls object then initialise UI.

        Parameters
        ----------
        name : str
            The name of the project.
        save_path : str
            The save path of the project.

        """
        self.model.create_project(name, save_path)
        self.initialise_ui()

    def load_project(self, load_path: str):
        """Load an existing RAT project then initialise UI.

        Parameters
        ----------
        load_path : str
            The path from which to load the project.

        """
        self.model.load_project(load_path)
        if self.model.results is None:
            self.model.results = self.quick_run()
        update_recent_projects(load_path)

    def load_r1_project(self, load_path: str):
        """Load a RAT project from a RasCAL-1 project file.

        Parameters
        ----------
        load_path : str
            The path to the R1 file.

        """
        self.model.load_r1_project(load_path)
        self.model.results = self.quick_run()

    def initialise_ui(self):
        """Initialise UI for a project."""
        suffix = " [Example]" if self.model.is_project_example() else f"[{self.model.save_path}]"
        self.view.setWindowTitle(
            self.view.windowTitle().split(" - ")[0] + " - " + self.model.project.name + suffix,
        )
        self.view.setup_mdi()
        self.view.plot_widget.update_plots()
        self.view.handle_results(self.model.results)
        self.view.undo_stack.clear()
        self.view.enable_elements()

    def import_ort_project(self, ort_path: str, project_folder: str):
        from rascal2.core.orso_importer import import_ort_to_project
        from pathlib import Path
        from rascal2.settings import update_recent_projects

        ort_file = Path(ort_path)
        proj_name = ort_file.stem.replace("_", " ").strip() or "ORSO Import"
        save_path = str(Path(project_folder))  # ✅ use what user selected

        self.model.create_project(proj_name, save_path)

        imported_project, imported_controls = import_ort_to_project(
            ort_path,
            base_project=self.model.project,
            project_folder=save_path,
        )

        self.model.project = imported_project
        if imported_controls is not None:
            self.model.controls = imported_controls

        # Optional preview run (no MATLAB required for standard layers)
        print("Imported layers:", len(self.model.project.layers))
        print("Imported parameters:", len(self.model.project.parameters))
        print("First layer:", self.model.project.layers[0] if self.model.project.layers else None)

        self.model.results = self.quick_run(self.model.project)

        # Persist so it becomes a normal RasCAL-2 project folder
        self.model.save_project()
        update_recent_projects(self.model.save_path)

    def edit_controls(self, setting: str, value: Any):
        """Edit a setting in the Controls object.

        Parameters
        ----------
        setting : str
            Which setting in the Controls object should be changed.
        value : Any
            The value which the setting should be changed to.

        Raises
        ------
        ValidationError
            If the setting is changed to an invalid value.

        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model.controls.model_validate({setting: value})
            self.view.undo_stack.push(commands.EditControls({setting: value}, self))

    def save_project(self, save_as: bool = False):
        """Save the model.

        Parameters
        ----------
        save_as : bool
            Whether we are saving to the existing save path or to a specified folder.

        Returns
        -------
         : bool
            Indicates if the project was saved.
        """
        to_path = self.model.save_path
        if save_as or self.model.is_project_example():
            to_path = self.view.get_project_folder()
            if not to_path:
                return False
        try:
            self.model.save_project(to_path)
        except OSError as err:
            LOGGER.error(f"Failed to save project to {to_path}.\n", exc_info=err)
        else:
            update_recent_projects(self.model.save_path)
            self.view.undo_stack.setClean()
        return True

    def ask_to_save_project(self):
        """Warn the user of unsaved changes."""
        proceed = True

        if not self.view.undo_stack.isClean():
            message = "The project has been modified. Do you want to save changes?"
            reply = self.view.show_unsaved_dialog(message)
            if reply == UnsavedReply.Save:
                proceed = self.save_project()
            elif reply == UnsavedReply.Cancel:
                proceed = False

        return proceed

    def export_fits(self):
        """Export results into multiple csv files in a zip file."""
        if self.model.results is None:
            return

        results = self.model.results
        filename = self.model.project.name.replace(" ", "_")
        save_file = self.view.get_save_file("Export Results as ZIP Archive", filename, "*.zip")
        if not save_file:
            return

        try:
            write_result_to_zipped_csvs(save_file, results)
        except OSError as err:
            LOGGER.error(f"Failed to save fits to {save_file}.\n", exc_info=err)

    def interrupt_terminal(self):
        """Send an interrupt signal to the RAT runner."""
        if self.model.controls.procedure in [rat.utils.enums.Procedures.Simplex, rat.utils.enums.Procedures.DE]:
            self.model.controls.sendStopEvent()
        else:
            if not self.view.show_confirm_stop_calculation_dialog():
                return
            if self.runner.process.is_alive():
                self.runner.interrupt()

    def quick_run(self, project=None):
        """Run rat calculation with calculate procedure on the given project.

        The project in the MainWindowModel is used if no project is provided.

        Parameters
        ----------
        project : Optional[ratapi.Project]
            The project to use for run

        Returns
        -------
        results : Union[ratapi.outputs.Results, ratapi.outputs.BayesResults]
            The calculation results.
        """
        if project is None:
            project = self.model.project
        if ratapi.wrappers.MatlabWrapper.loader is None and any(
            [file.language == "matlab" for file in self.model.project.custom_files]
        ):
            matlab_helper = MatlabHelper()
            matlab_helper.get_local_engine()
        return rat.run(project, rat.Controls(display="off"))[1]

    def run(self):
        """Run rat using multiprocessing."""
        # reset terminal
        self.view.terminal_widget.progress_bar.setVisible(False)
        if self.view.settings.clear_terminal:
            self.view.terminal_widget.clear()

        # hide bayes plots button so users can't open plots during run
        self.view.plot_widget.bayes_plots_button.setVisible(False)

        self.model.controls.initialise_IPC()
        rat_inputs = rat.inputs.make_input(self.model.project, self.model.controls)
        display_on = self.model.controls.display != rat.utils.enums.Display.Off

        self.runner = RATRunner(rat_inputs, self.model.controls.procedure, display_on)
        self.runner.finished.connect(self.handle_results)
        self.runner.stopped.connect(self.handle_interrupt)
        self.runner.event_received.connect(self.handle_event)
        self.runner.start()

    def handle_results(self):
        """Handle a RAT run being finished."""
        self.view.undo_stack.push(
            commands.SaveCalculationOutputs(
                self.runner.updated_problem,
                self.runner.results,
                self.view.terminal_widget.text_area.toPlainText(),
                self,
            )
        )
        self.view.handle_results(self.runner.results)
        self.model.controls.delete_IPC()

    def handle_interrupt(self):
        """Handle a RAT run being interrupted."""
        if self.runner.error is None:
            LOGGER.info("RAT run interrupted!")
        else:
            LOGGER.error("RAT run failed with exception.\n", exc_info=self.runner.error)
        self.view.handle_results()
        self.model.controls.delete_IPC()

    def handle_event(self):
        """Handle event data produced by the RAT run."""
        event = self.runner.events.pop(0)
        match event:
            case str():
                self.view.terminal_widget.write(event)
                chi_squared = get_live_chi_squared(event, str(self.model.controls.procedure))
                if chi_squared is not None:
                    self.view.controls_widget.chi_squared.setText(chi_squared)
            case rat.events.ProgressEventData():
                self.view.terminal_widget.update_progress(event)
            case rat.events.PlotEventData():
                self.view.plot_widget.plot_with_blit(event)
            case LogData():
                LOGGER.log(event.level, event.msg)

    def edit_project(self, updated_project: dict, preview: bool = True) -> None:
        """Edit the Project with a dictionary of attributes.

        Parameters
        ----------
        updated_project : dict
            The updated project attributes.
        preview : bool
            indicates if the result should be previewed after update.

        Raises
        ------
        ValidationError
            If the updated project attributes are not valid.

        """
        project_dict = self.model.project.model_dump()
        project_dict.update(updated_project)
        self.model.project.model_validate(project_dict)
        self.view.undo_stack.push(commands.EditProject(updated_project, self, preview=preview))


# '\d+\.\d+' is the regex for
# 'some integer, then a decimal point, then another integer'
# the parentheses () mean it is put in capture group 1,
# which is what we return as the chi-squared value
# we compile these regexes on import to make `get_live_chi_squared` basically instant
chi_squared_patterns = {
    "simplex": re.compile(r"(\d+\.\d+)"),
    "de": re.compile(r"Best: (\d+\.\d+)"),
}


def get_live_chi_squared(item: str, procedure: str) -> str | None:
    """Get the chi-squared value from iteration message data.

    Parameters
    ----------
    item : str
        The iteration message.
    procedure : str
        The procedure currently running.

    Returns
    -------
    str or None
        The chi-squared value from that procedure's message data in string form,
        or None if one has not been found.

    """
    if procedure not in chi_squared_patterns:
        return None
    # match returns None if no match found, so whether one is found can be checked via 'if match'
    return match.group(1) if (match := chi_squared_patterns[procedure].search(item)) else None
