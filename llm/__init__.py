"""LLM client wrapper for internal pipeline-stage Claude calls.

Phase 4 T3 ships the seam consumed by the Interpreter (T5, bible 03 §5.2
Step 2) and Classifier (T11, bible 08 §5.5) modules. Distinct from the
Phase 7 ``EXECUTOR`` adapter (bible 14 §5.6) which sends FinalPrompts as
the terminal pipeline step — see downstream candidate #60 for the
canonicalization deferral.
"""

from llm.anthropic_client import (
    LiveAnthropicClient,
    LLMClient,
    LLMResponse,
    default_client_factory,
)

__all__ = [
    "LLMClient",
    "LLMResponse",
    "LiveAnthropicClient",
    "default_client_factory",
]
