import click
from pathlib import Path
import json
from mos.core.config import get_config
from mos.core.logging import get_logger

logger = get_logger(__name__)

# Try to import quant config if plugin is installed
try:
    from mos_quant.core.config import get_quant_config
    QUANT_AVAILABLE = True
except ImportError:
    QUANT_AVAILABLE = False


def _get_mos_dir():
    """获取 MOS 根目录"""
    return Path.home() / ".mos"


def _init_config_file(force=False):
    """初始化配置文件"""
    config_file = _get_mos_dir() / "config.json"

    if config_file.exists():
        if force:
            config_file.unlink()
            click.echo(f"  ⚠ 已删除旧配置文件: {config_file}")
        else:
            click.echo(f"  [OK] 配置文件已存在: {config_file}")
            return False

    config = get_config()
    config_dict = config.model_dump()

    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=2, ensure_ascii=False)

    click.echo(f"  [OK] 已创建配置文件: {config_file}")
    return True


def _init_data_dir():
    """初始化数据目录（使用配置中的 database.path）"""
    if not QUANT_AVAILABLE:
        click.echo("  [SKIP] quant 插件未安装，跳过数据目录初始化")
        return False

    config = get_quant_config()
    data_dir = Path(config.database.get_expanded_path())

    if data_dir.exists():
        click.echo(f"  [OK] 数据目录已存在: {data_dir}")
        return False

    data_dir.mkdir(parents=True, exist_ok=True)

    subdirs = [
        "bars",
        # "sh/bar",
        # "sz/bar",
    ]

    for subdir in subdirs:
        dir_path = data_dir / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        click.echo(f"    - {dir_path}")

    click.echo(f"  [OK] 已创建数据目录: {data_dir}")
    return True


def _init_log_dir():
    """初始化日志目录"""
    log_dir = _get_mos_dir() / "logs"

    if log_dir.exists():
        click.echo(f"  [OK] 日志目录已存在: {log_dir}")
        return False

    log_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"  [OK] 已创建日志目录: {log_dir}")
    return True


def _init_cache_dir():
    """初始化缓存目录"""
    cache_dir = _get_mos_dir() / "cache"

    if cache_dir.exists():
        click.echo(f"  [OK] 缓存目录已存在: {cache_dir}")
        return False

    cache_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"  [OK] 已创建缓存目录: {cache_dir}")
    return True


def _init_plugin_dir():
    """初始化插件目录。

    使用 ``Config.plugin.plugin_path`` 作为根目录；首次安装的
    external 插件（通过 ``mos plugin install``）会被 ``git clone``
    到该目录下。
    """
    config = get_config()
    plugin_dir = Path(config.plugin.get_expanded_path())

    if plugin_dir.exists():
        click.echo(f"  [OK] 插件目录已存在: {plugin_dir}")
        return False

    plugin_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"  [OK] 已创建插件目录: {plugin_dir}")
    return True


@click.command()
@click.option('--force', '-f', is_flag=True, help='强制重新初始化（覆盖现有配置）')
def init(force):
    """初始化 MOS 配置和环境

    首次使用或重新配置时运行此命令。
    将创建必要的配置文件和目录结构。
    """
    click.echo()
    click.echo("=" * 60)
    click.echo("MOS 初始化向导")
    click.echo("=" * 60)
    click.echo()

    mos_dir = _get_mos_dir()
    click.echo(f"MOS 根目录: {mos_dir}")
    click.echo()

    if not mos_dir.exists():
        click.echo("创建 MOS 根目录...")
        mos_dir.mkdir(parents=True, exist_ok=True)
        click.echo(f"  [OK] 已创建: {mos_dir}")
    else:
        click.echo(f"  [OK] MOS 根目录已存在: {mos_dir}")

    click.echo()
    click.echo("初始化配置文件...")
    _init_config_file(force)

    click.echo()
    click.echo("初始化数据目录...")
    _init_data_dir()

    click.echo()
    click.echo("初始化日志目录...")
    _init_log_dir()

    click.echo()
    click.echo("初始化缓存目录...")
    _init_cache_dir()

    click.echo()
    click.echo("初始化插件目录...")
    _init_plugin_dir()

    click.echo()
    click.echo("=" * 60)
    click.echo("[OK] 初始化完成！")
    click.echo("=" * 60)
    click.echo()
    click.echo("接下来你可以：")
    click.echo("  1. 使用 'zq config list' 查看配置")
    click.echo("  2. 使用 'zq config set <key> <value>' 修改配置")
    click.echo("  3. 使用 'zq data instrument-update' 更新证券品种信息")
    click.echo()
    click.echo("更多信息请参考项目文档")
    click.echo()
