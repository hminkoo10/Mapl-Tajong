import sys
import unittest

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer

from app.core import single_instance


@unittest.skipUnless(sys.platform == "win32", "Windows 이름 있는 파이프")
class SecondLaunchTests(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.name = "MaplTajongTest"

    def test_second_launch_asks_running_one_to_show(self):
        shown = []
        server = single_instance.listen(self.name, lambda: shown.append(1))
        self.assertIsNotNone(server)
        try:
            self.assertTrue(single_instance.show_running(self.name))
            loop = QEventLoop()
            QTimer.singleShot(500, loop.quit)
            loop.exec()
            self.assertEqual(shown, [1])
        finally:
            server.close()

    def test_nothing_running(self):
        self.assertFalse(single_instance.show_running(self.name + "-none"))


if __name__ == "__main__":
    unittest.main()


class BuildKeepsNetworkTests(unittest.TestCase):
    def test_build_does_not_prune_qt_network(self):
        from tools import build
        self.assertFalse([p for p in build.PRUNE if "Network" in p])
