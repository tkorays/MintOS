"""任务类型测试"""

import unittest
from mos.core.task.types import TaskDefinition, TaskTriggerType


class TestTaskTypes(unittest.TestCase):

    def test_task_trigger_type_enum(self):
        """测试触发类型枚举"""
        assert TaskTriggerType.CRON.value == "cron"
        assert TaskTriggerType.INTERVAL.value == "interval"
        assert TaskTriggerType.EVENT.value == "event"

    def test_task_definition_creation(self):
        """测试任务定义创建"""
        def dummy_func():
            pass

        task = TaskDefinition(
            name="test.task",
            func=dummy_func,
            trigger_type=TaskTriggerType.CRON,
            trigger_config={"cron": "0 9 * * 1-5"},
            description="测试任务",
        )

        assert task.name == "test.task"
        assert task.trigger_type == TaskTriggerType.CRON
        assert task.enabled is True

    def test_task_definition_with_interval(self):
        """测试间隔任务定义"""
        def dummy_func():
            pass

        task = TaskDefinition(
            name="test.interval",
            func=dummy_func,
            trigger_type=TaskTriggerType.INTERVAL,
            trigger_config={"minutes": 5},
        )

        assert task.trigger_type == TaskTriggerType.INTERVAL
        assert task.trigger_config["minutes"] == 5


if __name__ == "__main__":
    unittest.main()
