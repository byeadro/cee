"""Load and validate ``~/.cee/config.toml`` against the Config schema.

Authorized by System Design Bible:

* **04 §5.2** — the canonical config layout, sections, and defaults.
* **04 §10.7** — failure recovery: "Default config can be regenerated from
  ``~/cee/.template/config.toml.default``."
* **00 §12 B1** — boot-step taxonomy. Config loading is folded into
  environment verification; failures here raise ``BootError(step="B1")``.
* **19 §5.7** — the ``BootError`` exception contract.
* **02 §5 Rule 5** — external roles never write directly to canon. The
  template-copy here goes through :func:`atomic_write_text`, the only
  sanctioned writer per bible 14.

The loader does three things:

1. If ``CONFIG_FILE`` is missing, atomically copy the template at
   ``TEMPLATE_CONFIG_FILE`` to ``CONFIG_FILE`` (creating the user
   config directory if needed).
2. Read ``CONFIG_FILE`` and parse it with :mod:`tomllib`.
3. Validate the parsed dict against :class:`schemas.Config` and return
   the typed model.

Any of those steps failing raises :class:`errors.BootError` with
``step="B1"`` so the pipeline driver's boot dispatcher can handle it
uniformly.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import ValidationError

import paths
from errors import BootError
from persistence.atomic import atomic_write_text
from schemas import Config

# Boot step for config-loading failures. Bible 00 §12: B1 is "Verify
# environment", which subsumes reading and validating the user config.
_BOOT_STEP = "B1"


def load_config() -> Config:
    """Load the OPERATOR's ``~/.cee/config.toml`` and return a typed
    :class:`schemas.Config`.

    Behaviour:

    * If ``paths.CONFIG_FILE`` does not exist, the user config directory
      ``paths.USER_CONFIG_DIR`` is created via :func:`paths.ensure_dir`
      and ``paths.TEMPLATE_CONFIG_FILE`` is copied to
      ``paths.CONFIG_FILE`` via :func:`atomic_write_text` (the only
      sanctioned writer per bible 14). The OPERATOR's existing config
      is never overwritten.
    * The file is read and parsed by :mod:`tomllib` (Python 3.11+ stdlib).
    * The parsed dict is validated against :class:`schemas.Config`.
    * Any failure (template missing, TOML parse error, schema
      violation, OS error) raises :class:`errors.BootError` with
      ``step="B1"`` and a ``reason`` pointing at the failed file.

    Returns
    -------
    Config
        A fully-validated :class:`schemas.Config` instance — every
        nested section model has been constructed and cross-validators
        have run.

    Raises
    ------
    errors.BootError
        With ``step="B1"`` if the config cannot be loaded for any reason.
        Bible 04 §10.7 documents the recovery path (regenerate the file
        from the template).
    """
    _ensure_user_config_present()

    raw = _read_toml(paths.CONFIG_FILE)
    return _validate(raw)


# --------------------------------------------------------------------------- #
# Internals                                                                   #
# --------------------------------------------------------------------------- #


def _ensure_user_config_present() -> None:
    """Create ``USER_CONFIG_DIR`` and copy the template to ``CONFIG_FILE``
    if (and only if) ``CONFIG_FILE`` does not exist.

    Idempotent: when the OPERATOR's config is already present, this is a
    no-op. The template itself is never mutated.
    """
    if paths.CONFIG_FILE.exists():
        return

    if not paths.TEMPLATE_CONFIG_FILE.exists():
        raise BootError(
            step=_BOOT_STEP,
            reason=(
                f"config template missing at {paths.TEMPLATE_CONFIG_FILE!s}; "
                "expected the bible-mandated default at this location "
                "(bible 04 §10.7). Reinstall CEE or restore the template "
                "from the repository."
            ),
        )

    paths.ensure_dir(paths.USER_CONFIG_DIR)

    try:
        template_text = paths.TEMPLATE_CONFIG_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise BootError(
            step=_BOOT_STEP,
            reason=(
                f"failed to read config template at "
                f"{paths.TEMPLATE_CONFIG_FILE!s}: {exc}"
            ),
        ) from exc

    try:
        atomic_write_text(paths.CONFIG_FILE, template_text)
    except OSError as exc:
        raise BootError(
            step=_BOOT_STEP,
            reason=(
                f"failed to write user config at {paths.CONFIG_FILE!s} "
                f"from template {paths.TEMPLATE_CONFIG_FILE!s}: {exc}"
            ),
        ) from exc


def _read_toml(path: Path) -> dict:
    """Read and parse a TOML file, mapping any failure to BootError(step=B1)."""
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError as exc:
        # _ensure_user_config_present should have prevented this; if we
        # reach here, the OPERATOR removed the file mid-boot.
        raise BootError(
            step=_BOOT_STEP,
            reason=(
                f"user config disappeared between materialise and read "
                f"at {path!s}"
            ),
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise BootError(
            step=_BOOT_STEP,
            reason=(
                f"invalid TOML in user config at {path!s}: {exc}. "
                "Bible 04 §10.7 — the default can be regenerated from "
                f"{paths.TEMPLATE_CONFIG_FILE!s}."
            ),
        ) from exc
    except OSError as exc:
        raise BootError(
            step=_BOOT_STEP,
            reason=f"failed to read user config at {path!s}: {exc}",
        ) from exc


def _validate(raw: dict) -> Config:
    """Validate a parsed TOML dict against :class:`schemas.Config`."""
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise BootError(
            step=_BOOT_STEP,
            reason=(
                f"user config at {paths.CONFIG_FILE!s} failed schema "
                f"validation against Config (bible 04 §5.2):\n{exc}"
            ),
        ) from exc
