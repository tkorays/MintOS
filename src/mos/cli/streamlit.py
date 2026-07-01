"""``mos streamlit`` — 启动 MOS Streamlit 管理界面."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click


@click.command()
@click.option(
    "--port", "-p",
    type=int,
    default=8501,
    help="Streamlit 服务端口（默认 8501）",
)
@click.option(
    "--host",
    type=str,
    default="localhost",
    help="Streamlit 服务地址（默认 localhost）",
)
def streamlit(port: int, host: str) -> None:
    """启动 MOS Streamlit 管理界面。

    此命令启动一个统一的 Streamlit Web 界面，整合所有已注册插件的页面。
    """
    # 获取 MOS web 入口文件路径
    mos_web_path = Path(__file__).parent.parent / "web" / "app.py"

    if not mos_web_path.exists():
        click.echo(f"错误：找不到 MOS web 入口文件 {mos_web_path}", err=True)
        sys.exit(1)

    click.echo("启动 MOS Streamlit 界面...")
    click.echo(f"入口文件: {mos_web_path}")
    click.echo(f"地址: http://{host}:{port}")
    click.echo("按 Ctrl+C 退出")

    # 调用 streamlit run
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(mos_web_path),
                "--server.port",
                str(port),
                "--server.address",
                host,
            ],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        click.echo(f"启动 Streamlit 失败: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n收到 Ctrl+C，正在退出...")
