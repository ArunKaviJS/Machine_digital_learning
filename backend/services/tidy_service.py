"""Folder tidy service (SKILL §17): propose (counts only) -> confirm -> undo.

Never deletes. Only top level of the folder. Categories by extension.
Safety: folder keys whitelisted, roots must resolve inside the home folder.
"""

from __future__ import annotations

import datetime
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from backend.config import TIDY_FOLDER_KEYS
from backend.db.connection import Database
from backend.db.repositories.tidy_repo import TidyRepo

logger = logging.getLogger("arun.tidy")

FILE_ATTRIBUTE_HIDDEN = 0x2
RECENT_SECONDS = 60.0
TEMP_SUFFIXES = {".crdownload", ".part", ".tmp"}

DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "images":    [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
    "videos":    [".mp4", ".mkv", ".avi", ".mov", ".webm"],
    "audio":     [".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"],
    "documents": [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
                  ".ppt", ".pptx", ".csv"],
    "archives":  [".zip", ".rar", ".7z", ".tar", ".gz"],
}
CATEGORY_ORDER = ("images", "videos", "audio", "documents", "archives")
LABELS = {"images": "image", "videos": "video", "audio": "audio file",
          "documents": "document", "archives": "archive"}
_HOME_NAMES = {"downloads": "Downloads", "desktop": "Desktop",
               "documents": "Documents", "pictures": "Pictures",
               "videos": "Videos"}


