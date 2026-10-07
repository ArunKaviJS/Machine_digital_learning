"""Animation player (SKILL §20): <pose>.png or numbered <pose>/0001.png frames.

Falls back to an SVG placeholder (client/placeholder_svg.py) when no asset
exists yet, so the client runs before character artwork is ready
(need-to-do.md §E).
"""

from __future__ import annotations

from pathlib import Path

VALID_ANIMATIONS = (
    "idle", "walk", "smile", "wave", "warn", "angry", "happy", "water",
    # extended character-state system (character spec, 2026-10-07):
    "greeting", "thinking", "answering", "confused", "working", "success", "sleep",
)


def resolve_pose_frames(assets_dir: Path, pose: str) -> list[Path]:
    """Return ordered frame file paths for a pose, or [] to use the placeholder."""
    single = assets_dir / f"{pose}.png"
    if single.is_file():
        return [single]
    frame_dir = assets_dir / pose
    if frame_dir.is_dir():
        frames = sorted(p for p in frame_dir.iterdir()
                        if p.suffix.lower() == ".png")
        if frames:
            return frames
    return []


class AnimationPlayer:
    """Caches QPixmaps per pose; advances frames at `fps`. Qt-dependent."""

    def __init__(self, assets_dir: Path, fps: int = 24):
        self.assets_dir = Path(assets_dir)
        self.fps = max(1, fps)
        self.pose = "idle"
        self._frame_index = 0
        self._cache: dict[str, list] = {}

    def set_pose(self, pose: str) -> None:
        if pose not in VALID_ANIMATIONS:
            pose = "idle"
        if pose != self.pose:
            self.pose = pose
            self._frame_index = 0

    def _frames(self, pose: str) -> list:
        if pose not in self._cache:
            from PyQt6.QtGui import QPixmap
            paths = resolve_pose_frames(self.assets_dir, pose)
            self._cache[pose] = [QPixmap(str(p)) for p in paths]
        return self._cache[pose]

    def advance(self) -> None:
        frames = self._frames(self.pose)
        if len(frames) > 1:
            self._frame_index = (self._frame_index + 1) % len(frames)

    def current_pixmap(self):
        """The current QPixmap, or None if this pose has no real artwork yet."""
        frames = self._frames(self.pose)
        if not frames:
            return None
        return frames[self._frame_index % len(frames)]
