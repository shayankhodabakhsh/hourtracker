"""SQLite storage for study sessions: (start, end) pairs in Unix seconds."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id    INTEGER PRIMARY KEY,
    start REAL NOT NULL,
    end   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_start ON sessions (start);
"""


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def begin(self, ts: float) -> int:
        """Record a new session starting (and, for now, ending) at ts."""
        with self._db:
            return self._db.execute(
                "INSERT INTO sessions (start, end) VALUES (?, ?)", (ts, ts)).lastrowid

    def extend(self, session_id: int, ts: float) -> None:
        """Move a session's end forward to ts. It never moves backward."""
        with self._db:
            self._db.execute("UPDATE sessions SET end = max(end, ?) WHERE id = ?",
                             (ts, session_id))

    def remove_range(self, a: float, b: float) -> None:
        """Cut the time between a and b out of every session, splitting a
        session in two when the cut falls in its middle."""
        if b <= a:
            return
        with self._db:
            rows = self._db.execute(
                "SELECT id, start, end FROM sessions WHERE start < ? AND end > ?",
                (b, a)).fetchall()
            for session_id, start, end in rows:
                if a <= start and end <= b:
                    self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                elif start < a and b < end:
                    self._db.execute("UPDATE sessions SET end = ? WHERE id = ?",
                                     (a, session_id))
                    self._db.execute("INSERT INTO sessions (start, end) VALUES (?, ?)",
                                     (b, end))
                elif start < a:
                    self._db.execute("UPDATE sessions SET end = ? WHERE id = ?",
                                     (a, session_id))
                else:
                    self._db.execute("UPDATE sessions SET start = ? WHERE id = ?",
                                     (b, session_id))

    def sessions_between(self, a: float, b: float) -> list[tuple[float, float]]:
        """(start, end) of every session overlapping [a, b), oldest first."""
        return self._db.execute(
            "SELECT start, end FROM sessions WHERE start < ? AND end > ? ORDER BY start",
            (b, a)).fetchall()
