"""Dialogs for editing custom files."""

from pathlib import Path

from PyQt6 import Qsci, QtCore, QtGui, QtWidgets
from ratapi.utils.enums import Languages

from rascal2.config import EXAMPLES_PATH, LOGGER, MatlabHelper
from rascal2.widgets.model_assistant import ModelAssistant


def edit_file(filename: str, language: Languages, parent: QtWidgets.QWidget):
    """Edit a file in the file editor.

    Parameters
    ----------
    filename : str
        The name of the file to edit.
    language : Languages
        The language for dialog highlighting.
    parent : QtWidgets.QWidget
        The parent of this widget.

    """
    file = Path(filename)
    if not file.is_file():
        LOGGER.error("Attempted to edit a custom file which does not exist!")
        return

    dialog = CustomFileEditorDialog(parent)
    dialog.open_file(file, language)
    dialog.setModal(False)
    dialog.show()


def edit_file_matlab(filename: str):
    """Open a file in MATLAB."""
    try:
        engine = MatlabHelper().get_local_engine()
    except Exception as ex:
        LOGGER.error("Attempted to edit a file in MATLAB engine", exc_info=ex)
        return

    engine.edit(str(filename))


class Singleton(type(QtWidgets.QDialog), type):
    """Metaclass used to create a PyQt singleton."""

    def __init__(cls, name, bases, cls_dict):
        super().__init__(name, bases, cls_dict)
        cls._instance = None

    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__call__(*args, **kwargs)
        return cls._instance


class CustomFileEditorDialog(QtWidgets.QDialog, metaclass=Singleton):
    """Dialog for editing custom files.

    Parameters
    ----------
    parent : QtWidgets.QWidget
        The parent of this widget.

    """

    def __init__(self, parent):
        super().__init__(parent)

        self.file = None
        self.unchanged_text = ""
        self.editor = Qsci.QsciScintilla()
        self.editor.setBraceMatching(Qsci.QsciScintilla.BraceMatch.SloppyBraceMatch)
        self.editor.setCaretLineVisible(True)
        self.editor.setCaretLineBackgroundColor(QtGui.QColor("#cccccc"))
        self.editor.setScrollWidth(1)
        self.editor.setEolMode(Qsci.QsciScintilla.EolMode.EolUnix)
        self.editor.setScrollWidthTracking(True)
        self.editor.setFolding(Qsci.QsciScintilla.FoldStyle.PlainFoldStyle)
        self.editor.setIndentationsUseTabs(False)
        self.editor.setIndentationGuides(True)
        self.editor.setAutoIndent(True)
        self.editor.setTabWidth(4)

        font = self.default_font
        self.editor.setFont(font)
        # Margin 0 is used for line numbers
        font_metrics = QtGui.QFontMetrics(font)
        self.editor.setMarginsFont(font)
        self.editor.setMarginWidth(0, font_metrics.horizontalAdvance("00000") + 6)
        self.editor.setMarginLineNumbers(0, True)
        self.editor.setMarginsBackgroundColor(QtGui.QColor("#cccccc"))
        self.editor.textChanged.connect(self.show_modified)

        save_button = QtWidgets.QPushButton("Save", self)
        save_button.clicked.connect(self.save_file)
        close_button = QtWidgets.QPushButton("Close", self)
        close_button.clicked.connect(self.reject)

        button_layout = QtWidgets.QHBoxLayout()
        assistant_button = QtWidgets.QPushButton("Model Assistant", self)
        assistant_button.setCheckable(True)
        button_layout.addWidget(assistant_button)
        button_layout.addStretch(1)
        button_layout.addWidget(save_button)
        button_layout.addWidget(close_button)
        button_layout.addSpacing(10)

        layout = QtWidgets.QVBoxLayout()
        self.assistant = ModelAssistant(self.editor, self)
        self.assistant.hide()
        assistant_button.toggled.connect(self.assistant.setVisible)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.assistant)
        splitter.setSizes([800, 440])
        layout.addWidget(splitter)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        layout.setContentsMargins(0, 0, 0, 0)

    @property
    def default_font(self):
        """Return default editor font.

        Returns
        -------
        font : QtGui.QFont
            The default font.

        """
        # Set the default font
        font = QtGui.QFont("Courier", 10)
        font.setFixedPitch(True)
        return font

    @property
    def is_modified(self):
        """Return if document is modified.

        Returns
        -------
        modified : bool
            Indicates if document is modified.

        """
        return self.unchanged_text != self.editor.text()

    def show_modified(self):
        """Show modified state in window title."""
        pre = "* " if self.is_modified else ""
        self.setWindowTitle(f"{pre}Edit {str(self.file)}")

    def open_file(self, file, language):
        """Open a custom file.

        Parameters
        ----------
        file : pathlib.Path
            The file to edit.
        language : Languages
            The language for dialog highlighting.
        """
        if file == self.file:
            return  # file is already opened

        if self.is_modified:
            result = QtWidgets.QMessageBox.question(
                self,
                "Save File",
                "Do you want to save changes to this file?",
                QtWidgets.QMessageBox.StandardButton.Discard | QtWidgets.QMessageBox.StandardButton.Save,
                QtWidgets.QMessageBox.StandardButton.Save,
            )
            if result == QtWidgets.QMessageBox.StandardButton.Save:
                self.save_file()

        self.file = file
        self.assistant.reset(language)
        self.setWindowTitle(f"Edit {str(file)}")
        match language:
            case Languages.Python:
                self.editor.setLexer(Qsci.QsciLexerPython(self.editor))
            case Languages.Matlab:
                self.editor.setLexer(Qsci.QsciLexerMatlab(self.editor))
            case _:
                self.editor.setLexer(None)

        if self.editor.lexer() is not None:
            self.editor.lexer().setFont(self.default_font)
        self.unchanged_text = self.file.read_text()
        self.editor.setText(self.unchanged_text)
        self.editor.setModified(False)
        self.setWindowModified(False)

    def save_file(self):
        """Save the custom file."""
        if not self.is_modified:
            return

        if self.file.is_relative_to(EXAMPLES_PATH):
            message = "Files cannot be saved into the examples directory, please copy the file to another directory."
            QtWidgets.QMessageBox.warning(self, "Save File", message, QtWidgets.QMessageBox.StandardButton.Ok)
            return

        try:
            self.file.write_text(self.editor.text())
            self.unchanged_text = self.editor.text()
            self.show_modified()
        except OSError as ex:
            message = f"Failed to save custom file to {self.file}.\n"
            LOGGER.error(message, exc_info=ex)
            QtWidgets.QMessageBox.critical(self, "Save File", message, QtWidgets.QMessageBox.StandardButton.Ok)

    def reject(self):
        if self.assistant.worker and self.assistant.worker.isRunning():
            self.assistant.stop()
            return
        CustomFileEditorDialog._instance = None
        super().reject()

    def closeEvent(self, event):
        if self.assistant.worker and self.assistant.worker.isRunning():
            self.assistant.stop()
            event.ignore()
            return
        super().closeEvent(event)
