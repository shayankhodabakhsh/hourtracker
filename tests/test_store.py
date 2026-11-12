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


class SubjectTest(StoreTest):
    def test_subject_is_kept_when_a_cut_splits_a_session(self):
        session_id = self.store.begin(100, "Bio")
        self.store.extend(session_id, 400)
        self.store.remove_range(200, 300)
        self.assertEqual([row[1:] for row in self.store.sittings_between(0, 1000)],
                         [(100.0, 200.0, "Bio"), (300.0, 400.0, "Bio")])

    def test_update_delete_and_add(self):
        session_id = self.add(100, 200)
        self.store.update(session_id, 120, 180, "Calc")
        other = self.store.add(300, 400, None)
        self.assertEqual(self.store.sittings_between(0, 1000),
                         [(session_id, 120.0, 180.0, "Calc"), (other, 300.0, 400.0, None)])
        self.store.delete(session_id)
        self.assertEqual(self.sessions(), [(300.0, 400.0)])

    def test_subjects_most_recent_first(self):
        self.store.add(100, 200, "Calc")
        self.store.add(300, 400, "Bio")
        self.store.add(500, 600, "")
        self.store.add(700, 800, None)
        self.assertEqual(self.store.subjects(), ["Bio", "Calc"])


class MigrationTest(unittest.TestCase):
    def test_old_database_gets_a_subject_column_and_keeps_its_rows(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hours.db")
            old = sqlite3.connect(path)
            old.executescript("CREATE TABLE sessions (id INTEGER PRIMARY KEY, "
                              "start REAL NOT NULL, end REAL NOT NULL);"
                              "INSERT INTO sessions (start, end) VALUES (100, 200);")
            old.commit()
            old.close()
            for _ in range(2):                   # safe to open twice
                store = Store(path)
                self.assertEqual(store.sittings_between(0, 1000), [(1, 100.0, 200.0, None)])
                store.close()
