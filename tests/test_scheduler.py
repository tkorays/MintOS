"""调度器测试"""

import unittest
import tempfile
import shutil
from pathlib import Path
from mos.core.task.scheduler import Scheduler
from mos.core.task.storage.file import FileBackend
from mos.core.task.types import TaskDefinition, TaskTriggerType


class TestScheduler(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = FileBackend(Path(self.temp_dir))
        self.scheduler = Scheduler(self.storage)
        self.executed_count = 0

    def tearDown(self):
        if self.scheduler.is_running():
            self.scheduler.stop()
        shutil.rmtree(self.temp_dir)

    def _increment_func(self):
        """增加计数"""
        self.executed_count += 1

    def test_start_and_stop(self):
        """测试启动和停止"""
        self.scheduler.start()

        assert self.scheduler.is_running()

        self.scheduler.stop()

        assert not self.scheduler.is_running()

    def test_add_interval_task(self):
        """测试添加间隔任务"""
        task = TaskDefinition(
            name="test.interval",
            func=self._increment_func,
            trigger_type=TaskTriggerType.INTERVAL,
            trigger_config={"seconds": 1},
        )

        self.scheduler.start()
        self.scheduler.add_task(task)

        # 验证任务已注册
        loaded = self.storage.load_task("test.interval")
        assert loaded is not None
        assert loaded.name == "test.interval"

        self.scheduler.stop()


if __name__ == "__main__":
    unittest.main()
