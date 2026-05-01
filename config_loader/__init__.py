"""Boot-time loader for the OPERATOR's ``~/.cee/config.toml``.

Re-exports :func:`config_loader.loader.load_config` so callers can write
``from config_loader import load_config``. Bible reference: 04 §5.2 +
§10.7 (template regeneration), bible 00 §12 B1 (this module runs as part
of environment verification).
"""

from config_loader.loader import load_config

__all__ = ["load_config"]
