"""Atomic filesystem write helpers — the only sanctioned writers in CEE.

This module provides the only sanctioned way to write files in CEE.
Every other module that needs to mutate a file MUST go through one of
these helpers; raw ``open()`` for writes is forbidden by bible 14
("All filesystem writes use ``~/cee/persistence/atomic.py``. Never use
raw ``open()``").

**Atomicity guarantee.** A caller observing the target path always sees
either the previous state or the new state — never partial bytes. The
implementation writes content to a temp file in the same directory as
the target, fsyncs it to disk, then ``os.replace()`` it over the
target. ``os.replace()`` is atomic on POSIX and on Windows (Python 3.3+).

**fsync guarantee.** Data is flushed to disk via ``os.fsync()`` before
the rename returns, so a crash after the rename still leaves the new
content readable. A crash *before* the rename leaves the target
untouched.

**Same-filesystem requirement.** The temp file lives in the same
directory as the target. ``os.replace()`` is only atomic within a
single filesystem; using ``tempfile.gettempdir()`` would silently break
atomicity when ``/tmp`` lives on a different mount.

``atomic_write_*`` delegates parent-directory creation to
``cee.paths.ensure_dir``, which is the only sanctioned mechanism for
materializing directories outside of ``cee init`` scaffolding.

Bible references mandating atomic writes:

- ``04_database_file_structure.md`` §4 Rule 4 ("Atomic writes only").
- ``04_database_file_structure.md`` §11 — names this module and these
  functions; declares atomic writes the only path to filesystem mutation.
- ``03_full_system_workflow.md`` — every Run step writes via these helpers.
- ``12_prompt_leak_security_rules.md`` — audit-log integrity depends on
  atomic appends; partial writes would invalidate the hash chain.
- ``13_obsidian_integration.md`` — Obsidian writes also use this helper.
- ``14_claude_code_integration.md`` — "Never use raw ``open()``."
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import IO, Callable

# `paths` lives at the project root (~/cee/paths.py). Conceptually
# referenced as `cee.paths` in docstrings; on the import path it
# resolves as the top-level `paths` module.
from paths import ensure_dir


def _atomic_write_via_temp(
    path: Path,
    write_callback: Callable[[IO[bytes]], None],
    mode: int | None,
) -> None:
    """Shared atomicity logic: same-dir temp file, fsync, ``os.replace``.

    Steps, in order:

    1. Ensure ``path.parent`` exists (via ``cee.paths.ensure_dir``).
    2. Resolve the effective file mode: caller-supplied ``mode`` wins;
       otherwise preserve the existing target's permission bits if it
       exists; otherwise leave at the OS default (umask).
    3. Open a ``NamedTemporaryFile(delete=False)`` in ``path.parent``.
    4. Hand its binary file handle to ``write_callback``.
    5. ``flush()`` + ``os.fsync(fd)`` BEFORE ``close()`` so kernel
       buffers reach the disk before the rename.
    6. ``chmod`` the temp file to the effective mode (if any).
    7. ``os.replace(tmp, path)`` — the atomic step.

    On any exception, the temp file is unlinked and the exception is
    re-raised. The target is never observed in a partial state.
    """
    ensure_dir(path.parent)

    effective_mode: int | None = mode
    if effective_mode is None and path.exists():
        try:
            effective_mode = path.stat().st_mode & 0o7777
        except OSError:
            effective_mode = None

    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    try:
        try:
            write_callback(tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()

        if effective_mode is not None:
            os.chmod(tmp_path, effective_mode)

        os.replace(tmp_path, path)
    except BaseException:
        # Cleanup MUST not leak a partial temp file on failure.
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    mode: int | None = None,
) -> None:
    """Atomically write ``text`` to ``path``.

    After the call returns, ``path`` either contains exactly ``text``
    encoded as ``encoding``, or is unchanged from before. Never a
    partial write.

    The parent directory is created via ``cee.paths.ensure_dir`` if
    missing — callers do not need to ``mkdir`` themselves.

    Permission bits: if ``mode`` is given, the resulting file has that
    mode; otherwise, an existing target's mode is preserved; otherwise,
    the OS default (umask) applies.
    """
    encoded = text.encode(encoding)

    def _write(fh: IO[bytes]) -> None:
        fh.write(encoded)

    _atomic_write_via_temp(path, _write, mode)


def atomic_write_json(
    path: Path,
    data: object,
    *,
    indent: int = 2,
    sort_keys: bool = True,
    mode: int | None = None,
) -> None:
    """Atomically write ``data`` as JSON to ``path``.

    Same atomicity guarantees as :func:`atomic_write_text`.

    Determinism: ``sort_keys`` defaults to ``True`` so the same data
    always produces the same byte sequence. ``allow_nan=False`` rejects
    ``NaN`` and ``±Infinity`` — these are not valid JSON and indicate a
    bug upstream rather than something to silently emit. ``ensure_ascii``
    is ``False`` so the rendered file is human-readable for non-ASCII
    text without changing semantics.
    """
    rendered = json.dumps(
        data,
        indent=indent,
        sort_keys=sort_keys,
        allow_nan=False,
        ensure_ascii=False,
    )
    encoded = rendered.encode("utf-8")

    def _write(fh: IO[bytes]) -> None:
        fh.write(encoded)

    _atomic_write_via_temp(path, _write, mode)
