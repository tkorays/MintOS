"""存储后端接口测试"""

import unittest
from datetime import datetime
from mos.core.task.storage.base import TaskRecord, TaskExecutionLog


class TestStorageTypes(unittest.TestCase):

    def test_task_record_creation(self):
        """测试任务记录创建"""
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

        assert record.name == "test.task"
        assert record.trigger_type == "cron"

    def test_execution_log_creation(self):
        """测试执行日志创建"""
        log = TaskExecutionLog(
            id="log-123",
            task_name="test.task",
            started_at=datetime.now(),
            finished_at=None,
            status="running",
            error=None,
            duration=None,
        )

        assert log.task_name == "test.task"
        assert log.status == "running"


if __name__ == "__main__":
    unittest.main()
