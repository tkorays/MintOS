"""任务管理器测试"""

import unittest
import tempfile
import shutil
from pathlib import Path
from mos.core.task.manager import TaskManager, get_task_manager
from mos.core.task.types import TaskDefinition, TaskTriggerType


class TestTaskManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_task_manager_creation(self):
        """测试任务管理器创建"""
        manager = TaskManager(Path(self.temp_dir))

        assert manager.registry is not None
        assert manager.scheduler is not None
        assert manager.event_bus is not None

    def test_add_task(self):
        """测试添加任务"""
        manager = TaskManager(Path(self.temp_dir))

        task = TaskDefinition(
            name="test.task",
            func=lambda: None,
            trigger_type=TaskTriggerType.INTERVAL,
            trigger_config={"seconds": 60},
        )

        manager.add_task(task)

        loaded = manager.registry.get("test.task")
        assert loaded == task

    def test_global_task_manager(self):
        """测试全局任务管理器"""
        manager = get_task_manager()

        assert manager is not None


if __name__ == "__main__":
    unittest.main()
