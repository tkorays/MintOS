"""插件任务集成测试"""

import unittest
from mos.core.plugin import PluginDefinition
from mos.core.task.types import TaskDefinition, TaskTriggerType
from mos.core.task.registry import TaskRegistry
from mos.core.task.event_bus import EventBus


class TestPluginTaskIntegration(unittest.TestCase):

    def setUp(self):
        self.registry = TaskRegistry()
        self.event_bus = EventBus()

    def test_plugin_with_register_tasks(self):
        """测试带任务注册的插件"""
        def dummy_register_tasks(registry, event_bus):
            task = TaskDefinition(
                name="plugin.task",
                func=lambda: None,
                trigger_type=TaskTriggerType.INTERVAL,
                trigger_config={"minutes": 5},
            )
            registry.register(task)

        import click
        plugin_def = PluginDefinition(
            name="test_plugin",
            command=click.Group(),
            register_tasks=dummy_register_tasks,
        )

        # 模拟插件加载时调用 register_tasks
        if plugin_def.register_tasks:
            plugin_def.register_tasks(self.registry, self.event_bus)

        assert self.registry.get("plugin.task") is not None


if __name__ == "__main__":
    unittest.main()
