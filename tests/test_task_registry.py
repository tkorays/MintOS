"""任务注册表测试"""

import unittest
from mos.core.task.registry import TaskRegistry
from mos.core.task.types import TaskDefinition, TaskTriggerType


class TestTaskRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = TaskRegistry()

    def test_register_task(self):
        """测试注册任务"""
        task = TaskDefinition(
            name="test.task",
            func=lambda: None,
            trigger_type=TaskTriggerType.CRON,
            trigger_config={"cron": "0 9 * * *"},
        )

        self.registry.register(task)
        assert self.registry.get("test.task") == task

    def test_register_duplicate_task(self):
        """测试重复注册任务"""
        task1 = TaskDefinition(
            name="test.task",
            func=lambda: None,
            trigger_type=TaskTriggerType.CRON,
            trigger_config={"cron": "0 9 * * *"},
        )

        self.registry.register(task1)

        task2 = TaskDefinition(
            name="test.task",
            func=lambda: None,
            trigger_type=TaskTriggerType.INTERVAL,
            trigger_config={"minutes": 5},
        )

        with self.assertRaises(ValueError):
            self.registry.register(task2)

    def test_unregister_task(self):
        """测试取消注册任务"""
        task = TaskDefinition(
            name="test.task",
            func=lambda: None,
            trigger_type=TaskTriggerType.CRON,
            trigger_config={"cron": "0 9 * * *"},
        )

        self.registry.register(task)
        removed = self.registry.unregister("test.task")

        assert removed == task
        assert self.registry.get("test.task") is None

    def test_list_all_tasks(self):
        """测试列出所有任务"""
        task1 = TaskDefinition(
            name="test.task1",
            func=lambda: None,
            trigger_type=TaskTriggerType.CRON,
            trigger_config={"cron": "0 9 * * *"},
        )
        task2 = TaskDefinition(
            name="test.task2",
            func=lambda: None,
            trigger_type=TaskTriggerType.INTERVAL,
            trigger_config={"minutes": 5},
        )

        self.registry.register(task1)
        self.registry.register(task2)

        tasks = self.registry.list_all()
        assert len(tasks) == 2
        assert task1 in tasks
        assert task2 in tasks

    def test_list_by_trigger_type(self):
        """测试按触发类型列出任务"""
        task1 = TaskDefinition(
            name="test.task1",
            func=lambda: None,
            trigger_type=TaskTriggerType.CRON,
            trigger_config={"cron": "0 9 * * *"},
        )
        task2 = TaskDefinition(
            name="test.task2",
            func=lambda: None,
            trigger_type=TaskTriggerType.INTERVAL,
            trigger_config={"minutes": 5},
        )

        self.registry.register(task1)
        self.registry.register(task2)

        cron_tasks = self.registry.list_by_trigger_type(TaskTriggerType.CRON)
        assert len(cron_tasks) == 1
        assert task1 in cron_tasks


if __name__ == "__main__":
    unittest.main()
