"""TidyService tests (SKILL §17) in a temp dir + API/router integration."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from backend.db.connection import Database
from backend.db.migrations import migrate
from backend.db.repositories.tidy_repo import TidyRepo
from backend.router.router import QuestionRouter
from backend.services.tidy_service import TidyError, TidyService

NOW = time.time()
CFG = {"siteMatchers": {"youtube.com": ["YouTube"]},
       "browsers": ["chrome.exe"], "dndApps": []}


@pytest.fixture()
def db():
    database = Database(":memory:")
    migrate(database.raw)
    yield database
    database.close()


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "Downloads"
    r.mkdir()
    return r


@pytest.fixture()
def svc(db, tmp_path: Path, root: Path) -> TidyService:
    return TidyService(db, {}, clock=lambda: NOW,
                       roots={"downloads": root}, home=tmp_path)


def touch(directory: Path, name: str, age: float = 3600.0) -> Path:
    path = directory / name
    path.write_bytes(b"x")
    os.utime(path, (NOW - age, NOW - age))
    return path


def old_mtimes(path: Path) -> None:
    os.utime(path, (NOW - 3600, NOW - 3600))


# ---- propose ----

def test_propose_counts_by_category_and_moves_nothing(svc, root):
    for name in ("a.jpg", "b.mp4", "c.mp3", "d.pdf", "e.zip"):
        touch(root, name)
    touch(root, "notes.xyz")                       # unknown -> stays
    out = svc.propose("downloads")
    assert out["counts"] == {"images": 1, "videos": 1, "audio": 1,
                             "documents": 1, "archives": 1}
    assert out["needs_confirmation"] is True
    assert out["proposal_id"] > 0
    assert "1 image" in out["text"] and "1 archive" in out["text"]
    # side-effect free: everything still at top level
    assert (root / "a.jpg").is_file() and not (root / "images").exists()
    # batch row exists, unconfirmed
    batch = TidyRepo(svc.repo.db).get_batch(out["proposal_id"])
    assert batch["confirmed"] == 0 and batch["folder"] == "downloads"


def test_propose_skips_dirs_hidden_recent_and_temp(svc, root):
    sub = root / "sub"; sub.mkdir()
    touch(sub, "inside.jpg")                       # in a subdir
    touch(root, ".secret.jpg")                     # hidden by name
    (root / "fresh.png").write_bytes(b"x")         # modified now
    touch(root, "dl.crdownload")                   # temp suffix
    touch(root, "ok.png")
    out = svc.propose("downloads")
    assert out["counts"] == {"images": 1}
    assert out["files"] == {"images": ["ok.png"]}


def test_propose_empty_folder_needs_no_confirmation(svc, root):
    out = svc.propose("downloads")
    assert out["proposal_id"] is None
    assert out["needs_confirmation"] is False
    assert "Nothing to sort" in out["text"]


def test_propose_unknown_folder_refused(svc):
    with pytest.raises(TidyError) as e:
        svc.propose("hacks")
    assert e.value.status == 400


def test_propose_outside_home_refused(db, tmp_path: Path):
    outside = tmp_path.parent / "outside_dir"
    outside.mkdir(exist_ok=True)
    svc = TidyService(db, {}, clock=lambda: NOW,
                      roots={"downloads": outside}, home=tmp_path)
    try:
        with pytest.raises(TidyError, match="outside"):
            svc.propose("downloads")
    finally:
        for f in outside.iterdir():
            f.unlink()
        outside.rmdir()


# ---- confirm ----

def test_confirm_moves_files_and_logs_rows(svc, root):
    for name in ("a.jpg", "b.jpg", "c.pdf"):
        touch(root, name)
    pid = svc.propose("downloads")["proposal_id"]
    out = svc.confirm(pid)
    assert out["moved"] == 3 and out["skipped"] == 0
    assert (root / "images" / "a.jpg").is_file()
    assert (root / "images" / "b.jpg").is_file()
    assert (root / "documents" / "c.pdf").is_file()
    assert not (root / "a.jpg").exists()
    moves = svc.repo.moves_of_batch(pid)
    assert len(moves) == 3
    assert svc.repo.get_batch(pid)["confirmed"] == 1


def test_confirm_collision_uses_suffix(svc, root):
    (root / "images").mkdir()
    (root / "images" / "a.jpg").write_bytes(b"old")
    touch(root, "a.jpg")
    pid = svc.propose("downloads")["proposal_id"]
    svc.confirm(pid)
    assert (root / "images" / "a.jpg").read_bytes() == b"old"
    assert (root / "images" / "a (1).jpg").read_bytes() == b"x"


def test_confirm_skips_vanished_files(svc, root):
    touch(root, "gone.jpg")
    touch(root, "stays.jpg")
    pid = svc.propose("downloads")["proposal_id"]
    (root / "gone.jpg").unlink()
    out = svc.confirm(pid)
    assert out["moved"] == 1 and out["skipped"] == 1
    assert "vanished" in out["text"]


def test_confirm_unknown_or_double_errors(svc, root):
    touch(root, "a.jpg")
    pid = svc.propose("downloads")["proposal_id"]
    with pytest.raises(TidyError) as e:
        svc.confirm(999)
    assert e.value.status == 400
    svc.confirm(pid)
    with pytest.raises(TidyError) as e:
        svc.confirm(pid)
    assert e.value.status == 409


# ---- undo ----

def test_undo_restores_everything(svc, root):
    for name in ("a.jpg", "b.pdf"):
        touch(root, name)
    pid = svc.propose("downloads")["proposal_id"]
    svc.confirm(pid)
    out = svc.undo()
    assert out["restored"] == 2
    assert (root / "a.jpg").is_file() and (root / "b.pdf").is_file()
    assert not (root / "images").joinpath("a.jpg").exists()
    assert svc.repo.get_batch(pid)["undone"] == 1
    assert all(m["undone"] == 1 for m in svc.repo.moves_of_batch(pid))
    # second undo: nothing left
    out2 = svc.undo()
    assert out2["batch_id"] is None
    assert out2["needs_confirmation"] is False
    assert "Nothing to undo" in out2["text"]


def test_undo_collision_keeps_new_name(svc, root):
    touch(root, "a.jpg")
    pid = svc.propose("downloads")["proposal_id"]
    svc.confirm(pid)
    touch(root, "a.jpg")                      # something else took the name
    out = svc.undo()
    assert out["restored"] == 1
    assert (root / "a.jpg").read_bytes() == b"x"          # original restored
    assert (root / "a (1).jpg").read_bytes() == b"x"      # moved copy parked


# ---- router integration ----

def test_router_propose_then_yes_confirms(db, root):
    touch(root, "a.jpg")
    touch(root, "b.mp4")
    svc = TidyService(db, CFG, clock=lambda: NOW,
                      roots={"downloads": root}, home=root.parent)
    router = QuestionRouter(db, CFG, tidy_service=svc)
    first = router.ask("organize my downloads")
    assert first["needs_confirmation"] is True
    assert "1 image" in first["text"]
    second = router.ask("yes")
    assert second["needs_confirmation"] is False
    assert "Moved 2 files" in second["text"]
    assert (root / "images" / "a.jpg").is_file()
    assert (root / "videos" / "b.mp4").is_file()


def test_router_undo_text(db, root):
    svc = TidyService(db, CFG, clock=lambda: NOW,
                      roots={"downloads": root}, home=root.parent)
    router = QuestionRouter(db, CFG, tidy_service=svc)
    out = router.ask("undo that")
    assert "Nothing to undo" in out["text"]


# ---- API ----

def test_api_unknown_folder_400(client):
    r = client.post("/tidy/propose", json={"folder": "hacks"})
    assert r.status_code == 400
    assert "Unknown folder" in r.json()["detail"]


def test_api_undo_empty_200(client):
    r = client.post("/tidy/undo")
    assert r.status_code == 200
    assert "Nothing to undo" in r.json()["text"]


def test_api_full_flow(client, tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    for name in ("a.jpg", "b.pdf"):
        path = root / name
        path.write_bytes(b"x")
        os.utime(path, (NOW - 3600, NOW - 3600))
    client.app.state.tidy_service = TidyService(
        client.app.state.db, {}, roots={"downloads": root}, home=tmp_path)

    r = client.post("/tidy/propose", json={"folder": "downloads"})
    assert r.status_code == 200
    body = r.json()
    assert body["needs_confirmation"] is True
    pid = body["proposal_id"]

    r = client.post("/tidy/confirm", json={"proposal_id": pid})
    assert r.status_code == 200
    assert r.json()["moved"] == 2
    assert (root / "images" / "a.jpg").is_file()

    r = client.post("/tidy/confirm", json={"proposal_id": pid})
    assert r.status_code == 409

    r = client.post("/tidy/undo")
    assert r.status_code == 200
    assert r.json()["restored"] == 2
    assert (root / "a.jpg").is_file()

    r = client.post("/tidy/confirm", json={"proposal_id": 12345})
    assert r.status_code == 400
