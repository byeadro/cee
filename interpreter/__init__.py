"""INTERPRETER pipeline-step module — Step 2 of the Run pipeline.

Phase 4 T5 ships the seam consumed by the pipeline driver (Phase 5+).
Bible 03 §5.2 Step 2 names :class:`Interpreter` as the role that
converts ``RawInput`` to ``IntentObject`` via temperature-0 Claude
call with the fixed system prompt at
``~/cee/prompts/interpreter_system.txt``.
"""

from interpreter.interpreter import Interpreter, InterpreterConfig

__all__ = [
    "Interpreter",
    "InterpreterConfig",
]
