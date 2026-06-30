"""文件存储后端测试"""

import unittest
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from mos.core.task.storage.file import FileBackend
from mos.core.task.storage.base import TaskRecord, TaskExecutionLog


class TestFileBackend(unittest.TestCase):

    def setUp(self):
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp()
        self.backend = FileBackend(Path(self.temp_dir))

    def tearDown(self):
        # 清理临时目录
        shutil.rmtree(self.temp_dir)

    def test_save_and_load_task(self):
        """测试保存和加载任务"""
        record = TaskRecord(
            name="test.task",
            trigger_type="cron",
            trigger_config={"cron": "0 9 * * *"},
            description="测试任务",
            enabled=True,
            max_retries=0,
            timeout=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        self.backend.save_task(record)
        loaded = self.backend.load_task("test.task")

        assert loaded is not None
        assert loaded.name == record.name
        assert loaded.trigger_type == record.trigger_type

    def test_load_all_tasks(self):
        """测试加载所有任务"""
        record1 = TaskRecord(
            name="test.task1",
            trigger_type="cron",
            trigger_config={"cron": "0 9 * * *"},
            description="测试任务1",
            enabled=True,
            max_retries=0,
            timeout=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        record2 = TaskRecord(
            name="test.task2",
            trigger_type="interval",
            trigger_config={"minutes": 5},
            description="测试任务2",
            enabled=True,
            max_retries=0,
            timeout=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        self.backend.save_task(record1)
        self.backend.save_task(record2)

        tasks = self.backend.load_all_tasks()
        assert len(tasks) == 2

    def test_delete_task(self):
        """测试删除任务"""
        record = TaskRecord(
            name="test.task",
            trigger_type="cron",
            trigger_config={"cron": "0 9 * * *"},
            description="测试任务",
            enabled=True,
            max_retries=0,
            timeout=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        self.backend.save_task(record)
        self.backend.delete_task("test.task")

        loaded = self.backend.load_task("test.task")
        assert loaded is None

    def test_save_and_load_execution_log(self):
        """测试保存和加载执行日志"""
        log = TaskExecutionLog(
            id="log-123",
            task_name="test.task",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            status="success",
            error=None,
            duration=1.5,
        )

        self.backend.save_execution_log(log)
        logs = self.backend.load_execution_logs(task_name="test.task")

        assert len(logs) >= 1
        assert logs[0].task_name == "test.task"

    def test_daemon_status(self):
        """测试守护进程状态"""
        status = {"running": True, "pid": 12345}

        self.backend.save_daemon_status(status)
        loaded = self.backend.load_daemon_status()

        assert loaded is not None
        assert loaded["running"] is True
        assert loaded["pid"] == 12345


if __name__ == "__main__":
    unittest.main()
