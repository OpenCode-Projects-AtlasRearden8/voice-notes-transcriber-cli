"""Configuration loading for voice-notes-transcriber.

Precedence (last wins):
  1. built-in defaults
  2. ~/.config/vnt/vnt.toml
  3. ./vnt.toml (or --config PATH)
  4. environment variables (VNT_*)
  5. command-line flags

There are deliberately no API-key options anywhere: this tool is
local-first and only talks to keyless, local OpenAI-compatible endpoints.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_NOTES_DIR = "notes"

DEFAULT_AUDIO_EXTENSIONS: tuple[str, ...] = (
    ".m4a",
    ".mp4",
    ".mp3",
    ".wav",
    ".ogg",
    ".oga",
    ".flac",
    ".aac",
    ".opus",
    ".webm",
    ".amr",
    ".3gp",
    ".wma",
)

ENV_OVERRIDES = {
    "notes_dir": "VNT_NOTES_DIR",
    "asr_command": "VNT_ASR_COMMAND",
    "base_url": "VNT_BASE_URL",
    "llm_model": "VNT_LLM_MODEL",
    "transcribe_model": "VNT_TRANSCRIBE_MODEL",
}

_STRING_FIELDS = {
    "notes_dir",
    "asr_command",
    "base_url",
    "llm_model",
    "transcribe_model",
}
_FLOAT_FIELDS = {"asr_timeout", "chat_timeout"}
_INT_FIELDS = {"llm_max_chars"}


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is malformed."""


@dataclass
class Config:
    notes_dir: str = DEFAULT_NOTES_DIR
    asr_command: str | None = None
    asr_timeout: float = 600.0
    base_url: str = DEFAULT_BASE_URL
    llm_model: str | None = None
    transcribe_model: str | None = None
    chat_timeout: float = 120.0
    llm_max_chars: int = 8000
    audio_extensions: tuple[str, ...] = DEFAULT_AUDIO_EXTENSIONS
    offline: bool = False


def _read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc


def _coerce(key: str, value) -> object:
    if key in _STRING_FIELDS:
        if not isinstance(value, str):
            raise ConfigError(f"config key '{key}' must be a string")
        return value
    if key in _FLOAT_FIELDS:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ConfigError(f"config key '{key}' must be a number")
        return float(value)
    if key in _INT_FIELDS:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ConfigError(f"config key '{key}' must be an integer")
        return value
    if key == "offline":
        if not isinstance(value, bool):
            raise ConfigError("config key 'offline' must be true or false")
        return value
    if key == "audio_extensions":
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            return tuple(v.lower() for v in value)
        raise ConfigError("config key 'audio_extensions' must be a list of strings")
    raise ConfigError(f"unknown config key '{key}'")


def _apply_file(config: Config, path: Path) -> None:
    data = _read_toml(path)
    for key, value in data.items():
        if isinstance(value, dict):
            raise ConfigError(f"config key '{key}' in {path} is a table; values must be flat")
        setattr(config, key, _coerce(key, value))


def load_config(
    overrides: dict | None = None,
    config_path: Path | None = None,
) -> tuple[Config, list[Path]]:
    """Load the merged configuration.

    Returns the config plus the list of config files that were applied.
    """
    config = Config()
    used_files: list[Path] = []

    home_config = Path.home() / ".config" / "vnt" / "vnt.toml"
    if home_config.is_file():
        used_files.append(home_config)
        _apply_file(config, home_config)

    project_config = Path("vnt.toml")
    if project_config.is_file() and project_config.resolve() != home_config.resolve():
        used_files.append(project_config)
        _apply_file(config, project_config)

    if config_path is not None and config_path.is_file():
        if config_path.resolve() not in {p.resolve() for p in used_files}:
            used_files.append(config_path)
            _apply_file(config, config_path)
    elif config_path is not None:
        raise ConfigError(f"config file not found: {config_path}")

    for attr, env_name in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value:
            setattr(config, attr, _coerce(attr, value))

    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key == "offline":
            config.offline = True
            continue
        setattr(config, key, _coerce(key, value))

    if config.audio_extensions != tuple(
        ext.lower() for ext in config.audio_extensions
    ):
        config = replace(
            config,
            audio_extensions=tuple(ext.lower() for ext in config.audio_extensions),
        )
    return config, used_files
