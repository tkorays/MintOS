"""`mos plugin` — manage plugin enable/disable status.

Subcommands:

  * ``list``    — show all loaded plugins and their status.
  * ``enable``  — re-enable a previously disabled plugin.
  * ``disable`` — mark a plugin as disabled.
  * ``create``  — scaffold a minimal Python plugin project in CWD.

Status semantics for ``list``:
    ``loaded``    — registered with :func:`mos.core.plugin.get_registry`.
    ``disabled``  — present in ``Config.disabled_plugins`.

Persistence:
    All mutations go through :meth:`BaseConfig.update` +
    :meth:`BaseConfig.save` (see :mod:`mos.core.baseconfig`), so the
    changes are atomic and survive process exit. ``get_config(reload=True)``
    is called after each save so the in-memory config stays in sync.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import click

from mos.core.config import get_config
from mos.core.logging import get_logger
from mos.core.plugin import get_registry, unregister_plugin

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
@click.command(name="list")
def list_cmd():
    """列出已加载的插件。

    输出所有通过 entry_points 加载的插件及其状态和版本。
    """
    cfg = get_config()
    disabled = set(cfg.plugin.disabled_plugins)

    click.echo(f"disabled_plugins: {', '.join(sorted(disabled)) if disabled else '(none)'}")
    click.echo()

    registry = get_registry()
    loaded_plugins = registry.all()

    if loaded_plugins:
        click.echo("PLUGINS:")
        click.echo(f"  {'NAME':<20} {'VERSION':<10} {'STATUS':<12}")
        click.echo(f"  {'-'*20} {'-'*10} {'-'*12}")
        for plugin in sorted(loaded_plugins, key=lambda p: p.name):
            status = "disabled" if plugin.name in disabled else "loaded"
            version = plugin.version or "unknown"
            click.echo(f"  {plugin.name:<20} {version:<10} {status:<12}")
        click.echo()
    else:
        click.echo("(no plugins loaded)")


# ---------------------------------------------------------------------------
# enable
# ---------------------------------------------------------------------------
@click.command()
@click.argument("name")
def enable(name: str):
    """启用一个之前被禁用的插件。

    从 ``disabled_plugins`` 中移除 ``NAME``。插件会在下次启动时
    自动重新加载。
    """
    cfg = get_config()
    disabled = list(cfg.plugin.disabled_plugins)

    if name not in disabled:
        click.echo(f"[OK] 插件 `{name}` 未被禁用，无需操作")
        return

    new_disabled = [n for n in disabled if n != name]
    new_cfg = cfg.update(plugin={"disabled_plugins": new_disabled})
    new_cfg.save()
    get_config(reload=True)
    click.echo(f"[OK] 已从 disabled_plugins 移除 `{name}`")


# ---------------------------------------------------------------------------
# disable
# ---------------------------------------------------------------------------
@click.command()
@click.argument("name")
def disable(name: str):
    """禁用插件。

    把 ``NAME`` 加入 ``disabled_plugins``，并立刻从当前会话的注册
    表中反注册。下次启动时也不会再加载它。
    """
    cfg = get_config()
    disabled = list(cfg.plugin.disabled_plugins)

    if name in disabled:
        click.echo(f"[OK] 插件 `{name}` 已被禁用，无需操作")
    else:
        disabled.append(name)
        new_cfg = cfg.update(plugin={"disabled_plugins": disabled})
        new_cfg.save()
        get_config(reload=True)
        click.echo(f"[OK] 已将 `{name}` 加入 disabled_plugins")

    # Unload immediately for the current session
    removed = unregister_plugin(name)
    if removed is not None:
        click.echo(f"[OK] 插件 `{name}` 已从当前会话反注册")


# ---------------------------------------------------------------------------
# create — scaffold a new plugin
# ---------------------------------------------------------------------------
# Naming convention: the project directory and the Python package both
# default to ``mos_<entry>`` (entry being the ``mos <entry>`` subcommand
# the plugin registers). The entry point key in pyproject.toml is just
# ``<entry>``. Validation is intentionally lenient — we only reject
# values that Python's import system or Click's command group would
# reject at runtime.
_VALID_PKG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_package_name(name: str) -> str:
    """Validate a Python package name.

    Raises ``click.BadParameter`` with a Chinese message so the error
    stays consistent with the rest of the CLI.
    """
    candidate = name.strip()
    if not candidate:
        raise click.BadParameter("包名不能为空")
    if not _VALID_PKG_RE.match(candidate):
        raise click.BadParameter(
            f"包名 `{candidate}` 非法：必须以小写字母开头，"
            "仅包含小写字母、数字和下划线"
        )
    return candidate


def _validate_entry_name(name: str) -> str:
    """Validate a Click command-group name."""
    candidate = name.strip()
    if not candidate:
        raise click.BadParameter("命令名不能为空")
    if not _VALID_PKG_RE.match(candidate):
        raise click.BadParameter(
            f"命令名 `{candidate}` 非法：必须以小写字母开头，"
            "仅包含小写字母、数字和下划线"
        )
    return candidate


# Template fragments. Kept inline (rather than in a templates/ dir) so a
# fresh checkout can scaffold a plugin without first installing mos —
# the command's only real dependency is click, which mos already pulls
# in. Strings use ``str.format`` with ``{{`` / ``}}`` escapes for any
# literal braces the target file needs (e.g. the TOML inline table).

_PYPROJECT_TMPL = '''[project]
name = "{pkg}"
version = "{version}"
description = "{description}"
readme = "README.md"
requires-python = ">=3.13"
authors = [
    {{name = "{author}"}},
]

# 插件依赖：声明对主程序的依赖
dependencies = [
    "mos>=0.1.0",
    "click>=8.4.1",
]

# 关键：声明 entry_point，MOS 通过此发现插件
[project.entry-points."mos.plugins"]
{entry} = "{pkg}:describe_plugin"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "ruff",
]
'''

_README_TMPL = '''# {pkg}

{description}

## 安装

```bash
pip install -e .
```

## 使用

插件安装后，MOS 会自动发现并注册 `{entry}` 子命令：

```bash
mos {entry} --help
```

## 开发

本插件独立于主仓库开发。
'''

_GITIGNORE_TMPL = '''# Python-generated files
__pycache__/
*.py[oc]
build/
dist/
wheels/
*.egg-info

# Virtual environments
.venv
venv/
.env

# IDE
.idea/
.vscode/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/

# Linting
.ruff_cache/

# OS
.DS_Store
Thumbs.db

# Logs
logs/
*.log
'''

_INIT_TMPL = '''"""{pkg} - {description}"""

__version__ = "{version}"

from mos.core.plugin import PluginDefinition


def describe_plugin() -> PluginDefinition:
    """Declare the {entry} module as an entry_point plugin."""
    from {pkg}.cli import {entry}
    from {pkg}.core.config import get_config

    return PluginDefinition(
        name="{entry}",
        command={entry},
        get_config=get_config,
    )
'''

_CLI_INIT_TMPL = '''"""{pkg} CLI commands."""

import click


@click.group()
@click.version_option()
def {entry}():
    """{description}"""
    pass
'''

_CORE_CONFIG_TMPL = '''"""{pkg} configuration.

