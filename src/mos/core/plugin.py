"""Plugin discovery contract for mos.

A plugin is a Python module / package that declares:

  * a CLI group (``click.Group``) the host can register under its own
    root command.

The host discovers a plugin by importing a known module and calling
its top-level ``describe_plugin()`` function, which must return a
:class:`PluginDefinition`.

Plugin sources:
    Plugins are installed via ``pip install`` and discovered through
    Python's entry_points mechanism. Each plugin declares an entry point
    in its ``pyproject.toml`` under the ``mos.plugins`` group.

Plugin module convention::

    # my_plugin/__init__.py
    import click
    from mos.core.plugin import PluginDefinition


    @click.group()
    def cli():
        \"\"\"My plugin CLI.\"\"\"
        pass


    def describe_plugin() -> PluginDefinition:
        return PluginDefinition(
            name="my_plugin",
            command=cli,
            get_config=get_my_config,
        )

The host then does::

    results = load_entry_point_plugins(disabled_plugins)
    for result in results:
        if result.status == "loaded":
            main_cli.add_command(result.definition.command)

Configuration:
    Plugins that need their own configuration should ship a config
    file in their own package and expose a ``config`` subcommand via
    their :class:`click.Group`. The host does not manage plugin
    configuration on their behalf.

Disabling:
    A plugin whose name appears in ``Config.disabled_plugins`` is
    skipped at load time and never reaches the registry. ``mos plugin
    disable <name>`` updates that list and additionally unregisters
    the plugin from the in-process registry so the change is visible
    immediately for the current session.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable

import click


# Entry point group name for MOS plugins
ENTRY_POINT_GROUP = "mos.plugins"


class PluginError(Exception):
    """Raised when a plugin module fails to load or describe itself.

    Wraps the underlying cause (missing function, wrong return type,
    exception inside ``describe_plugin``) so the host gets a single
    error class to catch without losing the original traceback.
    """


@dataclass
class PluginDefinition:
    """The contract a plugin module's ``describe_plugin()`` returns.

    Attributes:
        name: Plugin name, used for config type identification and for
            toggling on/off via ``mos plugin enable|disable``.
        command: A :class:`click.Group` to be registered under the
            host's main CLI.
        version: Plugin version, automatically extracted from package metadata.
        get_config: Optional function to get the plugin's config instance.
            The function should accept a ``reload: bool = False`` parameter
            to support reloading config from file. If None, the plugin
            does not provide configuration management.
        init: Optional initialization function called after plugin load.
        register_mcp: Optional function to register MCP tools.
    """

    name: str
    command: click.Group
    version: Optional[str] = None
    get_config: Optional[Callable] = None
    init: Optional[Callable] = None
    register_mcp: Optional[Callable] = None


class PluginRegistry:
    """In-memory registry of currently-loaded plugins.

    The registry is the single source of truth for "is plugin X
    routable right now?" — both the CLI dispatcher (via
    :func:`get_registry`) and the ``mos plugin`` commands read from
    it. Disable / remove operations mutate the registry so the change
    takes effect immediately for the running session.
    """

    def __init__(self):
        self._plugins: Dict[str, PluginDefinition] = {}

    def register(self, definition: PluginDefinition) -> None:
        """Register a plugin definition.

        Raises PluginError if a plugin with the same name is already registered.
        """
        if definition.name in self._plugins:
            raise PluginError(
                f"Plugin '{definition.name}' already registered; "
                f"refusing to overwrite"
            )
        self._plugins[definition.name] = definition

    def unregister(self, name: str) -> Optional[PluginDefinition]:
        """Remove a plugin from the registry.

        Returns the removed definition, or ``None`` if no such plugin
        was registered. After unregister, ``mos <plugin> ...`` is no
        longer routable until the plugin is reloaded (e.g. via
        ``mos plugin enable``).
        """
        return self._plugins.pop(name, None)

    def get(self, name: str) -> Optional[PluginDefinition]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def list_names(self) -> List[str]:
        """List all registered plugin names."""
        return list(self._plugins.keys())

    def all(self) -> List[PluginDefinition]:
        """Return all registered plugin definitions."""
        return list(self._plugins.values())

    def get_config_func(self, name: str) -> Optional[callable]:
        """Get the get_config function for a plugin."""
        plugin = self._plugins.get(name)
        return plugin.get_config if plugin else None


# Global plugin registry instance
_registry: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    """Get or create the global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def register_plugin(definition: PluginDefinition) -> None:
    """Register a plugin in the global registry."""
    get_registry().register(definition)


