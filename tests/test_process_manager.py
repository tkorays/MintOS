"""进程管理器测试"""

import unittest
import time
import tempfile
import shutil
from pathlib import Path
from mos.core.task.process_manager import ProcessManager


class TestProcessManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pid_file = Path(self.temp_dir) / "daemon.pid"
        self.log_file = Path(self.temp_dir) / "daemon.log"
        self.manager = ProcessManager(self.pid_file, self.log_file)

    def tearDown(self):
        if self.manager.is_running():
            self.manager.stop()
        shutil.rmtree(self.temp_dir)

    def _simple_target(self):
        """简单的目标函数"""
        time.sleep(2)

    def test_start_and_stop(self):
        """测试启动和停止"""
        self.manager.start(self._simple_target)

        assert self.manager.is_running()
        assert self.pid_file.exists()

        self.manager.stop()

        assert not self.manager.is_running()

    def test_get_status(self):
        """测试获取状态"""
        self.manager.start(self._simple_target)

        status = self.manager.get_status()

        assert status["running"] is True
        assert status["pid"] is not None

        self.manager.stop()

    def test_double_start_error(self):
        """测试重复启动报错"""
        self.manager.start(self._simple_target)

        with self.assertRaises(RuntimeError):
            self.manager.start(self._simple_target)

        self.manager.stop()


if __name__ == "__main__":
    unittest.main()