Plugin-scoped config. Lives in its own file (``~/.mos/{entry}.json`` by
default) so this plugin's settings stay independent of the main app
config and of any sibling plugin.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import Field

from mos.core.baseconfig import BaseConfig


DEFAULT_{entry_upper}_CONFIG_PATH: Path = Path.home() / ".mos" / "{entry}.json"


class {cls}Config(BaseConfig):
    """Plugin config — add your own fields here."""

    config_file_path: ClassVar[Path] = DEFAULT_{entry_upper}_CONFIG_PATH

    # Example field; replace with whatever your plugin needs.
    enabled: bool = Field(default=True)


_{entry}_config: "{cls}Config | None" = None


def get_config(reload: bool = False) -> "{cls}Config":
    """Get or create the global plugin config instance."""
    global _{entry}_config
    if reload or _{entry}_config is None:
        _{entry}_config = {cls}Config.load()
    return _{entry}_config
'''

_CORE_INIT_TMPL = '''"""{pkg} core package."""
'''


def _render_template(tmpl: str, **kwargs: str) -> str:
    """Render a template that uses ``{{`` / ``}}`` for literal braces.

    ``str.format`` would treat bare ``{{...}}`` as placeholders too; we
    convert the doubled braces to sentinels, format, then restore.
    """
    safe = tmpl.replace("{{", "\x00").replace("}}", "\x01")
    rendered = safe.format(**kwargs)
    return rendered.replace("\x00", "{").replace("\x01", "}")


def _write_file(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` using UTF-8, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _scaffold_plugin(
    target_dir: Path,
    pkg: str,
    entry: str,
    version: str,
    description: str,
    author: str,
) -> list[Path]:
    """Materialize the plugin tree under ``target_dir``.

    Returns the list of files written, in deterministic order, so the
    caller can show the user what was created and the tests can assert
    on the exact set.
    """
    cls = entry.capitalize()
    pkg_root = target_dir
    src_root = pkg_root / "src" / pkg
    ctx = {
        "pkg": pkg,
        "entry": entry,
        "version": version,
        "description": description,
        "author": author,
        "cls": cls,
        "entry_upper": entry.upper(),
    }

    files: list[tuple[Path, str]] = [
        (pkg_root / "pyproject.toml", _PYPROJECT_TMPL),
        (pkg_root / "README.md", _README_TMPL),
        (pkg_root / ".gitignore", _GITIGNORE_TMPL),
        (src_root / "__init__.py", _INIT_TMPL),
        (src_root / "cli" / "__init__.py", _CLI_INIT_TMPL),
        (src_root / "core" / "__init__.py", _CORE_INIT_TMPL),
        (src_root / "core" / "config.py", _CORE_CONFIG_TMPL),
    ]

    written: list[Path] = []
    for path, tmpl in files:
        _write_file(path, _render_template(tmpl, **ctx))
        written.append(path)
        # Use f-string rather than positional ``%s`` so the project's
        # loguru console_format (which renders ``{message}``) gets the
        # final string rather than the format spec.
        logger.info(f"created {path}")
    return written


def _gather_inputs(
    directory: Optional[str],
    entry_name: Optional[str],
    version: str,
    description: Optional[str],
    author: Optional[str],
    interactive: bool,
) -> tuple[str, str, str, str, str, str]:
    """Resolve all user inputs into a final tuple of strings.

    Centralised so the same code path serves both interactive
    (``click.prompt``) and non-interactive (``--non-interactive``) use.
    """
    # 1. Entry point name — the `mos <name>` subcommand.
    if entry_name is None:
        if interactive:
            entry_name = click.prompt(
                "entry_point 名（即 `mos <name>` 中的 name，例如 demo）",
                default="myplugin",
            )
        else:
            entry_name = "myplugin"
    entry_name = _validate_entry_name(entry_name)

    # 2. Project directory.
    if directory is None:
        default_dir = f"mos_{entry_name}"
        if interactive:
            directory = click.prompt("插件目录名", default=default_dir)
        else:
            directory = default_dir
    directory = directory.strip()
    if not directory:
        raise click.BadParameter("目录名不能为空")

    # 3. Python package name — defaults to the directory name so the
    # generated package matches the existing ``mos_<entry>`` convention
    # when the user accepts the default directory.
    if interactive:
        pkg_name = click.prompt(
            "Python 包名（src/ 下的目录）", default=directory
        )
    else:
        pkg_name = directory
    pkg_name = _validate_package_name(pkg_name)

    # 4. Version / description / author.
    if interactive:
        version = click.prompt("初始版本号", default=version)
        description = click.prompt("插件描述", default="") or ""
        author = click.prompt("作者", default="") or ""
    else:
        description = description or f"{entry_name} plugin for MOS"
        author = author or ""

    return directory, pkg_name, entry_name, version, description, author


@click.command()
@click.option(
    "--dir",
    "directory",
    default=None,
    help="插件目录名（默认 ./mos_<entry>）。在当前目录下创建。",
)
@click.option(
    "--name",
    "entry_name",
    default=None,
    help="entry_point 名（即 `mos <name>` 中的 name）。",
)
@click.option(
    "--version",
    "version",
    default="0.1.0",
    show_default=True,
    help="初始版本号。",
)
@click.option("--description", "description", default=None, help="插件描述。")
@click.option("--author", "author", default=None, help="作者姓名。")
@click.option(
    "--force/--no-force",
    default=False,
    help="目标目录已存在时仍继续（会向其中写入文件）。",
)
@click.option(
    "--non-interactive",
    is_flag=True,
    help="使用默认值 / 命令行提供的值，不进行交互式提问。",
)
def create(
    directory: Optional[str],
    entry_name: Optional[str],
    version: str,
    description: Optional[str],
    author: Optional[str],
    force: bool,
    non_interactive: bool,
):
    """交互式创建一个 mos 插件工程。

    在当前目录下生成一个新的 Python 包，包含 ``pyproject.toml``、
    ``src/<pkg>/__init__.py``、``cli/``、``core/config.py`` 等基础
    文件，可立即 ``pip install -e .`` 后被主程序识别。
    """
    interactive = not non_interactive and sys.stdin.isatty()

    if interactive:
        click.echo("将创建一个新的 mos 插件工程。按 Ctrl+C 随时取消。")
        click.echo()

    directory, pkg_name, entry_name, version, description, author = _gather_inputs(
        directory=directory,
        entry_name=entry_name,
        version=version,
        description=description,
        author=author,
        interactive=interactive,
    )

    target_dir = Path(directory).resolve()
    if target_dir.exists():
        if not force and any(target_dir.iterdir()):
            raise click.BadParameter(
                f"目标目录 `{target_dir}` 已存在且非空；"
                "使用 --force 覆盖，或换一个目录名"
            )
        # Empty existing dir is fine without --force.
    else:
        target_dir.mkdir(parents=True, exist_ok=True)

    if interactive:
        click.echo()
        click.echo("即将创建：")
        click.echo(f"  目录      : {target_dir}")
        click.echo(f"  Python 包 : {pkg_name}")
        click.echo(f"  命令      : mos {entry_name}")
        click.echo(f"  版本      : {version}")
        click.echo(f"  描述      : {description or '(empty)'}")
        click.echo(f"  作者      : {author or '(empty)'}")
        click.echo()
        if not click.confirm("确认创建？", default=True):
            click.echo("已取消。")
            raise click.Abort()

    written = _scaffold_plugin(
        target_dir=target_dir,
        pkg=pkg_name,
        entry=entry_name,
        version=version,
        description=description,
        author=author,
    )

    click.echo()
    click.echo(f"[OK] 已在 {target_dir} 创建插件 `{entry_name}`：")
    for path in written:
        try:
            rel = path.relative_to(Path.cwd())
        except ValueError:
            rel = path
        click.echo(f"  - {rel}")
    click.echo()
    click.echo("接下来可以：")
    click.echo(f"  cd {target_dir.name if target_dir.parent == Path.cwd() else target_dir}")
    click.echo("  pip install -e .")
    click.echo(f"  mos {entry_name} --help")


# ---------------------------------------------------------------------------
# plugin group
# ---------------------------------------------------------------------------
@click.group()
def plugin():
    """插件管理：启用 / 禁用 / 列出 / 创建。"""
    pass


plugin.add_command(list_cmd)
plugin.add_command(enable)
plugin.add_command(disable)
plugin.add_command(create)
