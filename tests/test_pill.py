import unittest

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk  # noqa: E402

from hourtracker.tracker import Away  # noqa: E402


@unittest.skipIf(Gdk.Display.get_default() is None, "needs a display")
class PillAnswerTest(unittest.TestCase):
    def setUp(self):
        from hourtracker.pill import PillWindow
        self.answers = []
        self.pill = PillWindow({"pill_pos": None}, on_toggle=lambda: None,
                               on_open_stats=lambda: None,
                               on_answer=lambda kind, yes: self.answers.append((kind, yes)),
                               menu_factory=lambda: None)
        self.addCleanup(self.pill.destroy)

    def test_answer_goes_to_the_open_question(self):
        self.pill.update(True, 0, away=Away(0, 900))
        self.pill._yes.clicked()
        self.assertEqual(self.answers, [("away", True)])

    def test_clicks_with_no_open_question_are_ignored(self):
        self.pill.update(False, 0)
        self.pill._no.clicked()
        self.assertEqual(self.answers, [])

    def test_pill_knows_its_real_size_before_it_is_shown(self):
        width, height = self.pill.get_size()
        self.assertLess(width, 120)
        self.assertLess(height, 40)

    def test_pill_shrinks_back_after_a_question(self):
        small = self.pill.get_size()
        self.pill.update(True, 0, away=Away(0, 900))
        self.assertGreater(self.pill.get_size()[0], small[0])
        self.pill.update(True, 0)
        self.assertEqual(self.pill.get_size(), small)
