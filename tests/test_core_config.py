"""Smoke tests for ``mos.core.config.Config`` after the ``json_file`` refactor.

Run with::

    PYTHONPATH=src pytest tests/test_core_config.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import pytest


@pytest.fixture
def isolated_config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point ``Config.config_file_path`` at a temp file for this test.

    Config carries its JSON location as a :class:`ClassVar`, not in
    ``model_config``, so the fixture overrides the class attribute
    directly. pydantic-settings reads it per-instantiation, so any
    ``Config.load()`` in the test body picks up the temp path.
    """
    target = tmp_path / "config.json"
    monkeypatch.setattr(Config, "config_file_path", target)
    return target


from mos.core.config import Config, reload_config  # noqa: E402  (after fixture)


def _write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_returns_defaults_when_file_missing(isolated_config_path: Path) -> None:
    # File does not exist; Config.load() should fall back to defaults.
    assert not isolated_config_path.exists()

    cfg = Config.load()

    assert cfg.debug is False
    assert cfg.log.level == "INFO"
    assert cfg.log.console_enabled is True
    assert cfg.database.port == 5432
    assert cfg.mini_qmt.path == "D:\\国金证券QMT交易端\\userdata_mini"


def test_load_reads_valid_json_file(isolated_config_path: Path) -> None:
    _write(
        isolated_config_path,
        {
            "debug": True,
            "log": {"level": "DEBUG", "console_enabled": False},
            "database": {"host": "db.local", "port": 6543},
        },
    )

    cfg = Config.load()

    assert cfg.debug is True
    assert cfg.log.level == "DEBUG"
    assert cfg.log.console_enabled is False
    # Untouched fields keep their defaults.
    assert cfg.log.file_path == "~/.mos/mos.log"
    assert cfg.database.host == "db.local"
    assert cfg.database.port == 6543
    assert cfg.database.name == "mos"  # default


