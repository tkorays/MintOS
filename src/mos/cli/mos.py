import click

from mos.core.logging import setup_logging
from mos.core.config import get_config
from mos.core.plugin import load_entry_point_plugins
from mos.cli.config import config
from mos.cli.init import init
from mos.cli.plugin import plugin as plugin_cmd
from mos.cli.mcp import mcp
from mos.cli.task import task


@click.group()
@click.version_option(package_name="mos-core")
def cli():
    # Windows 上 multiprocessing 需要 freeze_support
    import multiprocessing
    multiprocessing.freeze_support()
    setup_logging()


cli.add_command(config)
cli.add_command(init)
cli.add_command(plugin_cmd)
cli.add_command(mcp)
cli.add_command(task)


cfg = get_config()
disabled_plugins = list(cfg.plugin.disabled_plugins)

# Load all plugins via entry_points (pip-installed packages)
ep_results = load_entry_point_plugins(disabled_plugins)
for r in ep_results:
    if r.status == "loaded" and r.definition is not None:
        cmd = r.definition.command
        # 只使用 Click 命令对象的名称注册，不使用 entry_point 名称
        # 避免因 Click 自动转换 _ 为 - 导致重复注册
        if cmd.name and cmd.name not in cli.commands:
            cli.add_command(cmd)
        # Register MCP tools if plugin supports it
        if r.definition.register_mcp:
            from mos.core.mcp import mcp
            r.definition.register_mcp(mcp)
        # Register background tasks if plugin supports it
        if r.definition.register_tasks:
            from mos.core.task import get_task_manager
            task_manager = get_task_manager()
            r.definition.register_tasks(task_manager.registry, task_manager.event_bus)


if __name__ == "__main__":
    # Windows 上 multiprocessing 需要 freeze_support
    import multiprocessing
    multiprocessing.freeze_support()
    cli()
