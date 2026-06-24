import json
from typing import Any, Callable

import click
from pydantic import ValidationError

from mos.core.config import get_config
from mos.core.plugin import get_registry
from mos.core.logging import get_logger

logger = get_logger(__name__)


@click.group()
def config():
    """配置管理命令"""
    pass


def _get_config_func(config_type: str) -> Callable:
    """根据配置类型获取对应的配置管理函数

    Args:
        config_type: 配置类型，'main' 表示主配置，其他为插件名称

    Returns:
        get_config_func: 配置获取函数，支持 reload 参数
    """
    if config_type == "main":
        return get_config

    registry = get_registry()
    get_func = registry.get_config_func(config_type)

    if get_func is None:
        raise click.ClickException(f"未知的配置类型: '{config_type}'。可用类型: main, {', '.join(registry.list_names())}")

    return get_func


def _format_value(value):
    """格式化配置值为可读字符串"""
    value_type = type(value)

    if value_type is bool:
        return "true" if value else "false"
    elif value_type in (list, tuple):
        return ", ".join(str(item) for item in value)
    else:
        return str(value)


def _print_config_tree(data, prefix=""):
    """递归打印配置树"""
    data_type = type(data)

    if data_type is not dict:
        click.echo(f"{prefix}{data}")
        return

    for key, value in data.items():
        value_type = type(value)

        if value is None:
            click.echo(f"{prefix}{key}: null")
        elif value_type is dict:
            click.echo(f"{prefix}{key}:")
            _print_config_tree(value, prefix + "  ")
        else:
            display_value = _format_value(value)
            click.echo(f"{prefix}{key}: {display_value}")


def _coerce_cli_value(value: str) -> Any:
    """根据 CLI 字符串字面量推断 Python 标量（true/false/int/float/JSON/str）。"""
    if value.startswith("~"):
        return value
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        if value.startswith("[") or value.startswith("{"):
            return json.loads(value)
        return value


@click.command()
@click.option('--type', 'config_type', default='main', help='配置类型：main(主配置) 或插件名称(如 quant, wiki)')
def list(config_type: str):
    """列出所有配置项

    示例:
      mos config list                    # 列出主配置
      mos config list --type quant       # 列出 quant 插件配置
      mos config list --type wiki        # 列出 wiki 插件配置
    """
    try:
        get_config_func = _get_config_func(config_type)
        config_obj = get_config_func()
        config_dict = config_obj.model_dump()
        config_file = config_obj.config_file_path

        click.echo(f"当前配置 ({config_type}):\n")
        click.echo(f"配置文件: {config_file}")
        click.echo(f"配置文件存在: {config_file.exists()}")
        click.echo()

        _print_config_tree(config_dict)

        click.echo()
        click.echo("提示: 使用 'mos config set <key> <value> --type <type>' 修改配置")

    except Exception as e:
        logger.error(f"列出配置失败: {e}")
        raise click.ClickException(f"列出配置失败: {e}")


@click.command()
@click.argument("key")
@click.argument("value")
@click.option('--type', 'config_type', default='main', help='配置类型：main(主配置) 或插件名称(如 quant, wiki)')
def set(key, value, config_type: str):
    """设置配置项

    示例:
      mos config set log.level DEBUG
      mos config set debug true --type main
      mos config set database.path ~/.mos/custom_data/ --type quant
      mos config set mini_qmt.path D:\\QMT --type quant
    """
    try:
        get_config_func = _get_config_func(config_type)
        keys = key.split(".")
        if not keys or not all(keys):
            raise click.ClickException(f"无效的 key: {key!r}")

        # 用当前 Config 作为基线，把 CLI 改的字段 deep-merge 进去。
        # pydantic 在 model_validate 阶段会做类型转换（str→int/bool/...）。
        current = get_config_func()
        override: dict[str, Any] = {}
        cursor: dict[str, Any] = override
        for k in keys[:-1]:
            cursor[k] = {}
            cursor = cursor[k]
        cursor[keys[-1]] = _coerce_cli_value(value)

        try:
            new_cfg = current.update(**override)
        except ValidationError as e:
            raise click.ClickException(f"配置项 {key!r} 校验失败: {e}")

        target = new_cfg.save()
        get_config_func(reload=True)

        click.echo(f"[OK] 已设置 {config_type}.{key} = {value}")
        click.echo(f"  配置文件: {target}")
        click.echo()
        click.echo("提示: 某些配置可能需要重启应用才能生效")

    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"设置配置失败: {e}")
        raise click.ClickException(f"设置配置失败: {e}")


@click.command()
@click.argument("key")
@click.option('--type', 'config_type', default='main', help='配置类型：main(主配置) 或插件名称(如 quant, wiki)')
def get(key, config_type: str):
    """获取指定配置项的值

    示例:
      mos config get log.level
      mos config get debug --type main
      mos config get database.path --type quant
    """
    try:
        get_config_func = _get_config_func(config_type)
        config_obj = get_config_func()
        value = config_obj.get(*key.split("."))

        if value is None:
            click.echo(f"配置项 '{config_type}.{key}' 不存在")
            return

        click.echo(f"{config_type}.{key} = {value}")

    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        raise click.ClickException(f"获取配置失败: {e}")


@click.command()
@click.option('--type', 'config_type', default='main', help='配置类型：main(主配置) 或插件名称(如 quant, wiki)')
def types(config_type: str):
    """列出所有可用的配置类型"""
    registry = get_registry()
    plugin_names = registry.list_names()

    click.echo("可用的配置类型:")
    click.echo("  main - MOS 主配置 (log, llm, debug)")
    for name in plugin_names:
        click.echo(f"  {name} - {name} 插件配置")

    click.echo()
    click.echo("示例:")
    click.echo("  mos config list --type main")
    click.echo("  mos config list --type quant")


config.add_command(list)
config.add_command(set)
config.add_command(get)
config.add_command(types)
