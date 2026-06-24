import click

from mos.core.logging import setup_logging
from mos.core.config import get_config
from mos.core.plugin import load_entry_point_plugins
from mos.cli.config import config
from mos.cli.init import init
from mos.cli.plugin import plugin as plugin_cmd
from mos.cli.mcp import mcp


@click.group()
@click.version_option(package_name="mos-core")
def cli():
    setup_logging()


cli.add_command(config)
cli.add_command(init)
cli.add_command(plugin_cmd)
cli.add_command(mcp)


cfg = get_config()
disabled_plugins = list(cfg.plugin.disabled_plugins)

# Load all plugins via entry_points (pip-installed packages)
ep_results = load_entry_point_plugins(disabled_plugins)
for r in ep_results:
    if r.status == "loaded" and r.definition is not None:
        cmd = r.definition.command
        if cmd.name and cmd.name not in cli.commands:
            cli.add_command(cmd)
        if r.name != cmd.name and r.name not in cli.commands:
            cli.add_command(cmd, name=r.name)
        # Register MCP tools if plugin supports it
        if r.definition.register_mcp:
            from mos.core.mcp import mcp
            r.definition.register_mcp(mcp)


if __name__ == "__main__":
    cli()
