"""Load and validate the JSON settings file (allowed action types and due-soon window)."""

import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.constants import ActionType

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.json"


class SettingsError(ValueError):
    """The settings file is missing, unreadable, not valid JSON, or has invalid values."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Limited to the action types the database accepts (see CHECK in schema.sql).
    allowed_action_types: list[ActionType] = Field(min_length=1)
    due_soon_days: Annotated[int, Field(ge=0, le=365)]

    @field_validator("allowed_action_types")
    @classmethod
    def no_duplicates(cls, value: list[ActionType]) -> list[ActionType]:
        if len(set(value)) != len(value):
            raise ValueError("action types must not repeat")
        return value


def load_settings(path: str | Path = DEFAULT_SETTINGS_PATH) -> Settings:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SettingsError(f"Settings file not found: {path}") from None
    except (OSError, UnicodeDecodeError) as error:
        raise SettingsError(f"Settings file could not be read: {path} ({error})") from error

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise SettingsError(
            f"Settings file is not valid JSON: {path} ({error.msg} at line {error.lineno}, column {error.colno})"
        ) from error
    if not isinstance(data, dict):
        raise SettingsError(f"Settings file must contain a JSON object: {path}")

    try:
        return Settings.model_validate(data)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg'].removeprefix('Value error, ')}"
            for problem in error.errors()
        )
        raise SettingsError(f"Invalid settings in {path}: {problems}") from None
