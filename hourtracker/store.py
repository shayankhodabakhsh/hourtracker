"""SQLite storage for study sessions: (start, end) pairs in Unix seconds,
each with an optional subject."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id    INTEGER PRIMARY KEY,
    start REAL NOT NULL,
    end   REAL NOT NULL,
    subject TEXT
);
CREATE INDEX IF NOT EXISTS sessions_start ON sessions (start);
"""


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.executescript(SCHEMA)
        columns = [row[1] for row in self._db.execute("PRAGMA table_info(sessions)")]
        if "subject" not in columns:          # databases from before subjects
            with self._db:
                self._db.execute("ALTER TABLE sessions ADD COLUMN subject TEXT")

    def close(self) -> None:
        self._db.close()

    def begin(self, ts: float, subject: str | None = None) -> int:
        """Record a new session starting (and, for now, ending) at ts."""
        return self.add(ts, ts, subject)

    def add(self, start: float, end: float, subject: str | None = None) -> int:
        with self._db:
            return self._db.execute(
                "INSERT INTO sessions (start, end, subject) VALUES (?, ?, ?)",
                (start, end, subject)).lastrowid

    def update(self, session_id: int, start: float, end: float,
               subject: str | None) -> None:
        with self._db:
            self._db.execute("UPDATE sessions SET start = ?, end = ?, subject = ? "
                             "WHERE id = ?", (start, end, subject, session_id))

    def set_subject(self, session_id: int, subject: str | None) -> None:
        with self._db:
            self._db.execute("UPDATE sessions SET subject = ? WHERE id = ?",
                             (subject, session_id))

    def delete(self, session_id: int) -> None:
        with self._db:
            self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

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
                "SELECT id, start, end, subject FROM sessions WHERE start < ? AND end > ?",
                (b, a)).fetchall()
            for session_id, start, end, subject in rows:
                if a <= start and end <= b:
                    self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                elif start < a and b < end:
                    self._db.execute("UPDATE sessions SET end = ? WHERE id = ?",
                                     (a, session_id))
                    self._db.execute(
                        "INSERT INTO sessions (start, end, subject) VALUES (?, ?, ?)",
                        (b, end, subject))
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

    def sittings_between(self, a: float, b: float) -> list[tuple]:
        """(id, start, end, subject) of every session overlapping [a, b)."""
        return self._db.execute(
            "SELECT id, start, end, subject FROM sessions WHERE start < ? AND end > ? "
            "ORDER BY start", (b, a)).fetchall()

    def subjects(self, limit: int = 8) -> list[str]:
        """Subjects used before, most recently used first."""
        return [row[0] for row in self._db.execute(
            "SELECT subject FROM sessions WHERE subject IS NOT NULL AND subject != '' "
            "GROUP BY subject ORDER BY max(start) DESC LIMIT ?", (limit,))]
