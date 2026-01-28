import click
from mos.core.logging import get_logger

logger = get_logger(__name__)

@click.command()
def mcp():
    """
    MCP命令
    """
    from mos.core.mcp import mcp
    logger.info("MCP server running...")
    mcp.run(transport="streamable-http")
