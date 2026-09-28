import unittest

from hourtracker.floating import clamp_to_workareas

LAPTOP = (67, 32, 1853, 1168)      # the real layout: dock on the left, top bar above,
MONITOR = (1920, 0, 1920, 1080)    # and an external monitor to the right
AREAS = [LAPTOP, MONITOR]


class ClampTest(unittest.TestCase):
    def test_a_visible_spot_is_kept(self):
        self.assertEqual(clamp_to_workareas(500, 400, 100, 50, AREAS), (500, 400))

    def test_behind_the_dock_moves_right(self):
        self.assertEqual(clamp_to_workareas(10, 400, 100, 50, AREAS), (67, 400))

    def test_off_the_right_edge_comes_back(self):
        self.assertEqual(clamp_to_workareas(3900, 100, 100, 50, AREAS), (3740, 100))

    def test_below_the_shorter_monitor_moves_up(self):
        self.assertEqual(clamp_to_workareas(2500, 1150, 100, 50, AREAS), (2500, 1030))

    def test_unplugged_monitor_falls_back_to_the_laptop(self):
        self.assertEqual(clamp_to_workareas(2500, 300, 100, 50, [LAPTOP]), (1820, 300))
