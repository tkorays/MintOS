"""Generic settings base for JSON-backed configs.

This module hosts :class:`BaseConfig` — a pydantic-settings base that
lets concrete subclasses declare their JSON location as a
:class:`ClassVar` and inherit ``load`` / ``save`` / ``update`` / ``get``
from here. Project-specific configs (e.g. ``mos.core.config.Config``)
subclass it and add fields.

Why this lives in its own file:
    Keeping the generic base separate from project-specific config lets
    other packages (backtest, broker, data-source configs) import just
    :class:`BaseConfig` without pulling in mos's domain models. The
    dependency direction stays one-way: config -> baseconfig, never the
    reverse.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class BaseConfig(BaseSettings):
    """Generic settings base for JSON-backed configs.

    Subclasses declare a :class:`ClassVar` ``config_file_path`` pointing
    at their JSON file. The path is read at instantiation time inside
    :meth:`settings_customise_sources`, so each subclass's override
    takes effect without having to subclass per call site.

    Multiple concrete configs can share this base — the main app config,
    future backtest / broker / data-source configs — each pointing at a
    different file but reusing ``load`` / ``save`` / ``update`` / ``get``
    from here.
    """

    # Abstract: subclasses must override. Cannot live in ``model_config``
    # because that dict is captured at class definition time and would
    # freeze the *base's* path into every subclass. ClassVar keeps it
    # out of pydantic fields (this is metadata about the file, not
    # config data — we don't want it round-tripping through the JSON).
    config_file_path: ClassVar[Path]

    # Pydantic-settings configuration: subclasses SHOULD NOT override this.
    # The env_prefix and env_nested_delimiter are standardized across all
    # MOS configs to ensure consistent environment variable handling.
    # If a subclass needs different behavior, consider using a separate
    # BaseSettings class instead of inheriting from BaseConfig.
    model_config = SettingsConfigDict(
        json_file_encoding="utf-8",
        env_prefix="MOS_",
        env_nested_delimiter="__",
        extra="allow",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Inject the JSON source with the subclass-declared path.

        Called by pydantic-settings for *every* instantiation, so reading
        ``cls.config_file_path`` here (rather than baking it into
        ``model_config``) is what lets subclasses override the path.
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            JsonConfigSettingsSource(
                settings_cls,
                json_file=str(cls.config_file_path),
            ),
        )

    @classmethod
    def load(cls, *, path: Path | str | None = None) -> Self:
        """Load config, optionally from a non-default file path.

        Args:
            path: Override the JSON config file. The path is preserved on
                the returned instance — subsequent :meth:`save` calls write
                back to the same location. Intended primarily for tests
                that need isolation from the user's real config file.

        Implementation: pydantic-settings reads the JSON path at
        instantiation time, so per-call override happens at class level.
        We build a one-shot subclass with ``config_file_path`` redirected
        and instantiate it — the subclass goes out of scope immediately,
        so no global state is mutated and concurrent ``load()`` calls
        don't race.
        """
        if path is None:
            return cls()
        path = Path(path).expanduser()
        new_cls = type(cls)(cls.__name__, (cls,), {"config_file_path": path})
        return new_cls()

    def save(self, path: Path | str | None = None) -> Path:
        """Persist the current config to its JSON file (atomic write).

        pydantic-settings does not ship a write-back method, so we
        serialize with ``model_dump(mode="json")`` and write through a
        sibling temp file followed by ``os.replace`` — this avoids
        leaving a half-written file behind if the process is killed
        mid-write.

        Args:
            path: Optional override. Defaults to this instance's class
                ``config_file_path``.

        Returns:
            The path the config was written to.
        """
        target = Path(path or str(self.__class__.config_file_path)).expanduser()
        encoding = self.model_config.get("json_file_encoding", "utf-8")
        indent: int | str | None = self.model_config.get("json_file_indent", 2)

        target.parent.mkdir(parents=True, exist_ok=True)

        payload = self.model_dump(mode="json")
        # Serialize once up-front so a JSON error fails before we touch disk.
        rendered = json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"

        tmp = target.with_name(target.name + ".tmp")
        try:
            with tmp.open("w", encoding=encoding) as f:
                f.write(rendered)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target)
        except Exception:
            # Best-effort cleanup of the temp file on failure.
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

        return target

    def update(self, **kwargs: Any) -> Self:
        """Return a new instance with ``kwargs`` deep-merged into the current state.

        Read-modify-write counterpart to :meth:`save`: callers typically
        do ``new = cfg.update(...); new.save()``. Nested dicts are merged
        recursively, so ``update(log={"level": "DEBUG"})`` only touches
        ``log.level`` and leaves ``log.console_enabled`` intact.

        Non-dict values in ``kwargs`` overwrite the existing field
        wholesale. Type coercion (e.g. string "5433" → int 5433) is
        handled by pydantic during ``model_validate`` below.
        """
        merged = _deep_merge(self.model_dump(), kwargs)
        return type(self).model_validate(merged)

    def get(self, *keys: str, default: Any = None) -> Any:
        """Get nested config value by keys, e.g. config.get("log", "level")"""
        value = self.model_dump()
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, default)
            else:
                return default
        return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base``, returning a new dict.

    Dict-vs-dict collisions are merged; any other collision is overwritten.
    Neither input is mutated, so this is safe to call on ``model_dump()``
    results.
    """
    out: dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