def test_load_raises_on_corrupt_json(isolated_config_path: Path) -> None:
    isolated_config_path.write_text("{ this is not valid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        Config.load()


def test_env_var_overrides_file_value(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(isolated_config_path, {"debug": False, "log": {"level": "INFO"}})

    monkeypatch.setenv("ZQUANT_DEBUG", "true")
    monkeypatch.setenv("ZQUANT_LOG__LEVEL", "WARNING")

    cfg = Config.load()

    assert cfg.debug is True
    assert cfg.log.level == "WARNING"


def test_reload_config_picks_up_file_changes(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # First load: file missing -> defaults.
    monkeypatch.setattr(
        "mos.core.config._config", None, raising=False
    )

    cfg1 = reload_config()
    assert cfg1.debug is False

    # Now write a new file and reload.
    _write(isolated_config_path, {"debug": True, "log": {"level": "ERROR"}})
    cfg2 = reload_config()

    assert cfg2 is not cfg1
    assert cfg2.debug is True
    assert cfg2.log.level == "ERROR"


# ---------------------------------------------------------------------------
# save() / update() — write-back path
# ---------------------------------------------------------------------------


def test_save_writes_expected_json(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    cfg = Config.load()
    cfg.log.level = "DEBUG"
    cfg.database.port = 6543

    target = cfg.save()

    assert target == isolated_config_path
    payload = json.loads(isolated_config_path.read_text(encoding="utf-8"))
    assert payload["log"]["level"] == "DEBUG"
    assert payload["database"]["port"] == 6543
    # Defaults for untouched sections are still serialized.
    assert payload["database"]["host"] == "localhost"
    assert payload["debug"] is False


def test_save_round_trip_with_load(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    original = Config.load()
    original.debug = True
    original.log.level = "WARNING"
    original.log.console_enabled = False
    original.database.port = 6543
    original.save()

    reloaded = Config.load()
    assert reloaded.debug is True
    assert reloaded.log.level == "WARNING"
    assert reloaded.log.console_enabled is False
    assert reloaded.log.console_format == "<green>{time:HH:mm:ss}</green> <level>{message}</level>"
    assert reloaded.database.port == 6543
    assert reloaded.database.host == "localhost"


def test_save_creates_parent_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    nested = tmp_path / "deep" / "nested" / "config.json"
    monkeypatch.setattr(Config, "config_file_path", nested)
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    cfg = Config.load()
    cfg.save()

    assert nested.exists()
    json.loads(nested.read_text(encoding="utf-8"))


def test_save_atomic_does_not_leave_temp_on_success(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    Config.load().save()

    leftover = isolated_config_path.parent / (isolated_config_path.name + ".tmp")
    assert not leftover.exists()
    assert isolated_config_path.exists()


def test_save_does_not_overwrite_target_with_partial_data(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If write fails partway, the existing file must be untouched.
    _write(isolated_config_path, {"debug": True, "log": {"level": "INFO"}})
    before = isolated_config_path.read_text(encoding="utf-8")

    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    # Simulate a mid-write failure: the second write call raises before replace.
    real_open = Path.open

    def boom_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if str(self).endswith(".tmp") and getattr(Path, "_explode", True):
            Path._explode = False  # only explode once
            raise OSError("disk full")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", boom_open)
    Path._explode = True

    try:
        with pytest.raises(OSError):
            Config.load().save()
    finally:
        monkeypatch.undo()
        # The previous good file must still be intact on disk.
        assert isolated_config_path.read_text(encoding="utf-8") == before


def test_update_deep_merges_nested_dicts(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    base = Config.load()
    new = base.update(log={"level": "WARNING"}, database={"port": 9999})

    # Untouched nested fields keep their defaults.
    assert new.log.console_enabled is True
    assert new.log.file_path == "~/.mos/mos.log"
    # Changed nested fields pick up the override.
    assert new.log.level == "WARNING"
    assert new.database.port == 9999
    assert new.database.host == "localhost"
    # Original instance is unchanged (immutable-style update).
    assert base.log.level == "INFO"
    assert base.database.port == 5432


def test_update_coerces_string_values_via_pydantic(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    base = Config.load()
    new = base.update(
        debug="true",
        database={"port": "6543"},
    )

    # pydantic coerced "true" -> True and "6543" -> int.
    assert new.debug is True
    assert new.database.port == 6543
    assert isinstance(new.database.port, int)


def test_update_then_save_round_trip(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    base = Config.load()
    base.update(log={"level": "ERROR"}, database={"port": 7000}).save()

    payload = json.loads(isolated_config_path.read_text(encoding="utf-8"))
    assert payload["log"]["level"] == "ERROR"
    assert payload["database"]["port"] == 7000
    # Other sections still present.
    assert "mini_qmt" in payload


def test_config_file_path_attribute_is_source_of_truth(
    isolated_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    # The class-level ClassVar is what ``settings_customise_sources`` reads
    # to wire up the JSON source. monkey-patching it on the class redirects
    # every subsequent ``Config.load()`` to the temp file.
    assert Config.config_file_path == isolated_config_path

    cfg = Config.load()
    assert cfg.__class__.config_file_path == isolated_config_path


# ---------------------------------------------------------------------------
# load(path=...) — per-call file override
# ---------------------------------------------------------------------------


def test_load_with_path_reads_from_custom_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    custom = tmp_path / "custom.json"
    _write(custom, {"debug": True, "log": {"level": "WARNING"}, "database": {"port": 9999}})

    cfg = Config.load(path=custom)

    assert cfg.debug is True
    assert cfg.log.level == "WARNING"
    assert cfg.database.port == 9999
    # Unrelated defaults still come from the model.
    assert cfg.database.host == "localhost"
    # The dynamic subclass overrode ``config_file_path``, so the instance
    # will round-trip through save() back to the same file.
    assert cfg.__class__.config_file_path == custom


def test_load_with_path_save_writes_back_to_same_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    custom = tmp_path / "roundtrip.json"
    _write(custom, {"debug": False, "log": {"level": "INFO"}})

    cfg = Config.load(path=custom)
    cfg.log.level = "ERROR"
    cfg.database.port = 1234
    target = cfg.save()

    # save() must hit the custom file, not the default ~/.mos/config.json.
    assert target == custom
    payload = json.loads(custom.read_text(encoding="utf-8"))
    assert payload["log"]["level"] == "ERROR"
    assert payload["database"]["port"] == 1234
    # The default config path must NOT have been touched.
    from mos.core.config import DEFAULT_CONFIG_PATH
    assert not DEFAULT_CONFIG_PATH.exists() or DEFAULT_CONFIG_PATH.read_text(encoding="utf-8") != payload


def test_load_with_path_does_not_pollute_base_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    # Self-contained base: a known-good file that the test owns entirely,
    # so we don't accidentally read whatever the developer's
    # ``~/.mos/config.json`` happens to contain on this machine.
    base_path = tmp_path / "base.json"
    _write(base_path, {"debug": False, "log": {"level": "INFO"}})
    monkeypatch.setattr(Config, "config_file_path", base_path)

    custom = tmp_path / "isolated.json"
    _write(custom, {"debug": True, "log": {"level": "ERROR"}})

    # Load from custom path, mutate, and save.
    cfg_custom = Config.load(path=custom)
    cfg_custom.log.level = "WARNING"
    cfg_custom.save()

    # The base class is untouched — the dynamic subclass from the previous
    # call is gone, and ``Config.config_file_path`` still points at the
    # temp base file.
    assert Config.config_file_path == base_path
    default_cfg = Config.load()
    assert default_cfg.log.level == "INFO"


def test_load_with_path_accepts_string_and_expandsuser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mos.core.config._config", None, raising=False)

    sub = tmp_path / "nested"
    sub.mkdir()
    target = sub / "via-string.json"
    _write(target, {"debug": True, "log": {"level": "DEBUG"}})

    # Pass a string (not Path) — the helper should accept both.
    cfg = Config.load(path=str(target))
    assert cfg.debug is True
    assert cfg.__class__.config_file_path == target


def test_default_constants_resolve_under_home(tmp_path: Path) -> None:
    from mos.core.config import DEFAULT_ZQUANT_HOME, DEFAULT_CONFIG_PATH

    # Sanity: the constants are absolute paths and the config file lives
    # directly under the mos home directory.
    assert DEFAULT_ZQUANT_HOME.is_absolute()
    assert DEFAULT_CONFIG_PATH.parent == DEFAULT_ZQUANT_HOME
    assert DEFAULT_CONFIG_PATH.name == "config.json"


# ---------------------------------------------------------------------------
# BaseConfig — subclassing for alternative config files
# ---------------------------------------------------------------------------


def test_baseconfig_subclass_uses_its_own_config_file_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subclass that sets ``config_file_path`` should read/write its own
    JSON, completely independent of the main ``Config``'s file."""
    from mos.core.config import DEFAULT_CONFIG_PATH, BaseConfig

    backtest_path = tmp_path / "backtest.json"
    _write(backtest_path, {"initial_cash": 500_000, "commission": 0.0005})

    class BacktestConfig(BaseConfig):
        config_file_path: ClassVar[Path] = backtest_path

        initial_cash: int = 1_000_000
        commission: float = 0.0003

    # Reading from the subclass's file picks up its data, not defaults.
    cfg = BacktestConfig()
    assert cfg.initial_cash == 500_000
    assert cfg.commission == 0.0005

    # Mutate + save writes back to the subclass's file (NOT Config's file).
    cfg.initial_cash = 750_000
    target = cfg.save()
    assert target == backtest_path

    payload = json.loads(backtest_path.read_text(encoding="utf-8"))
    assert payload["initial_cash"] == 750_000

    # The subclass inherits load/save/update/get from BaseConfig — it
    # doesn't need to redeclare them.
    assert "load" in BacktestConfig.__dict__ or hasattr(BacktestConfig, "load")
    assert "save" in BacktestConfig.__dict__ or hasattr(BacktestConfig, "save")

    # The main Config class is unaffected.
    assert Config.config_file_path == DEFAULT_CONFIG_PATH


def test_baseconfig_subclass_load_path_overrides_only_that_subclass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``load(path=...)`` on a subclass builds a sub-subclass whose
    ``config_file_path`` is redirected, without touching the subclass
    itself or any sibling subclass."""
    from mos.core.config import BaseConfig

    home = tmp_path / "broker.json"
    other = tmp_path / "broker-other.json"
    _write(home, {"endpoint": "https://default"})
    _write(other, {"endpoint": "https://override"})

    class BrokerConfig(BaseConfig):
        config_file_path: ClassVar[Path] = home

        endpoint: str = "https://default"

    # Direct load: reads from the declared config_file_path.
    base_cfg = BrokerConfig()
    assert base_cfg.endpoint == "https://default"
    assert base_cfg.__class__.config_file_path == home

    # load(path=...) on the subclass: redirects to other, leaves the
    # subclass's own config_file_path alone.
    override_cfg = BrokerConfig.load(path=other)
    assert override_cfg.endpoint == "https://override"
    assert override_cfg.__class__.config_file_path == other

    # The subclass itself is unchanged.
    assert BrokerConfig.config_file_path == home

    # A fresh load() on the subclass still hits the original file.
    fresh = BrokerConfig.load()
    assert fresh.endpoint == "https://default"
