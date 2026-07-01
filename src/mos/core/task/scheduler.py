"""任务调度器"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from mos.core.task.types import TaskDefinition, TaskTriggerType
from mos.core.task.storage.base import StorageBackend, TaskRecord
from datetime import datetime


class Scheduler:
    """基于 APScheduler 的任务调度器"""

    def __init__(self, storage_backend: StorageBackend, registry=None):
        self._scheduler = BackgroundScheduler()
        self._storage = storage_backend
        self._registry = registry
        self._running = False

    def start(self):
        """启动调度器"""
        if not self._running:
            self._load_tasks_from_registry()
            self._load_tasks_from_storage()
            self._scheduler.start()
            self._running = True

    def stop(self):
        """停止调度器"""
        if self._running:
            self._scheduler.shutdown(wait=True)
            self._running = False

    def is_running(self) -> bool:
        """检查调度器是否运行"""
        return self._running

    def add_task(self, task: TaskDefinition):
        """添加任务

        Args:
            task: 任务定义
        """
        if task.trigger_type in (TaskTriggerType.CRON, TaskTriggerType.INTERVAL):
            self._schedule_task(task)

        # 保存到存储
        record = TaskRecord(
            name=task.name,
            trigger_type=task.trigger_type.value,
            trigger_config=task.trigger_config,
            description=task.description,
            enabled=task.enabled,
            max_retries=task.max_retries,
            timeout=task.timeout,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._storage.save_task(record)

    def remove_task(self, name: str):
        """移除任务

        Args:
            name: 任务名称
        """
        try:
            self._scheduler.remove_job(name)
        except Exception:
            pass  # 任务可能不存在

        self._storage.delete_task(name)

    def _schedule_task(self, task: TaskDefinition):
        """调度单个任务

        Args:
            task: 任务定义
        """
        if task.trigger_type == TaskTriggerType.CRON:
            trigger = CronTrigger.from_crontab(task.trigger_config["cron"])
        elif task.trigger_type == TaskTriggerType.INTERVAL:
            trigger = IntervalTrigger(**task.trigger_config)
        else:
            return

        self._scheduler.add_job(
            task.func,
            trigger,
            id=task.name,
            max_instances=1,
        )

    def _load_tasks_from_storage(self):
        """从存储加载任务"""
        records = self._storage.load_all_tasks()
        for record in records:
            # 注意：这里只加载任务定义，不执行
            # 实际的任务函数需要在插件注册时重新绑定
            pass

    def _load_tasks_from_registry(self):
        """从注册表加载任务"""
        if self._registry is None:
            return

        tasks = self._registry.list_all()
        for task in tasks:
            if task.enabled and task.trigger_type in (TaskTriggerType.CRON, TaskTriggerType.INTERVAL):
                self._schedule_task(task)
