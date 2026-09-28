import unittest

from hourtracker.stats_window import bar_index, nice_max


class ChartMathTest(unittest.TestCase):
    def test_scale_rounds_up_to_whole_hours(self):
        self.assertEqual(nice_max([]), 3600)
        self.assertEqual(nice_max([0, 0]), 3600)
        self.assertEqual(nice_max([1800, 5400]), 7200)
        self.assertEqual(nice_max([7200]), 7200)

    def test_bar_index(self):
        self.assertEqual(bar_index(0, 700, 7), 0)
        self.assertEqual(bar_index(350, 700, 7), 3)
        self.assertEqual(bar_index(699, 700, 7), 6)
        self.assertIsNone(bar_index(-1, 700, 7))
        self.assertIsNone(bar_index(700, 700, 7))
        self.assertIsNone(bar_index(10, 700, 0))
