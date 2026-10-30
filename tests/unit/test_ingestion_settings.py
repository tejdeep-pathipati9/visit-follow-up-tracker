"""Settings file loading: valid files, missing files, bad JSON, and invalid values."""

import json

import pytest

from app.ingestion.settings import DEFAULT_SETTINGS_PATH, Settings, SettingsError, load_settings


def write_settings(path, content):
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return path


def test_loads_valid_settings(tmp_path):
    path = write_settings(
        tmp_path / "settings.json", {"allowed_action_types": ["lab", "referral"], "due_soon_days": 14}
    )

    assert load_settings(path) == Settings(allowed_action_types=["lab", "referral"], due_soon_days=14)


def test_accepts_zero_day_window_and_string_path(tmp_path):
    path = write_settings(
        tmp_path / "settings.json", {"allowed_action_types": ["recheck"], "due_soon_days": 0}
    )

    assert load_settings(str(path)).due_soon_days == 0


def test_repository_default_settings_file_is_valid():
    settings = load_settings(DEFAULT_SETTINGS_PATH)

    assert settings.allowed_action_types == ["lab", "referral", "recheck"]
    assert settings.due_soon_days == 7


def test_missing_file_names_the_path(tmp_path):
    path = tmp_path / "missing.json"

    with pytest.raises(SettingsError, match="not found") as error:
        load_settings(path)

    assert str(path) in str(error.value)


def test_directory_instead_of_file_is_a_clear_error(tmp_path):
    with pytest.raises(SettingsError, match="could not be read"):
        load_settings(tmp_path)


def test_invalid_json_is_reported_as_invalid_json(tmp_path):
    path = write_settings(tmp_path / "settings.json", "{bad json")

    with pytest.raises(SettingsError, match="not valid JSON"):
        load_settings(path)


def test_empty_file_is_reported_as_invalid_json(tmp_path):
    path = write_settings(tmp_path / "settings.json", "")

    with pytest.raises(SettingsError, match="not valid JSON"):
        load_settings(path)


def test_non_utf8_file_is_reported_as_unreadable(tmp_path):
    path = tmp_path / "settings.json"
    path.write_bytes(b"\xff\xfe\x00bad")

    with pytest.raises(SettingsError, match="could not be read"):
        load_settings(path)


@pytest.mark.parametrize("content", ["[]", '"text"', "7", "null"])
def test_json_that_is_not_an_object_is_rejected(tmp_path, content):
    path = write_settings(tmp_path / "settings.json", content)

    with pytest.raises(SettingsError, match="JSON object"):
        load_settings(path)


@pytest.mark.parametrize(
    ("content", "field"),
    [
        ({"due_soon_days": 7}, "allowed_action_types"),
        ({"allowed_action_types": ["lab"]}, "due_soon_days"),
        ({"allowed_action_types": [], "due_soon_days": 7}, "allowed_action_types"),
        ({"allowed_action_types": ["lab", "lab"], "due_soon_days": 7}, "allowed_action_types"),
        ({"allowed_action_types": ["surgery"], "due_soon_days": 7}, "allowed_action_types"),
        ({"allowed_action_types": "lab", "due_soon_days": 7}, "allowed_action_types"),
        ({"allowed_action_types": ["lab"], "due_soon_days": -1}, "due_soon_days"),
        ({"allowed_action_types": ["lab"], "due_soon_days": 366}, "due_soon_days"),
        ({"allowed_action_types": ["lab"], "due_soon_days": "7"}, "due_soon_days"),
        ({"allowed_action_types": ["lab"], "due_soon_days": 7.5}, "due_soon_days"),
        ({"allowed_action_types": ["lab"], "due_soon_days": True}, "due_soon_days"),
        ({"allowed_action_types": ["lab"], "due_soon_days": None}, "due_soon_days"),
        ({"allowed_action_types": ["lab"], "due_soon_days": 7, "extra": 1}, "extra"),
    ],
)
def test_invalid_values_name_the_offending_field(tmp_path, content, field):
    path = write_settings(tmp_path / "settings.json", content)

    with pytest.raises(SettingsError, match="Invalid settings") as error:
        load_settings(path)

    assert field in str(error.value)
    assert str(path) in str(error.value)