class TidyError(Exception):
    """User-facing tidy failure. status = HTTP code for the API layer."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class TidyService:
    def __init__(self, db: Database, config: dict[str, Any],
                 clock: Callable[[], float] = time.time,
                 roots: dict[str, Path] | None = None,
                 home: Path | None = None):
        self.repo = TidyRepo(db)
        self.config = config
        self.clock = clock
        self.home = Path(home) if home else Path.home()
        if roots is None:
            roots = {}
            for key, name in _HOME_NAMES.items():
                p = self.home / name
                if not p.is_dir() and (self.home / "OneDrive" / name).is_dir():
                    p = self.home / "OneDrive" / name
                roots[key] = p
        self.roots = {k: Path(v) for k, v in roots.items()}
        self._proposals: dict[int, dict[str, Any]] = {}
        self._ext_to_cat = self._build_categories(config)

    # -- config ----------------------------------------------------------
    @staticmethod
    def _build_categories(config: dict[str, Any]) -> dict[str, str]:
        raw = config.get("tidyCategories") or DEFAULT_CATEGORIES
        mapping: dict[str, str] = {}
        for cat in CATEGORY_ORDER:
            for ext in raw.get(cat, DEFAULT_CATEGORIES[cat]):
                ext = ext if ext.startswith(".") else f".{ext}"
                mapping[ext.lower()] = cat
        return mapping

    def _now_iso(self) -> str:
        return datetime.datetime.fromtimestamp(self.clock()) \
            .astimezone().isoformat(timespec="seconds")

    def _root(self, folder_key: str) -> Path:
        if folder_key not in TIDY_FOLDER_KEYS:
            raise TidyError(
                f"Unknown folder '{folder_key}'. "
                f"Allowed: {', '.join(sorted(TIDY_FOLDER_KEYS))}.")
        root = self.roots.get(folder_key)
        if root is None:
            raise TidyError(f"Folder '{folder_key}' is not available here.")
        try:
            resolved = root.resolve()
            home = self.home.resolve()
        except OSError as exc:
            raise TidyError(f"Cannot access {folder_key}: {exc}") from exc
        if not resolved.is_relative_to(home):
            raise TidyError(
                "Refusing to touch files outside your user folder.")
        if not resolved.is_dir():
            raise TidyError(f"The {folder_key} folder was not found.", 404)
        return resolved

    # -- scanning --------------------------------------------------------
    @staticmethod
    def _is_hidden(path: Path, stat: os.stat_result) -> bool:
        if path.name.startswith("."):
            return True
        return bool(getattr(stat, "st_file_attributes", 0)
                    & FILE_ATTRIBUTE_HIDDEN)

    def _scan(self, root: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
        counts: dict[str, int] = {}
        files: dict[str, list[str]] = {}
        now = self.clock()
        for entry in sorted(root.iterdir()):
            try:
                if not entry.is_file():
                    continue
                st = entry.stat()
            except OSError:
                continue
            if self._is_hidden(entry, st):
                continue
            if now - st.st_mtime < RECENT_SECONDS:
                continue
            if entry.suffix.lower() in TEMP_SUFFIXES:
                continue
            cat = self._ext_to_cat.get(entry.suffix.lower())
            if cat is None:          # everything else stays (SKILL §17)
                continue
            counts[cat] = counts.get(cat, 0) + 1
            files.setdefault(cat, []).append(entry.name)
        return counts, files

    # -- text ------------------------------------------------------------
    @staticmethod
    def _found_text(counts: dict[str, int], folder: str) -> str:
        parts = []
        for cat in CATEGORY_ORDER:
            n = counts.get(cat, 0)
            if n:
                label = LABELS[cat]
                parts.append(f"{n} {label}" + ("" if n == 1 else "s"))
        joined = (", ".join(parts[:-1]) + " and " + parts[-1]
                  if len(parts) > 1 else parts[0])
        return (f"Found {joined} in {folder.capitalize()}. "
                f"Move them into subfolders?")

    @staticmethod
    def _unique_path(target: Path) -> Path:
        if not target.exists():
            return target
        stem, suffix = target.stem, target.suffix
        n = 1
        while True:
            candidate = target.with_name(f"{stem} ({n}){suffix}")
            if not candidate.exists():
                return candidate
            n += 1

    # -- API -------------------------------------------------------------
    def propose(self, folder_key: str) -> dict[str, Any]:
        """Count sortable files. Nothing moves."""
        root = self._root(folder_key)
        counts, files = self._scan(root)
        folder_name = folder_key.capitalize()
        if not counts:
            return {"folder": folder_key, "proposal_id": None,
                    "counts": {}, "files": {},
                    "text": f"Nothing to sort in {folder_name}, bro.",
                    "animation": "idle", "needs_confirmation": False}
        batch_id = self.repo.create_batch(folder_key, self._now_iso())
        self._proposals[batch_id] = {"folder": folder_key, "files": files}
        return {"folder": folder_key, "proposal_id": batch_id,
                "counts": counts, "files": files,
                "text": self._found_text(counts, folder_name),
                "animation": "idle", "needs_confirmation": True}

    def confirm(self, proposal_id: Any) -> dict[str, Any]:
        """Move the proposed files into category subfolders."""
        try:
            pid = int(proposal_id)
        except (TypeError, ValueError) as exc:
            raise TidyError("That proposal does not exist.") from exc
        batch = self.repo.get_batch(pid)
        if batch is None:
            raise TidyError("That proposal does not exist.")
        if batch["confirmed"]:
            raise TidyError("That folder was already tidied.", 409)
        stored = self._proposals.get(pid)
        if stored is None:
            raise TidyError(
                "That proposal expired — propose again.", 409)
        root = self._root(stored["folder"])
        moved = skipped = 0
        for cat in CATEGORY_ORDER:
            for name in stored["files"].get(cat, []):
                src = root / name
                if not src.is_file():
                    skipped += 1
                    continue
                dest_dir = root / cat.capitalize()
                dest_dir.mkdir(exist_ok=True)
                target = self._unique_path(dest_dir / name)
                shutil.move(str(src), str(target))
                self.repo.add_move(pid, str(src), str(target),
                                   self._now_iso())
                moved += 1
        self.repo.confirm_batch(pid)
        self._proposals.pop(pid, None)
        logger.info("tidy confirmed batch=%s moved=%s skipped=%s",
                    pid, moved, skipped)
        text = f"Done, bro. Moved {moved} file" + ("" if moved == 1 else "s") \
            + " into subfolders."
        if skipped:
            text += f" Skipped {skipped} that vanished."
        return {"folder": stored["folder"], "moved": moved,
                "skipped": skipped, "text": text, "animation": "happy",
                "needs_confirmation": False}

    def undo(self) -> dict[str, Any]:
        """Reverse the latest confirmed, non-undone batch."""
        batch = self.repo.last_undoable_batch()
        if batch is None:
            return {"batch_id": None, "restored": 0,
                    "text": "Nothing to undo, bro.",
                    "animation": "idle", "needs_confirmation": False}
        restored = 0
        for move in self.repo.moves_of_batch(batch["id"]):
            src = Path(move["new_path"])
            dst = Path(move["original_path"])
            if not src.is_file():
                continue
            target = dst if not dst.exists() else self._unique_path(dst)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
            restored += 1
        self.repo.mark_undone(batch["id"])
        logger.info("tidy undone batch=%s restored=%s",
                    batch["id"], restored)
        return {"batch_id": batch["id"], "restored": restored,
                "text": f"Done, bro. Restored {restored} file"
                        + ("" if restored == 1 else "s") + ".",
                "animation": "happy", "needs_confirmation": False}
