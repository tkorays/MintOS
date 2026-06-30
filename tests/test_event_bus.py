"""事件总线测试"""

import unittest
from mos.core.task.event_bus import EventBus
from mos.core.task.registry import TaskRegistry
from mos.core.task.types import TaskDefinition, TaskTriggerType


class TestEventBus(unittest.TestCase):

    def setUp(self):
        self.registry = TaskRegistry()
        self.event_bus = EventBus()
        self.event_bus.set_registry(self.registry)
        self.executed_tasks = []

    def _create_task_func(self, task_name):
        def func(event_data=None):
            self.executed_tasks.append((task_name, event_data))
        return func

    def test_subscribe_and_publish(self):
        """测试订阅和发布事件"""
        task = TaskDefinition(
            name="test.task",
            func=self._create_task_func("test.task"),
            trigger_type=TaskTriggerType.EVENT,
            trigger_config={"event_type": "test_event"},
        )

        self.registry.register(task)
        self.event_bus.subscribe("test_event", "test.task")

        self.event_bus.publish("test_event", {"data": "test"})

        assert len(self.executed_tasks) == 1
        assert self.executed_tasks[0] == ("test.task", {"data": "test"})

    def test_unsubscribe(self):
        """测试取消订阅"""
        task = TaskDefinition(
            name="test.task",
            func=self._create_task_func("test.task"),
            trigger_type=TaskTriggerType.EVENT,
            trigger_config={"event_type": "test_event"},
        )

        self.registry.register(task)
        self.event_bus.subscribe("test_event", "test.task")
        self.event_bus.unsubscribe("test_event", "test.task")

        self.event_bus.publish("test_event", {"data": "test"})

        assert len(self.executed_tasks) == 0

    def test_disabled_task_not_executed(self):
        """测试禁用的任务不会执行"""
        task = TaskDefinition(
            name="test.task",
            func=self._create_task_func("test.task"),
            trigger_type=TaskTriggerType.EVENT,
            trigger_config={"event_type": "test_event"},
            enabled=False,
        )

        self.registry.register(task)
        self.event_bus.subscribe("test_event", "test.task")

        self.event_bus.publish("test_event", {"data": "test"})

        assert len(self.executed_tasks) == 0


if __name__ == "__main__":
    unittest.main()
