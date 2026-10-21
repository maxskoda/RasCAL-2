"""Test the Settings model."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QSettings

from rascal2.settings import Settings, delete_local_settings, update_recent_projects


class MockGlobalSettings:
    """A mock of the global settings."""

    def __init__(self):
        self.settings = {"General/editor_fontsize": 15, "Terminal/terminal_fontsize": 28}

    def value(self, key):
        return self.settings[key]

    def allKeys(self):
        return list(self.settings.keys())


def mock_get_global_settings():
    """Mock for `get_global_settings`."""
    return MockGlobalSettings()


@patch("rascal2.settings.get_global_settings", new=mock_get_global_settings)
def test_global_defaults():
    """Test that settings are overwritten by global settings only if not manually set."""
    default_set = Settings()
    assert default_set.editor_fontsize == 15
    assert default_set.terminal_fontsize == 28
    edit_set = Settings(editor_fontsize=12)
    assert edit_set.editor_fontsize == 12
    assert edit_set.terminal_fontsize == 28
    all_set = Settings(editor_fontsize=12, terminal_fontsize=15)
    assert all_set.editor_fontsize == 12
    assert all_set.terminal_fontsize == 15


def test_delete_local_settings():
    """Test that the local settings file "settings.json" can be safely removed."""
    with tempfile.TemporaryDirectory() as temp:
        temp_settings_file = Path(temp, "settings.json")
        assert not temp_settings_file.exists()
        temp_settings_file.touch()
        assert temp_settings_file.exists()
        delete_local_settings(temp)
        assert not temp_settings_file.exists()
        # Delete does not raise an error if the settings file is not present
        delete_local_settings(temp)


@pytest.mark.parametrize("kwargs", [{}, {"style": "light", "editor_fontsize": 15}, {"terminal_fontsize": 8}])
@patch("rascal2.settings.get_global_settings", new=mock_get_global_settings)
def test_save(kwargs):
    """Tests that settings files can be saved and retrieved."""
    settings = Settings(**kwargs)
    with tempfile.TemporaryDirectory() as temp:
        settings.save(temp)
        json = Path(temp, "settings.json").read_text()

    for setting in kwargs:
        assert setting in json
        assert str(kwargs[setting]) in json

    loaded_settings = Settings.model_validate_json(json)

    assert settings == loaded_settings


@patch("rascal2.settings.get_global_settings")
def test_set_and_reset_global(mock_get_global):
    """Test that we can set manually-set project settings as global settings."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ini_file = Path(tmp_dir) / "settings.ini"
        global_setting = QSettings(str(ini_file), QSettings.Format.IniFormat)
        mock_get_global.return_value = global_setting
        settings = Settings()
        settings.set_global_settings()
        assert global_setting.allKeys() == []

        settings = Settings(editor_fontsize=9)
        settings.set_global_settings()
        assert global_setting.value("General/editor_fontsize") == 9
        settings.reset_global_settings()
        assert settings.editor_fontsize == 12
        assert global_setting.allKeys() == []

        settings = Settings(editor_fontsize=18, terminal_fontsize=3)
        settings.set_global_settings()
        assert global_setting.value("General/editor_fontsize") == 18
        assert global_setting.value("Terminal/terminal_fontsize") == 3
        settings.reset_global_settings()
        assert settings.editor_fontsize == 12
        assert settings.terminal_fontsize == 12
        assert global_setting.allKeys() == []


@pytest.mark.parametrize(
    "recent_projects, path, expected",
    (
        (["proj1", "proj2", "proj3"], None, ["proj1", "proj2", "proj3"]),
        (["proj1", "proj2", "DELETED"], None, ["proj1", "proj2"]),
        (["proj1", "proj2", "proj3"], "proj2", ["proj2", "proj1", "proj3"]),
    ),
)
@patch("rascal2.settings.QtCore.QSettings.setValue")
def test_update_recent_projects(set_val_mock, recent_projects, path, expected):
    """The recent projects should be updated to be newest to oldest with no deleted projects."""
    with tempfile.TemporaryDirectory() as temp:
        for proj in ["proj1", "proj2", "proj3"]:
            Path(temp, proj).touch()

        recent_projects = [str(Path(temp, proj)) for proj in recent_projects]
        expected = [str(Path(temp, proj)) for proj in expected]

        with patch("rascal2.settings.QtCore.QSettings.value", return_value=recent_projects):
            if path is not None:
                assert expected == update_recent_projects(str(Path(temp, path)))
            else:
                assert expected == update_recent_projects()


@pytest.mark.parametrize("error", [PermissionError(13, "Access denied"), OSError(1331, "Account disabled")])
@pytest.mark.parametrize("new_project", [None, "new-project"])
@patch("rascal2.settings.get_global_settings")
def test_recent_projects_skip_inaccessible_paths(mock_settings, error, new_project):
    """An inaccessible network path must not hide accessible projects or crash the dialog."""
    settings = mock_settings.return_value
    settings.value.return_value = ["accessible", "network-share", "missing", "another-accessible"]
    expected = ([new_project] if new_project else []) + ["accessible", "another-accessible"]
    with patch("rascal2.settings.Path.exists", side_effect=[True, error, False, True]):
        assert update_recent_projects(new_project) == expected
    settings.setValue.assert_called_once_with("recent_projects", expected)
    settings.sync.assert_called_once_with()
