import shutil
from json import JSONDecodeError
from pathlib import Path

import ratapi as rat
import ratapi.outputs
from PyQt6 import QtCore
from rascal2.config import EXAMPLES_PATH, EXAMPLES_TEMP_PATH

from rascal2.config import EXAMPLES_PATH, EXAMPLES_TEMP_PATH


def copy_example_project(load_path):
    """Copy example project to temp directory so user does not modify original.

    Non-example projects are not copied.

    Parameters
    ----------
    load_path : str
        The load path of the project.

    Returns
    -------
    new_load_path: str
        The path of the copied project if project is example otherwise the same as load_path.
    """
    load_path = Path(load_path)
    if load_path.is_relative_to(EXAMPLES_PATH):
        if load_path.is_file():
            temp_dir = EXAMPLES_TEMP_PATH / load_path.parent.stem
            shutil.copytree(load_path.parent, temp_dir, dirs_exist_ok=True)
            load_path = temp_dir / load_path.name
        else:
            temp_dir = EXAMPLES_TEMP_PATH / load_path.name
            shutil.copytree(load_path, temp_dir, dirs_exist_ok=True)
            load_path = temp_dir
    return str(load_path)


def copy_example_project(load_path):
    """Copy example project to temp directory so user does not modify original.

    Non-example projects are not copied.

    Parameters
    ----------
    load_path : str
        The load path of the project.

    Returns
    -------
    new_load_path: str
        The path of the copied project if project is example otherwise the same as load_path.
    """
    load_path = Path(load_path)
    if load_path.is_relative_to(EXAMPLES_PATH):
        if load_path.is_file():
            temp_dir = EXAMPLES_TEMP_PATH / load_path.parent.stem
            shutil.copytree(load_path.parent, temp_dir, dirs_exist_ok=True)
            load_path = temp_dir / load_path.name
        else:
            temp_dir = EXAMPLES_TEMP_PATH / load_path.name
            shutil.copytree(load_path, temp_dir, dirs_exist_ok=True)
            load_path = temp_dir
    return str(load_path)

class MainWindowModel(QtCore.QObject):
    """Manages project data and communicates to view via signals.

    Emits
    -----
    project_updated
        A signal that indicates the project has been updated.
    controls_updated
        A signal that indicates the control has been updated.
    results_updated
        A signal that indicates the project and results have been updated.

    """

    project_updated = QtCore.pyqtSignal()
    controls_updated = QtCore.pyqtSignal()
    results_updated = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()

        self.project = None
        self.results = None
        self.result_log = ""
        self.controls = None

        self.save_path = ""

    def create_project(self, name: str, save_path: str):
        """Create a new RAT project and controls object.

        Parameters
        ----------
        name : str
            The name of the project.
        save_path : str
            The save path of the project.
        """
        self.project = rat.Project(name=name)
        self.project.contrasts.append(
            name="Default Contrast",
            background="Background 1",
            resolution="Resolution 1",
            scalefactor="Scalefactor 1",
            bulk_out="SLD D2O",
            bulk_in="SLD Air",
            data="Simulation",
        )
        self.controls = rat.Controls()
        self.results = rat.run(self.project, rat.Controls(display="off"))[1]
        self.save_path = save_path

    def update_results(self, results: ratapi.outputs.Results | ratapi.outputs.BayesResults):
        """Update the project given a set of results.

        Parameters
        ----------
        results : Union[ratapi.outputs.Results, ratapi.outputs.BayesResults]
            The calculation results.
        """
        self.results = results
        self.results_updated.emit()

    def update_project(self, new_values: dict) -> None:
        """Replace the project with a new project.

        Parameters
        ----------
        new_values : dict
            New values to set in the project.

        """
        vars(self.project).update(new_values)
        self.project_updated.emit()

    def save_project(self, save_path):
        """Save the project to the save path.

        Parameters
        ----------
        save_path : str
            The save path of the project.
        """
        self.controls.save(Path(save_path, "controls.json"))
        self.project.save(Path(save_path, "project.json"))
        if self.results:
            self.results.save(Path(save_path, "results.json"))
        self.save_path = save_path

    def is_project_example(self):
        return Path(self.save_path).is_relative_to(EXAMPLES_TEMP_PATH)

    def is_project_example(self):
        return Path(self.save_path).is_relative_to(EXAMPLES_TEMP_PATH)

    def load_project(self, load_path: str):
        """Load a project from a project folder.

        Parameters
        ----------
        load_path : str
            The path to the project folder.

        Raises
        ------
        ValueError
            If the project files are not in a valid format.

        """
        load_path = copy_example_project(load_path)

        results_file = Path(load_path, "results.json")
        try:
            results = rat.Results.load(results_file)
        except FileNotFoundError:
            # If results are not included, simply move on.
            results = None
        except ValueError as err:
            raise ValueError(
                "The results.json file for this project is not valid.\n"
                "It may contain invalid parameter values or be invalid JSON."
            ) from err

        controls_file = Path(load_path, "controls.json")
        try:
            controls = rat.Controls.load(controls_file)
        except ValueError as err:
            raise ValueError(
                "The controls.json file for this project is not valid.\n"
                "It may contain invalid parameter values or be invalid JSON."
            ) from err

        project_file = Path(load_path, "project.json")
        try:
            project = rat.Project.load(project_file)
        except JSONDecodeError as err:
            raise ValueError("The project.json file for this project contains invalid JSON.") from err
        except (KeyError, ValueError) as err:
            raise ValueError("The project.json file for this project is not valid.") from err

        self.results = results
        self.controls = controls
        self.project = project
        self.save_path = load_path

    def load_r1_project(self, load_path: str):
        """Load a project from a RasCAL-1 file.

        Parameters
        ----------
        load_path : str
            The path to the RasCAL-1 file.

        """
        load_path = copy_example_project(load_path)
        self.project = rat.utils.convert.r1_to_project(load_path)
        self.controls = rat.Controls()
        self.save_path = str(Path(load_path).parent)

    def update_controls(self, new_values: dict):
        """Update the control attributes.

        Parameters
        ----------
        new_values: dict
            The attribute name-value pair to updated on the controls.
        """
        vars(self.controls).update(new_values)
        self.controls_updated.emit()
