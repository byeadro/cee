"""Tests for persistence/atomic.py — the only sanctioned writer in CEE."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from persistence.atomic import atomic_write_json, atomic_write_text


# ─── Basic correctness ──────────────────────────────────────────────────


def test_atomic_write_text_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_text_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    atomic_write_text(target, "first")
    atomic_write_text(target, "second")
    assert target.read_text(encoding="utf-8") == "second"


def test_atomic_write_json_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    payload = {"a": 1, "b": [2, 3]}
    atomic_write_json(target, payload)
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_atomic_write_json_sorts_keys(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    atomic_write_json(target, {"b": 2, "a": 1})
    rendered = target.read_text(encoding="utf-8")
    assert rendered.index('"a"') < rendered.index('"b"')


def test_atomic_write_json_indents(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    atomic_write_json(target, {"outer": {"inner": 1}})
    rendered = target.read_text(encoding="utf-8")
    # 2-space indent puts the inner key on its own line, leading-spaced.
    assert "\n  " in rendered
    assert "\n    " in rendered  # nested level indent


# ─── Atomicity ──────────────────────────────────────────────────────────


def test_atomic_write_text_failure_during_write_leaves_target_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "f.txt"
    target.write_text("old")

    def boom(fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(os, "fsync", boom)

    with pytest.raises(OSError, match="simulated fsync failure"):
        atomic_write_text(target, "new")

    # Target preserved.
    assert target.read_text() == "old"
    # No temp leakage in the directory.
    contents = sorted(p.name for p in tmp_path.iterdir())
    assert contents == ["f.txt"]


def test_atomic_write_json_rejects_nan(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    with pytest.raises(ValueError):
        atomic_write_json(target, {"x": float("nan")})
    with pytest.raises(ValueError):
        atomic_write_json(target, {"x": float("inf")})
    with pytest.raises(ValueError):
        atomic_write_json(target, {"x": float("-inf")})
    # No temp file or target should have been created.
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_temp_file_in_same_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "subdir" / "f.txt"
    target.parent.mkdir()

    captured: dict[str, object] = {}
    real_ntf = tempfile.NamedTemporaryFile

    def recording_ntf(*args: object, **kwargs: object) -> object:
        captured["dir"] = kwargs.get("dir")
        return real_ntf(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", recording_ntf)
    atomic_write_text(target, "x")

    assert captured["dir"] is not None
    assert Path(captured["dir"]) == target.parent  # type: ignore[arg-type]


def test_no_partial_files_left_in_directory_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "f.txt"

    def boom_replace(*args: object, **kwargs: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_text(target, "x")

    # Directory must be empty — no .tmp leakage, no target created.
    assert list(tmp_path.iterdir()) == []


# ─── Permissions ────────────────────────────────────────────────────────


def test_mode_applied_when_specified(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX chmod semantics not meaningful on Windows")
    target = tmp_path / "secret.txt"
    atomic_write_text(target, "x", mode=0o600)
    assert (target.stat().st_mode & 0o777) == 0o600


def test_mode_preserved_when_target_exists_and_no_mode_given(
    tmp_path: Path,
) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX chmod semantics not meaningful on Windows")
    target = tmp_path / "f.txt"
    target.write_text("old")
    target.chmod(0o644)
    atomic_write_text(target, "new")
    assert (target.stat().st_mode & 0o777) == 0o644


def test_mode_default_when_target_new_and_no_mode_given(
    tmp_path: Path,
) -> None:
    target = tmp_path / "f.txt"
    atomic_write_text(target, "x")
    assert target.exists()
    assert target.read_text() == "x"
    if sys.platform != "win32":
        # Owner read bit must be set so the file is readable.
        assert target.stat().st_mode & 0o400


# ─── Parent directory creation ──────────────────────────────────────────


def test_parent_dir_created_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "newsubdir" / "deeper" / "f.txt"
    assert not target.parent.exists()
    atomic_write_text(target, "x")
    assert target.exists()
    assert target.parent.is_dir()


def test_existing_parent_dir_unchanged(tmp_path: Path) -> None:
    parent = tmp_path / "p"
    parent.mkdir()
    sentinel = parent / "preexisting.txt"
    sentinel.write_text("pre")
    sentinel_mtime = sentinel.stat().st_mtime_ns

    atomic_write_text(parent / "new.txt", "new")

    assert parent.is_dir()
    assert sentinel.read_text() == "pre"
    assert sentinel.stat().st_mtime_ns == sentinel_mtime


# ─── Determinism ────────────────────────────────────────────────────────


def test_atomic_write_json_deterministic(tmp_path: Path) -> None:
    data = {"b": 2, "a": 1, "nested": {"y": 2, "x": 1}, "list": [3, 1, 2]}
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    atomic_write_json(p1, data)
    atomic_write_json(p2, data)
    assert p1.read_bytes() == p2.read_bytes()


# ─── fsync verification ────────────────────────────────────────────────


def test_fsync_called_before_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "f.txt"
    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def recording_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    atomic_write_text(target, "hello")

    assert len(fsync_calls) >= 1
    assert all(isinstance(fd, int) and fd >= 0 for fd in fsync_calls)
    assert target.read_text() == "hello"


# ─── Idempotence ────────────────────────────────────────────────────────


def test_writing_same_content_twice_produces_same_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "f.txt"
    atomic_write_text(target, "x")
    first_bytes = target.read_bytes()
    atomic_write_text(target, "x")
    second_bytes = target.read_bytes()
    assert first_bytes == second_bytes == b"x"
