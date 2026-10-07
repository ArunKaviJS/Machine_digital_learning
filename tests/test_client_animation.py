"""animation.py: pure pose-frame resolution (SKILL §20). No Qt/QPixmap here."""

from __future__ import annotations

from pathlib import Path

from client.animation import resolve_pose_frames


def test_no_assets_returns_empty_list(tmp_path: Path):
    assert resolve_pose_frames(tmp_path, "idle") == []


def test_single_png_resolves_to_one_frame(tmp_path: Path):
    (tmp_path / "idle.png").write_bytes(b"\x89PNG")
    frames = resolve_pose_frames(tmp_path, "idle")
    assert frames == [tmp_path / "idle.png"]


def test_frame_directory_resolves_sorted(tmp_path: Path):
    frame_dir = tmp_path / "walk"
    frame_dir.mkdir()
    (frame_dir / "0002.png").write_bytes(b"\x89PNG")
    (frame_dir / "0001.png").write_bytes(b"\x89PNG")
    (frame_dir / "notes.txt").write_text("ignore me")
    frames = resolve_pose_frames(tmp_path, "walk")
    assert [p.name for p in frames] == ["0001.png", "0002.png"]


def test_empty_frame_directory_returns_empty_list(tmp_path: Path):
    (tmp_path / "warn").mkdir()
    assert resolve_pose_frames(tmp_path, "warn") == []


def test_single_png_takes_priority_over_directory(tmp_path: Path):
    (tmp_path / "happy.png").write_bytes(b"\x89PNG")
    frame_dir = tmp_path / "happy"
    frame_dir.mkdir()
    (frame_dir / "0001.png").write_bytes(b"\x89PNG")
    frames = resolve_pose_frames(tmp_path, "happy")
    assert frames == [tmp_path / "happy.png"]
