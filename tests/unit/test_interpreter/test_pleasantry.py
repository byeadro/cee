"""Tests for the interpreter's pleasantry detector.

Verifies the closed 6-pattern :data:`_PLEASANTRY_PATTERNS` set covers
the Phase 4 acceptance set (whitespace, greetings, thanks,
acknowledgements, farewells, punctuation-only) without over-matching
actionable inputs that happen to start with a pleasantry-shaped
token.

Reference: bible 01 EC12 + bible 02 §248 + bible 03 §5.2 Step 2.
T5 ships the regex set as canonical-by-shipped-state pending bible
canonicalization (downstream candidate #64).
"""

from __future__ import annotations

from interpreter.interpreter import _is_pleasantry


# --------------------------------------------------------------------------- #
# Positive cases — one test per pattern in the closed 6-pattern set            #
# --------------------------------------------------------------------------- #


def test_whitespace_only_is_pleasantry() -> None:
    for text in ("", "   ", "\t\n  "):
        assert _is_pleasantry(text) is True, text


def test_greetings_are_pleasantry() -> None:
    for text in (
        "hi",
        "hello",
        "good morning",
        "yo",
        "howdy",
    ):
        assert _is_pleasantry(text) is True, text


def test_thanks_are_pleasantry() -> None:
    for text in (
        "thanks",
        "thank you",
        "ty",
        "thx",
        "appreciated",
        "cheers",
    ):
        assert _is_pleasantry(text) is True, text


def test_acknowledgements_are_pleasantry() -> None:
    for text in (
        "ok",
        "okay",
        "yes",
        "no",
        "sure",
        "got it",
        "alright",
    ):
        assert _is_pleasantry(text) is True, text


def test_farewells_are_pleasantry() -> None:
    for text in ("bye", "goodbye", "see ya", "later"):
        assert _is_pleasantry(text) is True, text


def test_punctuation_only_is_pleasantry() -> None:
    for text in ("?", "??", "!", "...", "?!"):
        assert _is_pleasantry(text) is True, text


# --------------------------------------------------------------------------- #
# Negative cases — actionable inputs must NOT match                            #
# --------------------------------------------------------------------------- #


def test_actionable_inputs_are_not_pleasantry() -> None:
    """Sentences that start with a pleasantry-shaped token but extend
    into actionable goal language must NOT be flagged.

    The "thanks much I appreciate it" case is the canonical regression
    guard: the thanks-pattern ends at ``[!.\\s]*$`` so trailing words
    after whitespace cause the pattern to miss, leaving the input
    actionable.
    """
    actionable = (
        "thanks much I appreciate it",
        "hi can you help me with X",
        "yes please write the email about quarterly results",
        "ok now build the schema",
        "good morning, write me an RLS policy for the mentor_inquiries table",
        "Refactor this module to use dataclasses.",
    )
    for text in actionable:
        assert _is_pleasantry(text) is False, text


# --------------------------------------------------------------------------- #
# Edge cases — case-insensitivity, trailing punctuation, surrounding ws        #
# --------------------------------------------------------------------------- #


def test_case_insensitive() -> None:
    for text in ("Hi", "HELLO", "Good Morning"):
        assert _is_pleasantry(text) is True, text


def test_trailing_punctuation_tolerated() -> None:
    for text in ("hi!", "thanks.", "ok?"):
        assert _is_pleasantry(text) is True, text


def test_surrounding_whitespace_tolerated() -> None:
    for text in ("  hi  ", " thanks ", " OK "):
        assert _is_pleasantry(text) is True, text
