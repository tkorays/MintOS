"""Plugin discovery contract for mos.

A plugin is a Python module / package that declares:

  * a CLI group (``click.Group``) the host can register under its own
    root command, and
  * a set of :class:`Resource` objects the plugin owns in some
    external system (e.g. Grafana dashboards, alerting rules).

The host discovers a plugin by importing a known module and calling
its top-level ``describe_plugin()`` function, which must return a
:class:`PluginDefinition`.

Plugin sources:
    ``BUILTIN`` plugins ship inside the ``mos`` package (``mos.quant``,
    ``mos.wiki``, ``mos.work``) and are loaded by name.
    ``EXTERNAL`` plugins live under ``plugin_path`` (default
    ``~/.mos/plugins/``); each subdirectory is treated as a Python
    package whose top-level ``describe_plugin()`` is invoked at startup.

Plugin module convention::

    # my_plugin/__init__.py
    import click
    from mos.core.plugin import PluginDefinition, Resource


    @click.group()
    def cli():
        \"\"\"My plugin CLI.\"\"\"
        pass


    class MyDashboard(Resource):
        @property
        def name(self) -> str:
            return "my-dashboard"

        def install(self) -> None:
            ...  # push to the external system

        def uninstall(self) -> None:
            ...  # remove from external system


    def describe_plugin() -> PluginDefinition:
        return PluginDefinition(
            name="my_plugin",
            command=cli,
            get_config=get_my_config,
            reload_config=reload_my_config,
            resources=[MyDashboard()],
        )

The host then does::

    definition = load_plugin("mos.quant")           # builtin
    definition = load_external_plugin(path, name)   # external
    main_cli.add_command(definition.command)
    for resource in definition.resources:
        resource.install()

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

import importlib
import importlib.metadata
import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Callable
from mos.core.resource import Resource

import click


# Entry point group name for MOS plugins
ENTRY_POINT_GROUP = "mos.plugins"


class PluginError(Exception):
    """Raised when a plugin module fails to load or describe itself.

    Wraps the underlying cause (missing function, wrong return type,
    exception inside ``describe_plugin``) so the host gets a single
    error class to catch without losing the original traceback.
    """


class PluginSource(str, Enum):
    """Where a :class:`PluginDefinition` came from.

    ``BUILTIN`` plugins are part of the ``mos`` package and loaded by
    their dotted module path (``mos.quant`` etc.). ``EXTERNAL`` plugins
    live under the user's ``plugin_path`` (each subdirectory is one
    plugin) and were installed via ``mos plugin install``.
    """

    BUILTIN = "builtin"
    EXTERNAL = "external"


@dataclass
class PluginDefinition:
    """The contract a plugin module's ``describe_plugin()`` returns.

    Attributes:
        name: Plugin name, used for config type identification and for
            toggling on/off via ``mos plugin enable|disable``.
        command: A :class:`click.Group` to be registered under the
            host's main CLI.
        get_config: Function to get the plugin's config instance.
        reload_config: Function to reload the plugin's config from file.
        resources: Resources this plugin owns. May be empty if the
            plugin is CLI-only.
        source: Where this plugin was loaded from. Set automatically by
            :func:`load_plugin` / :func:`load_external_plugin`; plugin
            authors don't fill this in.
        path: Filesystem location the plugin was loaded from.
            ``None`` for builtins.
    """

    name: str
    command: click.Group
    get_config: Callable
    reload_config: Callable
    register_mcp: Optional[Callable] = None
    resources: List[Resource] = field(default_factory=list)
    source: PluginSource = PluginSource.BUILTIN
    path: Optional[Path] = None


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

        Builtins and externals share the same namespace; if an external
        tries to register a name already taken by a builtin, raise so
        the host can decide (typically: tell the user to disable the
        builtin first).
        """
        if definition.name in self._plugins:
            existing = self._plugins[definition.name]
            raise PluginError(
                f"Plugin '{definition.name}' already registered "
                f"(source={existing.source.value}); "
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

    def get_reload_func(self, name: str) -> Optional[callable]:
        """Get the reload_config function for a plugin."""
        plugin = self._plugins.get(name)
        return plugin.reload_config if plugin else None


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


def load_plugin(
    module_name: str,
    disabled_names: Optional[List[str]] = None,
) -> Optional[PluginDefinition]:
    """Load a builtin plugin by dotted module name and return its definition.

    The host calls this for each builtin plugin it wants to enable. We
    import the module (executing its top-level code) and then call the
    module's ``describe_plugin()`` to discover the CLI group and
    resources.

    Args:
        module_name: Dotted Python module path, e.g.
            ``"mos.quant"`` or ``"zquant_plugins.grafana"``.
        disabled_names: Plugin names (as returned by
            ``PluginDefinition.name``) to skip. When a plugin's
            registered name appears in this list, the plugin is
            unloaded from the in-process registry and ``None`` is
            returned. Mirrors the disabled-list semantics of
            :func:`load_external_plugins` so callers can apply the
            same ``Config.plugin.disabled_plugins`` list uniformly.

    Returns:
        The :class:`PluginDefinition` produced by the plugin, or
        ``None`` if the plugin's name is in ``disabled_names``.

    Raises:
        ImportError: If the module cannot be imported (propagated
            from :func:`importlib.import_module`).
        PluginError: If the module lacks ``describe_plugin``, the
            function returns the wrong type, or the function raises.
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None

    describe = getattr(module, "describe_plugin", None)
    if describe is None:
        raise PluginError(
            f"Plugin module {module_name!r} does not define a "
            f"'describe_plugin' function"
        )
    if not callable(describe):
        raise PluginError(
            f"Plugin module {module_name!r}: 'describe_plugin' is not callable"
        )

    try:
        definition = describe()
    except Exception as exc:
        raise PluginError(
            f"Plugin module {module_name!r}: describe_plugin() raised"
        ) from exc

    if not isinstance(definition, PluginDefinition):
        raise PluginError(
            f"Plugin module {module_name!r}: describe_plugin() must return "
            f"a PluginDefinition, got {type(definition).__name__}"
        )

    definition.source = PluginSource.BUILTIN
    definition.path = None

    # Honor the disabled list: same pattern as
    # :func:`load_external_plugins` — register first (so the module's
    # import-time side effects are observable), then roll back the
    # registration if the plugin's registered name is in the disabled
    # list. The module is still imported either way; there is no cheap
    # way to learn ``PluginDefinition.name`` without calling
    # ``describe_plugin()``.
    disabled = set(disabled_names or [])
    if definition.name in disabled:
        unregister_plugin(definition.name)
        return None

    register_plugin(definition)
    return definition


# ---------------------------------------------------------------------------
# External plugins (user-installed under plugin_path)
# ---------------------------------------------------------------------------
@dataclass
class ExternalPluginResult:
    """Per-directory outcome of :func:`load_external_plugins`.

    Returned so the CLI can show the user which subdirectories were
    skipped, disabled, failed to import, or loaded — without losing
    the cause of the failure on the first error.
    """

    name: str
    status: str  # "loaded" | "disabled" | "error"
    error: Optional[str] = None
    definition: Optional[PluginDefinition] = None


def list_external_plugin_dirs(plugin_path: Path) -> List[Path]:
    """Return subdirectories of ``plugin_path`` that look like plugins.

    A subdirectory is a candidate if it contains an ``__init__.py``
    (treats it as a regular Python package). Bare directories without
    ``__init__.py`` are skipped — they might be data folders or git
    clones the user is mid-install.

    Hidden / dotfile directories (``.foo``) are filtered out so
    ``ls -la``-style artifacts don't show up in ``mos plugin list``.
    """
    if not plugin_path.exists() or not plugin_path.is_dir():
        return []

    candidates: List[Path] = []
    for entry in sorted(plugin_path.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if not (entry / "__init__.py").exists():
            continue
        candidates.append(entry)
    return candidates


# Back-compat alias used by tests / older callers.
_candidate_plugin_dirs = list_external_plugin_dirs


def _load_external_one(plugin_dir: Path) -> PluginDefinition:
    """Load a single external plugin from its on-disk directory.

    Adds the plugin directory's parent to ``sys.path`` (so the
    subdirectory can be imported as a top-level package), imports it,
    validates ``describe_plugin()``, marks the result
    :attr:`PluginSource.EXTERNAL`, and registers it.

    Raises:
        PluginError: If the directory cannot be imported, lacks
            ``describe_plugin``, or describes itself incorrectly.
    """
    plugin_path = plugin_dir.resolve()
    parent = plugin_path.parent
    name = plugin_path.name

    parent_str = str(parent)
    if parent_str not in sys.path:
        sys.path.insert(0, parent_str)

    # Use importlib so we control re-imports on re-enable, rather than
    # letting ``import`` return a stale cached module.
    spec = importlib.util.spec_from_file_location(
        name, plugin_path / "__init__.py"
    )
    if spec is None or spec.loader is None:
        raise PluginError(f"Cannot build import spec for {plugin_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PluginError(f"Failed to execute {plugin_path}: {exc}") from exc

    describe = getattr(module, "describe_plugin", None)
    if describe is None:
        raise PluginError(
            f"External plugin {plugin_path} does not define "
            f"'describe_plugin'"
        )
    if not callable(describe):
        raise PluginError(
            f"External plugin {plugin_path}: 'describe_plugin' is not callable"
        )

    try:
        definition = describe()
    except Exception as exc:
        raise PluginError(
            f"External plugin {plugin_path}: describe_plugin() raised"
        ) from exc

    if not isinstance(definition, PluginDefinition):
        raise PluginError(
            f"External plugin {plugin_path}: describe_plugin() must "
            f"return PluginDefinition, got {type(definition).__name__}"
        )

    definition.source = PluginSource.EXTERNAL
    definition.path = plugin_path
    register_plugin(definition)
    return definition


def load_external_plugins(
    plugin_path: Path,
    disabled_names: Optional[List[str]] = None,
) -> List[ExternalPluginResult]:
    """Discover and load all external plugins under ``plugin_path``.

    Each subdirectory of ``plugin_path`` containing an ``__init__.py``
    is treated as a plugin. Plugins whose ``PluginDefinition.name``
    appears in ``disabled_names`` are skipped (not registered), so the
    user can disable a plugin by name without removing the directory.

    The returned list is one :class:`ExternalPluginResult` per
    candidate directory — even failures are reported, so the CLI can
    surface "skipped because of X" without raising on the first error.
    """
    disabled = set(disabled_names or [])
    results: List[ExternalPluginResult] = []

    for candidate in list_external_plugin_dirs(plugin_path):
        dir_name = candidate.name
        try:
            definition = _load_external_one(candidate)
        except PluginError as exc:
            results.append(
                ExternalPluginResult(name=dir_name, status="error", error=str(exc))
            )
            continue

        if definition.name in disabled:
            # Roll back the registration we just did; the registry
            # should stay consistent with what's actually enabled.
            unregister_plugin(definition.name)
            results.append(
                ExternalPluginResult(
                    name=definition.name, status="disabled", definition=definition
                )
            )
            continue

        results.append(
            ExternalPluginResult(
                name=definition.name, status="loaded", definition=definition
            )
        )

    return results


# ---------------------------------------------------------------------------
# Git-based plugin installation
# ---------------------------------------------------------------------------
def git_clone(url: str, target_dir: Path) -> None:
    """Clone a git repository into ``target_dir``.

    Uses the system ``git`` binary rather than pulling in GitPython
    for a single CLI call — keeps the dep surface small.

    Raises:
        PluginError: If ``git`` is missing or the clone fails.
    """
    git = shutil.which("git")
    if git is None:
        raise PluginError(
            "git executable not found on PATH; cannot install plugins from git"
        )

    if target_dir.exists():
        raise PluginError(
            f"Target directory already exists: {target_dir}. "
            f"Remove it first (e.g. `mos plugin remove {target_dir.name}`)."
        )

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [git, "clone", "--", url, str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        # Clean up partial clone so the next attempt isn't blocked.
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        stderr = (exc.stderr or "").strip()
        raise PluginError(f"git clone failed: {stderr or exc}") from exc


def derive_plugin_name_from_url(url: str) -> str:
    """Derive a directory / package name from a git URL.

    Examples:
        https://github.com/foo/bar.git         -> ``bar``
        git@github.com:foo/bar.git             -> ``bar``
        https://example.com/plugins/my_plugin/ -> ``my_plugin``
    """
    trimmed = url.rstrip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[: -len(".git")]
    last = trimmed.rsplit("/", 1)[-1]
    if ":" in last:  # git@host:repo style — keep what's after the colon
        last = last.rsplit(":", 1)[-1]
    return last or "plugin"


def install_plugin_from_git(
    url: str, plugin_path: Path, name: Optional[str] = None
) -> Path:
    """Clone ``url`` into ``plugin_path/<name>`` and return the directory.

    Args:
        url: Git URL (https:// or git@).
        plugin_path: Root plugins directory (e.g. ``~/.mos/plugins``).
        name: Override the directory name. Defaults to deriving from
            the URL's last path segment.
    """
    dir_name = name or derive_plugin_name_from_url(url)
    target = plugin_path / dir_name
    git_clone(url, target)
    return target


def is_git_url(source: str) -> bool:
    """Heuristic: does ``source`` look like a git URL rather than a path?

    Recognises the common URL schemes and the SSH ``git@host:path``
    form. Plain paths (``/foo``, ``./foo``, ``~/foo``, ``../foo``)
    return False, even if their final segment contains a ``.git``
    suffix — we'd rather treat a path-shaped string as a path.
    """
    lowered = source.lower()
    if lowered.startswith(("http://", "https://", "git://", "ssh://", "ftp://")):
        return True
    # ``git@host:path`` — colon before any slash and an ``@`` at start.
    if source.startswith(("git@", "ssh@")) and ":" in source:
        return True
    return False


def install_plugin_from_local(
    source: Path,
    plugin_path: Path,
    name: Optional[str] = None,
) -> Path:
    """Copy an already-downloaded plugin directory into ``plugin_path``.

    Use this when the user has the plugin on disk (e.g. extracted a
    tarball, cloned earlier without ``mos plugin install``, or
    written it themselves) and wants it managed under
    ``plugin_path``.

    The source is validated before copy:

      * Must be an existing directory.
      * Must contain ``__init__.py`` (treats it as a Python package).
      * Must not be the same as, or live under, ``plugin_path`` —
        copying onto itself would either no-op or destroy the target
        directory.

    A dry-run import is also performed (``spec_from_file_location``
    + ``exec_module``) so a broken ``describe_plugin`` is reported
    before the copy lands on disk; nothing is registered in the live
    plugin registry during this probe.

    Args:
        source: Path to the plugin's source directory.
        plugin_path: Root plugins directory (e.g. ``~/.mos/plugins``).
        name: Override the destination directory name. Defaults to
            the source directory's basename.
    """
    source = source.expanduser().resolve()
    plugin_path_resolved = plugin_path.expanduser().resolve()

    if not source.exists():
        raise PluginError(f"本地路径不存在: {source}")
    if not source.is_dir():
        raise PluginError(f"不是目录: {source}")
    if not (source / "__init__.py").exists():
        raise PluginError(
            f"本地目录缺少 __init__.py（不是合法插件包）: {source}"
        )

    # Refuse self-copy: either identical paths, or source nested
    # inside the destination root (which would recurse / overlap).
    if source == plugin_path_resolved:
        raise PluginError(
            f"源目录与 plugin_path 相同: {source}"
        )
    if source.is_relative_to(plugin_path_resolved):
        raise PluginError(
            f"源目录位于 plugin_path 内部，无法复制自身: {source}"
        )

    # Dry-run import to catch ``describe_plugin`` errors before
    # touching disk. The module is exec'd but NOT registered — we
    # only need to know whether describe_plugin() returns a valid
    # PluginDefinition.
    spec = importlib.util.spec_from_file_location(
        f"_probe_{source.name}", source / "__init__.py"
    )
    if spec is None or spec.loader is None:
        raise PluginError(f"无法构造 import spec: {source}")
    probe = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(probe)
    except Exception as exc:
        raise PluginError(
            f"插件加载失败（不会复制到 plugin_path）: {exc}"
        ) from exc

    describe = getattr(probe, "describe_plugin", None)
    if not callable(describe):
        raise PluginError(
            f"本地插件缺少 describe_plugin 函数: {source}"
        )
    try:
        definition = describe()
    except Exception as exc:
        raise PluginError(
            f"本地插件 describe_plugin() 调用失败: {exc}"
        ) from exc
    if not isinstance(definition, PluginDefinition):
        raise PluginError(
            f"describe_plugin() 必须返回 PluginDefinition，"
            f"实际为 {type(definition).__name__}: {source}"
        )

    dir_name = name or source.name
    target = plugin_path / dir_name

    if target.exists():
        raise PluginError(
            f"目标目录已存在: {target}。"
            f"若要重新安装，先 `mos plugin remove {dir_name}`。"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)

    return target


def remove_plugin_dir(plugin_path: Path, name: str) -> Path:
    """Delete the plugin directory ``plugin_path/<name>``.

    Refuses to operate outside ``plugin_path`` — protects against
    ``mos plugin remove ..`` style arguments escaping the plugins root.
    """
    target = (plugin_path / name).resolve()
    plugin_path_resolved = plugin_path.resolve()

    # Path.is_relative_to is Python 3.9+; project requires 3.13.
    if not target.is_relative_to(plugin_path_resolved):
        raise PluginError(
            f"Refusing to remove {target}: outside plugin path "
            f"{plugin_path_resolved}"
        )

    if not target.exists():
        raise PluginError(f"Plugin directory does not exist: {target}")

    if not target.is_dir():
        raise PluginError(f"Not a directory: {target}")

    shutil.rmtree(target)
    return target


# ---------------------------------------------------------------------------
# Entry point plugin discovery (pip-installed packages)
# ---------------------------------------------------------------------------
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

        # Mark as EXTERNAL (entry point plugins are treated similarly to
        # external plugins for consistency in the registry)
        definition.source = PluginSource.EXTERNAL
        definition.path = None  # No local path for pip-installed plugins

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