def unregister_plugin(name: str) -> Optional[PluginDefinition]:
    """Remove a plugin from the global registry. See
    :meth:`PluginRegistry.unregister`."""
    return get_registry().unregister(name)


# ---------------------------------------------------------------------------
# Entry point plugin discovery (pip-installed packages)
# ---------------------------------------------------------------------------
@dataclass
class ExternalPluginResult:
    """Per-entry-point outcome of :func:`load_entry_point_plugins`.

    Returned so the CLI can show the user which entry points were
    skipped, disabled, failed to load, or loaded — without losing
    the cause of the failure on the first error.
    """

    name: str
    status: str  # "loaded" | "disabled" | "error"
    error: Optional[str] = None
    definition: Optional[PluginDefinition] = None


def load_entry_point_plugins(
    disabled_names: Optional[List[str]] = None,
) -> List[ExternalPluginResult]:
    """Discover and load plugins via Python entry_points mechanism.

    This function scans installed packages' metadata for entry points
    declared under the ``mos.plugins`` group. Unlike external plugins
    (which are loaded from ``~/.mos/plugins/``), entry point plugins
    are installed via ``pip install`` and discovered automatically.

    Performance: This only reads package metadata files (``.dist-info/
    entry_points.txt``), not the actual plugin code. Discovery typically
    takes 20-50ms regardless of how many packages are installed.

    Args:
        disabled_names: Plugin names to skip (from
            ``Config.plugin.disabled_plugins``).

    Returns:
        List of :class:`ExternalPluginResult` for each discovered entry
        point. Status is ``loaded``, ``disabled``, or ``error``.
    """
    disabled = set(disabled_names or [])
    results: List[ExternalPluginResult] = []

    try:
        # Python 3.10+ style: entry_points() accepts group parameter
        entries = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        # Python 3.9 fallback: entry_points() returns dict-like object
        all_entries = importlib.metadata.entry_points()
        entries = all_entries.get(ENTRY_POINT_GROUP, [])

    for entry in entries:
        plugin_key = entry.name  # e.g., "agent" from "agent = mos_agent:describe_plugin"

        try:
            # Load the function referenced by the entry point
            describe_func = entry.load()
        except Exception as exc:
            results.append(
                ExternalPluginResult(
                    name=plugin_key,
                    status="error",
                    error=f"Failed to load entry point '{entry.value}': {exc}",
                )
            )
            continue

        if not callable(describe_func):
            results.append(
                ExternalPluginResult(
                    name=plugin_key,
                    status="error",
                    error=f"Entry point '{entry.value}' is not callable",
                )
            )
            continue

        try:
            definition = describe_func()
        except Exception as exc:
            results.append(
                ExternalPluginResult(
                    name=plugin_key,
                    status="error",
                    error=f"describe_plugin() raised: {exc}",
                )
            )
            continue

        if not isinstance(definition, PluginDefinition):
            results.append(
                ExternalPluginResult(
                    name=plugin_key,
                    status="error",
                    error=f"describe_plugin() must return PluginDefinition, "
                          f"got {type(definition).__name__}",
                )
            )
            continue

        # Extract version from package metadata
        try:
            if hasattr(entry, 'dist') and entry.dist is not None:
                definition.version = entry.dist.version
        except Exception:
            # Version extraction failed, keep as None
            pass

        # Register to global registry
        register_plugin(definition)

        # Check disabled list
        if definition.name in disabled:
            unregister_plugin(definition.name)
            results.append(
                ExternalPluginResult(
                    name=definition.name,
                    status="disabled",
                    definition=definition,
                )
            )
        else:
            results.append(
                ExternalPluginResult(
                    name=definition.name,
                    status="loaded",
                    definition=definition,
                )
            )

    return results
