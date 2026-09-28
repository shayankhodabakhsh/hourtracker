import os
import tempfile
import unittest

from hourtracker.store import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def add(self, start, end):
        session_id = self.store.begin(start)
        self.store.extend(session_id, end)
        return session_id

    def sessions(self):
        return self.store.sessions_between(0, 1000)

    def test_begin_and_extend(self):
        self.add(100, 200)
        self.assertEqual(self.sessions(), [(100.0, 200.0)])

    def test_extend_never_moves_backward(self):
        session_id = self.add(100, 200)
        self.store.extend(session_id, 150)
        self.assertEqual(self.sessions(), [(100.0, 200.0)])

    def test_sessions_between_only_returns_overlaps(self):
        self.add(100, 200)
        self.add(300, 400)
        self.assertEqual(self.store.sessions_between(150, 300), [(100.0, 200.0)])

    def test_remove_range_inside_splits_the_session(self):
        self.add(100, 400)
        self.store.remove_range(200, 300)
        self.assertEqual(self.sessions(), [(100.0, 200.0), (300.0, 400.0)])

    def test_remove_range_covering_a_session_deletes_it(self):
        self.add(100, 200)
        self.store.remove_range(50, 250)
        self.assertEqual(self.sessions(), [])

    def test_remove_range_clips_the_end(self):
        self.add(100, 300)
        self.store.remove_range(200, 400)
        self.assertEqual(self.sessions(), [(100.0, 200.0)])

    def test_remove_range_clips_the_start(self):
        self.add(100, 300)
        self.store.remove_range(0, 200)
        self.assertEqual(self.sessions(), [(200.0, 300.0)])

    def test_remove_range_touches_several_sessions(self):
        self.add(100, 200)
        self.add(300, 400)
        self.store.remove_range(150, 350)
        self.assertEqual(self.sessions(), [(100.0, 150.0), (350.0, 400.0)])

    def test_remove_range_without_overlap_changes_nothing(self):
        self.add(100, 200)
        self.store.remove_range(300, 400)
        self.store.remove_range(250, 250)
        self.assertEqual(self.sessions(), [(100.0, 200.0)])


class PersistenceTest(unittest.TestCase):
    def test_sessions_survive_reopening(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "hours.db")
            store = Store(path)
            store.extend(store.begin(100), 200)
            store.close()
            reopened = Store(path)
            self.assertEqual(reopened.sessions_between(0, 1000), [(100.0, 200.0)])
            reopened.close()
