"""CEE CLI subcommand implementations.

Each module under this package defines one ``cmd_<name>`` function with
the signature ``cmd_<name>(args: argparse.Namespace) -> int``. The
dispatcher in :mod:`cli.main` wires them in via
``subparser.set_defaults(func=cmd_<name>)``.
"""
