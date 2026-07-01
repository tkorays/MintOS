"""统一任务管理器"""

from pathlib import Path
from typing import Optional
from mos.core.task.registry import TaskRegistry
from mos.core.task.scheduler import Scheduler
from mos.core.task.event_bus import EventBus
from mos.core.task.process_manager import ProcessManager
from mos.core.task.storage.file import FileBackend
from mos.core.task.types import TaskDefinition


class TaskManager:
    """统一任务管理器，整合所有任务管理组件"""

    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            storage_dir = Path.home() / ".mos" / "tasks"

        storage_dir.mkdir(parents=True, exist_ok=True)

        self.storage = FileBackend(storage_dir)
        self.registry = TaskRegistry()
        self.scheduler = Scheduler(self.storage, self.registry)
        self.event_bus = EventBus()
        self.process_manager = ProcessManager(
            storage_dir / "daemon.pid",
            storage_dir / "daemon.log"
        )

        self.event_bus.set_registry(self.registry)

    def add_task(self, task: TaskDefinition):
        """添加任务

        Args:
            task: 任务定义
        """
        self.registry.register(task)
        self.scheduler.add_task(task)

    def remove_task(self, name: str):
        """移除任务

        Args:
            name: 任务名称
        """
        self.registry.unregister(name)
        self.scheduler.remove_task(name)

    def start_foreground(self):
        """前台启动"""
        self.scheduler.start()
        # 保持主线程运行，防止程序退出
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.scheduler.stop()

    def stop_foreground(self):
        """停止前台运行"""
        self.scheduler.stop()

    def start_daemon(self):
        """守护进程模式启动"""
        self.process_manager.start(self._daemon_target)

    def stop_daemon(self):
        """停止守护进程"""
        self.process_manager.stop()

    def restart_daemon(self):
        """重启守护进程"""
        self.process_manager.restart(self._daemon_target)

    def get_status(self) -> dict:
        """获取任务管理器状态"""
        daemon_status = self.process_manager.get_status()
        return {
            "running": daemon_status["running"],
            "pid": daemon_status["pid"],
            "uptime": daemon_status.get("uptime", 0),
            "task_count": len(self.registry.list_all()),
        }

    def list_tasks(self) -> list:
        """列出所有任务"""
        return self.registry.list_all()

    def enable_task(self, name: str):
        """启用任务"""
        task = self.registry.get(name)
        if task:
            task.enabled = True

    def disable_task(self, name: str):
        """禁用任务"""
        task = self.registry.get(name)
        if task:
            task.enabled = False

    def run_task_now(self, name: str) -> dict:
        """立即执行任务"""
        task = self.registry.get(name)
        if not task:
            return {"success": False, "error": "Task not found"}

        try:
            task.func()
            return {"success": True, "duration": 0}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _daemon_target(self):
        """守护进程目标函数"""
        self.scheduler.start()
        # 保持运行
        import time
        while True:
            time.sleep(60)


# 全局任务管理器实例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取全局任务管理器"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
