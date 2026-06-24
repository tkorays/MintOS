"""mos application configuration.

Project-specific config: the :class:`LogConfig` / :class:`LLMConfig`
sub-models, the main :class:`Config` subclass that points at
``~/.mos/config.json``, and the module-level ``get_config`` helper.
The generic :class:`BaseConfig` lives in :mod:`mos.core.baseconfig`.

Quant-specific config (DatabaseConfig, MiniQmtConfig, TimezoneConfig)
has been moved to :mod:`mos.quant.core.config`.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from mos.core.baseconfig import BaseConfig


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
# Resolved at import time. Tests should not rely on monkey-patching these;
# instead pass ``path=`` to :meth:`Config.load` (or subclass) to redirect
# the config file. Symlinking ``~/.mos`` is the deployment-time override.
DEFAULT_ZQUANT_HOME: Path = Path.home() / ".mos"
DEFAULT_CONFIG_PATH: Path = DEFAULT_ZQUANT_HOME / "config.json"


class LogConfig(BaseModel):
    """Log configuration
    """

    level: str = "INFO"
    console_enabled: bool = True
    console_format: str = "<green>{time:HH:mm:ss}</green> <level>{message}</level>"
    file_enabled: bool = False
    file_path: str = "~/.mos/mos.log"
    file_rotation: str = "100 MB"
    file_retention: str = "7 days"
    file_format: str = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"


class LLMConfig(BaseModel):
    """OpenAI-compatible LLM client configuration.

    ``api_key`` is intentionally *not* committed — it must be supplied
    via the ``MOS_LLM__API_KEY`` environment variable (or
    ``MOS_LLM__API_KEY`` in ``~/.mos/.env``). The placeholder
    string ``YOUR_API_KEY`` is recognised by the client as "no key"
    so unit tests can construct clients without authenticating.

    ``endpoint`` and ``model`` keep sensible defaults pointing at
    minimaxi's MiniMax-M3 (matching ``~/.hammerspoon/im_reply_assistant.lua``),
    but should be overridden per project.
    """

    endpoint: str = "https://api.minimaxi.com/v1/chat/completions"
    api_key: str = "YOUR_API_KEY"
    model: str = "MiniMax-M3"
    timeout: float = 25.0
    """HTTP timeout in seconds for chat-completions requests."""

    top_k: int = 5
    """Default number of wiki pages to retrieve for RAG-style ask."""


class PostgresConfig(BaseModel):
    """PostgreSQL configuration"""

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = ""
    # database for mos application
    database: str = "mos"


class PluginConfig(BaseModel):
    """User-installed plugin management.

    plugin_path: Directory under which ``mos plugin install`` places
        downloaded plugins. Each subdirectory is one plugin (a Python
        package exposing ``describe_plugin()``).
    disabled_plugins: Names of plugins to skip at load time, whether
        builtin or external. Edited via ``mos plugin enable|disable``.
    """

    plugin_path: str = "~/.mos/plugins/"
    disabled_plugins: list[str] = Field(default_factory=list)

    def get_expanded_path(self) -> str:
        """Return ``plugin_path`` with a leading ``~`` expanded."""
        if self.plugin_path.startswith("~"):
            return str(Path.home() / self.plugin_path[2:])
        return self.plugin_path


class Config(BaseConfig):
    """Main mos application config, located at
    :data:`DEFAULT_CONFIG_PATH` (``~/.mos/config.json`` by default).
    """

    config_file_path: ClassVar[Path] = DEFAULT_CONFIG_PATH

    debug: bool = False
    log: LogConfig = Field(default_factory=LogConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    plugin: PluginConfig = Field(default_factory=PluginConfig)


_config: Config | None = None


def get_config(reload: bool = False) -> Config:
    """Get or create global config instance.

    Args:
        reload: If True, reload config from file instead of using cached instance.

    Returns:
        The global Config instance.
    """
    global _config
    if reload or _config is None:
        _config = Config.load()
    return _config
