import pytest

from vnt.config import Config, ConfigError, _apply_file, load_config
from vnt.config_template import CONFIG_TEMPLATE, write_config_template


def test_defaults():
    config, used = load_config()
    assert config.base_url == "http://localhost:11434/v1"
    assert config.notes_dir == "notes"
    assert config.asr_command is None
    assert config.offline is False
    assert config.audio_extensions[0] == ".m4a"


def test_file_overrides_defaults(tmp_path):
    cfg_file = tmp_path / "vnt.toml"
    cfg_file.write_text(
        'notes_dir = "custom"\nasr_command = "my-asr {input}"\n',
        encoding="utf-8",
    )
    config, used = load_config(config_path=cfg_file)
    assert config.notes_dir == "custom"
    assert config.asr_command == "my-asr {input}"


def test_env_and_cli_override_file(tmp_path, monkeypatch):
    cfg_file = tmp_path / "vnt.toml"
    cfg_file.write_text('notes_dir = "from-file"\n', encoding="utf-8")
    monkeypatch.setenv("VNT_NOTES_DIR", "from-env")
    config, _ = load_config(config_path=cfg_file)
    assert config.notes_dir == "from-env"

    monkeypatch.delenv("VNT_NOTES_DIR")
    config, _ = load_config({"notes_dir": "from-cli"}, cfg_file)
    assert config.notes_dir == "from-cli"


def test_offline_override():
    config, _ = load_config({"offline": True})
    assert config.offline is True


def test_unknown_key_rejected(tmp_path):
    cfg_file = tmp_path / "bad.toml"
    cfg_file.write_text("nope = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        _apply_file(Config(), cfg_file)


def test_invalid_toml_rejected(tmp_path):
    cfg_file = tmp_path / "bad.toml"
    cfg_file.write_text("notes_dir = oops\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config_path=cfg_file)


def test_missing_config_path_rejected(tmp_path):
    from vnt.config import ConfigError

    with pytest.raises(ConfigError):
        load_config(config_path=tmp_path / "does-not-exist.toml")


def test_audio_extensions_lowercased():
    config = Config()
    config.audio_extensions = (".M4A", ".Wav")
    assert tuple(ext.lower() for ext in config.audio_extensions)[1] == ".wav"


def test_template_parses_as_toml(tmp_path):
    target = tmp_path / "vnt.toml"
    write_config_template(target)
    config, _ = load_config(config_path=target)
    assert config.notes_dir == "notes"
    assert "{{input}}" not in CONFIG_TEMPLATE
    assert "{input}" in CONFIG_TEMPLATE
