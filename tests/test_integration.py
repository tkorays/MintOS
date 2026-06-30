"""集成测试"""

import unittest
from mos.core.task import get_task_manager


class TestIntegration(unittest.TestCase):

    def test_task_manager_singleton(self):
        """测试任务管理器单例"""
        manager1 = get_task_manager()
        manager2 = get_task_manager()

        assert manager1 == manager2


if __name__ == "__main__":
    unittest.main()
