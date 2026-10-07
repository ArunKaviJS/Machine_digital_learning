"""tidy_batches / tidy_moves repository (propose -> confirm -> undo)."""

from __future__ import annotations

import sqlite3

from backend.db.connection import Database


class TidyRepo:
    def __init__(self, db: Database):
        self.db = db

    def create_batch(self, folder: str, created_at: str, confirmed: bool = False) -> int:
        cur = self.db.execute(
            "INSERT INTO tidy_batches(folder, created_at, confirmed) VALUES(?,?,?)",
            (folder, created_at, 1 if confirmed else 0),
        )
        return int(cur.lastrowid or 0)

    def confirm_batch(self, batch_id: int) -> None:
        self.db.execute(
            "UPDATE tidy_batches SET confirmed = 1 WHERE id = ?", (batch_id,)
        )

    def add_move(self, batch_id: int, original_path: str, new_path: str, moved_at: str) -> int:
        cur = self.db.execute(
            "INSERT INTO tidy_moves(batch_id, original_path, new_path, moved_at)"
            " VALUES(?,?,?,?)",
            (batch_id, original_path, new_path, moved_at),
        )
        return int(cur.lastrowid or 0)

    def get_batch(self, batch_id: int) -> sqlite3.Row | None:
        return self.db.query_one("SELECT * FROM tidy_batches WHERE id = ?", (batch_id,))

    def moves_of_batch(self, batch_id: int) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT * FROM tidy_moves WHERE batch_id = ? ORDER BY id", (batch_id,)
        )

    def last_undoable_batch(self) -> sqlite3.Row | None:
        """Latest confirmed batch that has not been undone."""
        return self.db.query_one(
            "SELECT * FROM tidy_batches WHERE confirmed = 1 AND undone = 0"
            " ORDER BY id DESC LIMIT 1"
        )

    def mark_undone(self, batch_id: int) -> None:
        with self.db.transaction():
            self.db.execute(
                "UPDATE tidy_batches SET undone = 1 WHERE id = ?", (batch_id,)
            )
            self.db.execute(
                "UPDATE tidy_moves SET undone = 1 WHERE batch_id = ?", (batch_id,)
            )
