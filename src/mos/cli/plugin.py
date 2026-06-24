"""`mos plugin` — manage plugin enable/disable status.

Subcommands:

  * ``list``    — show all loaded plugins and their status.
  * ``enable``  — re-enable a previously disabled plugin.
  * ``disable`` — mark a plugin as disabled.

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
# plugin group
# ---------------------------------------------------------------------------
@click.group()
def plugin():
    """插件管理：启用 / 禁用 / 列出。"""
    pass


plugin.add_command(list_cmd)
plugin.add_command(enable)
plugin.add_command(disable)
