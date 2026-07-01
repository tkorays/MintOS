"""进程管理器"""

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional, Dict, Any


class ProcessManager:
    """守护进程管理器（使用 subprocess）"""

    def __init__(self, pid_file: Path, log_file: Path):
        self.pid_file = pid_file
        self.log_file = log_file
        self._process: Optional[subprocess.Popen] = None

    def start(self, target: Callable, args=()):
        """启动守护进程

        Args:
            target: 目标函数（会被忽略，使用独立的启动脚本）
            args: 函数参数（会被忽略）

        Raises:
            RuntimeError: 如果进程已运行
        """
        if self.is_running():
            raise RuntimeError("Daemon process is already running")

        # 使用 subprocess 启动独立的进程
        # 构造启动命令：python -m mos.core.task.daemon_launcher
        python_exe = sys.executable

        # 创建日志文件
        log_dir = self.log_file.parent
        log_dir.mkdir(parents=True, exist_ok=True)

        # Windows 上使用 CREATE_NO_WINDOW 标志创建无窗口进程
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        self._process = subprocess.Popen(
            [python_exe, "-m", "mos.core.task.daemon_launcher"],
            stdout=open(self.log_file, "w"),
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True,
        )

        self._save_pid()

    def stop(self):
        """停止守护进程"""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

        self._process = None

        # 通过 PID 文件查找并停止进程
        if self.pid_file.exists():
            try:
                with open(self.pid_file, "r") as f:
                    pid = int(f.read().strip())

                import psutil
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except psutil.TimeoutExpired:
                        proc.kill()

            except (ValueError, psutil.NoSuchProcess):
                pass

            self.pid_file.unlink()

    def restart(self, target: Callable, args=()):
        """重启守护进程

        Args:
            target: 目标函数
            args: 函数参数
        """
        self.stop()
        self.start(target, args)

    def is_running(self) -> bool:
        """检查守护进程是否在运行"""
        # 首先检查内存中的进程对象
        if self._process is not None and self._process.poll() is None:
            return True

        # 如果进程对象不存在，检查 PID 文件
        if self.pid_file.exists():
            try:
                with open(self.pid_file, "r") as f:
                    pid = int(f.read().strip())

                # 检查进程是否存在
                import psutil
                return psutil.pid_exists(pid)
            except (ValueError, FileNotFoundError):
                return False

        return False

    def get_status(self) -> Dict[str, Any]:
        """获取守护进程状态

        Returns:
            状态字典，包含 running、pid、uptime 等
        """
        running = self.is_running()
        pid = None

        if running:
            if self._process:
                pid = self._process.pid
            elif self.pid_file.exists():
                try:
                    with open(self.pid_file, "r") as f:
                        pid = int(f.read().strip())
                except ValueError:
                    pass

        return {
            "running": running,
            "pid": pid,
            "uptime": 0,  # TODO: 计算实际运行时间
        }

    def _save_pid(self):
        """保存 PID 到文件"""
        if self._process:
            with open(self.pid_file, "w") as f:
                f.write(str(self._process.pid))
