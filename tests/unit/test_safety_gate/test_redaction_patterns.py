"""Tests for safety_gate.redactor — bible 12 §5 redaction surface.

47 tests organised per Phase 3 T6 Step 3 design:

* Per-pattern positive + negative + placeholder format (10 patterns × 3 = 30)
* User-config layering (5)
* Residual / structural (4)
* Schema (5)
* Bible-grounding drift detectors (3)
"""

from __future__ import annotations

from pathlib import Path

import pytest

import paths
from errors import RedactionFailed
from safety_gate import (
    assert_no_residual,
    load_user_patterns,
    redact,
)
from safety_gate.redactor import _BUILTIN_PATTERNS, CompiledPattern
from schemas import RedactionLog, RedactionLogEntry


_BIBLE_12_PATH = Path.home() / "cee" / "bible" / "12_prompt_leak_security_rules.md"


def _names() -> set[str]:
    return {p.name for p in _BUILTIN_PATTERNS}


# ═══════════════════════════════════════════════════════════════════════
# Per-pattern positive + negative + placeholder format (10 patterns × 3)
# ═══════════════════════════════════════════════════════════════════════


# ─── 1. anthropic_api_key ──────────────────────────────────────────────


def test_anthropic_api_key_positive_match() -> None:
    text = "key=sk-ant-api03-abc123def456ghi789jkl012mno345pqr678 here"
    redacted, log = redact(text)
    assert "sk-ant-api03" not in redacted
    assert any(e.pattern == "anthropic_api_key" for e in log)


def test_anthropic_api_key_negative_no_match() -> None:
    text = "no api key in this string at all"
    redacted, log = redact(text)
    assert redacted == text
    assert not any(e.pattern == "anthropic_api_key" for e in log)


def test_anthropic_api_key_placeholder_format() -> None:
    text = "sk-ant-abc123def456ghi789jkl012mno345pqr"
    redacted, log = redact(text)
    assert "<redacted:anthropic_api_key>" in redacted
    assert log[0].replaced_with == "<redacted:anthropic_api_key>"


# ─── 2. openai_api_key ─────────────────────────────────────────────────


def test_openai_api_key_positive_match() -> None:
    text = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD here"
    redacted, log = redact(text)
    assert any(e.pattern == "openai_api_key" for e in log)


def test_openai_api_key_negative_too_short() -> None:
    text = "sk-tooshort"
    redacted, log = redact(text)
    assert redacted == text
    assert not any(e.pattern == "openai_api_key" for e in log)


def test_openai_api_key_placeholder_format() -> None:
    text = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    redacted, log = redact(text)
    assert "<redacted:openai_api_key>" in redacted


# ─── 3. aws_access_key ─────────────────────────────────────────────────


def test_aws_access_key_positive_match() -> None:
    text = "AKIAIOSFODNN7EXAMPLE here"
    redacted, log = redact(text)
    assert any(e.pattern == "aws_access_key" for e in log)


def test_aws_access_key_negative_wrong_prefix() -> None:
    text = "BKIAIOSFODNN7EXAMPLE wrong prefix"
    redacted, log = redact(text)
    assert not any(e.pattern == "aws_access_key" for e in log)


def test_aws_access_key_placeholder_format() -> None:
    text = "AKIAIOSFODNN7EXAMPLE"
    redacted, log = redact(text)
    assert "<redacted:aws_access_key>" in redacted


# ─── 4. aws_secret_key ─────────────────────────────────────────────────


def test_aws_secret_key_positive_match() -> None:
    # 40-char base64-ish string isolated by whitespace
    text = "secret wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY here"
    redacted, log = redact(text)
    assert any(e.pattern == "aws_secret_key" for e in log)


def test_aws_secret_key_negative_too_short() -> None:
    text = "shortstring"
    redacted, log = redact(text)
    assert not any(e.pattern == "aws_secret_key" for e in log)


def test_aws_secret_key_placeholder_format() -> None:
    text = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    redacted, log = redact(text)
    assert "<redacted:aws_secret_key>" in redacted


# ─── 5. github_token ───────────────────────────────────────────────────


def test_github_token_positive_match_classic() -> None:
    text = "ghp_abcdefghijklmnopqrstuvwxyz0123456789 here"
    redacted, log = redact(text)
    assert any(e.pattern == "github_token" for e in log)


def test_github_token_negative_wrong_prefix() -> None:
    text = "gho_abcdefghijklmnopqrstuvwxyz0123456789 here"
    redacted, log = redact(text)
    assert not any(e.pattern == "github_token" for e in log)


def test_github_token_placeholder_format() -> None:
    text = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    redacted, log = redact(text)
    assert "<redacted:github_token>" in redacted


# ─── 6. jwt ────────────────────────────────────────────────────────────


def test_jwt_positive_match() -> None:
    text = (
        "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    redacted, log = redact(text)
    assert any(e.pattern == "jwt" for e in log)


def test_jwt_negative_only_two_parts() -> None:
    text = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    redacted, log = redact(text)
    assert not any(e.pattern == "jwt" for e in log)


def test_jwt_placeholder_format() -> None:
    text = (
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    redacted, log = redact(text)
    assert "<redacted:jwt>" in redacted


# ─── 7. password_in_url ────────────────────────────────────────────────


def test_password_in_url_positive_match() -> None:
    text = "connect to https://admin:s3cret@db.example.com/data"
    redacted, log = redact(text)
    assert any(e.pattern == "password_in_url" for e in log)


def test_password_in_url_negative_no_credentials() -> None:
    text = "https://example.com/data"
    redacted, log = redact(text)
    assert not any(e.pattern == "password_in_url" for e in log)


def test_password_in_url_placeholder_format() -> None:
    text = "https://user:pass@host"
    redacted, log = redact(text)
    assert "<redacted:password_in_url>" in redacted


# ─── 8. phone_us ───────────────────────────────────────────────────────


def test_phone_us_positive_match() -> None:
    text = "Call me at 555-123-4567 tomorrow"
    redacted, log = redact(text)
    assert any(e.pattern == "phone_us" for e in log)


def test_phone_us_negative_too_few_digits() -> None:
    text = "Call 555-1234"
    redacted, log = redact(text)
    assert not any(e.pattern == "phone_us" for e in log)


def test_phone_us_placeholder_format() -> None:
    text = "555.123.4567"
    redacted, log = redact(text)
    assert "<redacted:phone_us>" in redacted


# ─── 9. ssn_us ─────────────────────────────────────────────────────────


def test_ssn_us_positive_match() -> None:
    text = "SSN: 123-45-6789 confidential"
    redacted, log = redact(text)
    assert any(e.pattern == "ssn_us" for e in log)


def test_ssn_us_negative_wrong_format() -> None:
    text = "SSN: 12345 6789"
    redacted, log = redact(text)
    assert not any(e.pattern == "ssn_us" for e in log)


def test_ssn_us_placeholder_format() -> None:
    text = "123-45-6789"
    redacted, log = redact(text)
    assert "<redacted:ssn_us>" in redacted


# ─── 10. private_key_block ─────────────────────────────────────────────


def test_private_key_block_positive_match() -> None:
    text = (
        "before\n-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA...lots of base64...\n"
        "-----END RSA PRIVATE KEY-----\nafter"
    )
    redacted, log = redact(text)
    assert any(e.pattern == "private_key_block" for e in log)


def test_private_key_block_negative_no_block() -> None:
    text = "no key here just text"
    redacted, log = redact(text)
    assert not any(e.pattern == "private_key_block" for e in log)


def test_private_key_block_placeholder_format() -> None:
    text = "-----BEGIN OPENSSH PRIVATE KEY-----\nbody\n-----END OPENSSH PRIVATE KEY-----"
    redacted, log = redact(text)
    assert "<redacted:private_key_block>" in redacted


# ═══════════════════════════════════════════════════════════════════════
# User-config layering (5 tests)
# ═══════════════════════════════════════════════════════════════════════


def test_load_user_patterns_absent_file_returns_empty(tmp_path: Path) -> None:
    """Bible 04 §EC10: missing redact_list is allowed (empty list)."""
    missing = tmp_path / "no_such_file"
    assert load_user_patterns(missing) == []


def test_load_user_patterns_skips_comments_and_blank_lines(
    tmp_path: Path,
) -> None:
    f = tmp_path / "redact_list"
    f.write_text(
        "# This is a comment\n\nClientCorp\n   \n# another comment\nProjectX\n",
        encoding="utf-8",
    )
    patterns = load_user_patterns(f)
    assert len(patterns) == 2


def test_load_user_patterns_plain_entry_exact_match(tmp_path: Path) -> None:
    """Bible 12 §5.3: plain entries are exact-match (re.escape applied)."""
    f = tmp_path / "redact_list"
    f.write_text("ClientCorp.Inc\n", encoding="utf-8")
    patterns = load_user_patterns(f)
    text = "Working with ClientCorp.Inc on the deal"
    redacted, log = redact(text, user_patterns=patterns)
    assert "ClientCorp.Inc" not in redacted
    assert "<redacted:user_term>" in redacted
    assert log[-1].term == "ClientCorp.Inc"


def test_load_user_patterns_regex_prefix_compiled(tmp_path: Path) -> None:
    """Bible 12 §5.3: ``regex:`` prefix → compiled Python regex."""
    f = tmp_path / "redact_list"
    f.write_text("regex:internal-[a-z0-9]{8}\n", encoding="utf-8")
    patterns = load_user_patterns(f)
    text = "see internal-abc12def for context"
    redacted, log = redact(text, user_patterns=patterns)
    assert "internal-abc12def" not in redacted
    assert log[-1].term == "internal-[a-z0-9]{8}"


def test_load_user_patterns_layers_after_builtins(tmp_path: Path) -> None:
    """User patterns run after built-ins; both apply to the same text."""
    f = tmp_path / "redact_list"
    f.write_text("ClientCorp\n", encoding="utf-8")
    patterns = load_user_patterns(f)
    text = "key sk-ant-abc123def456ghi789jkl012mno345pqr and ClientCorp"
    redacted, log = redact(text, user_patterns=patterns)
    pattern_names = {e.pattern for e in log}
    assert "anthropic_api_key" in pattern_names
    assert "user_term" in pattern_names


# ═══════════════════════════════════════════════════════════════════════
# Residual / structural (4 tests)
# ═══════════════════════════════════════════════════════════════════════


def test_assert_no_residual_clean_text_passes() -> None:
    """No built-in pattern matches → no exception."""
    assert_no_residual("just regular text here, nothing sensitive")


def test_assert_no_residual_dirty_text_raises() -> None:
    """Per bible 12 §10.2, residual content is RedactionFailed."""
    with pytest.raises(RedactionFailed):
        assert_no_residual("oops AKIAIOSFODNN7EXAMPLE leaked")


def test_redact_returns_log_entries_per_match() -> None:
    """One log entry per match, even if same pattern hits multiple times."""
    text = "key1 sk-ant-aaa111bbb222ccc333ddd444eee555fff and "
    text += "key2 sk-ant-zzz999yyy888xxx777www666vvv555uuu"
    redacted, log = redact(text)
    anthropic_entries = [e for e in log if e.pattern == "anthropic_api_key"]
    assert len(anthropic_entries) == 2


def test_redact_log_entry_shape_matches_bible_12_7_2() -> None:
    """Bible 12 §7.2's RedactionLog example: each entry has
    {pattern, location, replaced_with}.
    """
    text = "AKIAIOSFODNN7EXAMPLE"
    _, log = redact(text)
    entry = log[0]
    assert hasattr(entry, "pattern")
    assert hasattr(entry, "location")
    assert hasattr(entry, "replaced_with")
    assert entry.location == "prompt"


# ═══════════════════════════════════════════════════════════════════════
# Schema integration (5 tests)
# ═══════════════════════════════════════════════════════════════════════


def test_redaction_log_built_from_redact_output() -> None:
    """The RedactionLog wrapper accepts the raw redact() log list."""
    text = "AKIAIOSFODNN7EXAMPLE and ssn 123-45-6789"
    _, entries = redact(text)
    log = RedactionLog(redactions=entries)
    assert len(log.redactions) == 2


def test_redaction_log_default_produced_by_safety_gate() -> None:
    log = RedactionLog()
    assert log.produced_by.value == "SAFETY_GATE"


def test_redaction_log_extras_forbidden() -> None:
    from pydantic import ValidationError as PydanticValidationError
    with pytest.raises(PydanticValidationError):
        RedactionLog(redactions=[], extra_field="x")


def test_redaction_log_round_trip_json() -> None:
    text = "AKIAIOSFODNN7EXAMPLE"
    _, entries = redact(text)
    original = RedactionLog(redactions=entries)
    payload = original.model_dump_json()
    restored = RedactionLog.model_validate_json(payload)
    assert restored == original


def test_redaction_log_schema_version_present() -> None:
    log = RedactionLog()
    assert log.schema_version == "1.0.0"


# ═══════════════════════════════════════════════════════════════════════
# Bible-grounding drift detectors (3 tests)
# ═══════════════════════════════════════════════════════════════════════


def test_builtin_pattern_names_match_bible_12_5_2() -> None:
    """Each shipped pattern's name must appear as a labelled cell in
    bible 12 §5.2's catalog table.
    """
    if not _BIBLE_12_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_12_PATH}")
    text = _BIBLE_12_PATH.read_text(encoding="utf-8")
    section_start = text.find("### 5.2 The redaction pattern catalog")
    section_end = text.find("### 5.3", section_start)
    section = text[section_start:section_end]
    for name in _names():
        assert f"`{name}`" in section, (
            f"pattern {name!r} not found in bible 12 §5.2 catalog"
        )


def test_redaction_log_entry_fields_match_bible_12_7_2() -> None:
    """Bible 12 §7.2's JSON example: each entry has
    pattern + location + replaced_with.
    """
    if not _BIBLE_12_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_12_PATH}")
    text = _BIBLE_12_PATH.read_text(encoding="utf-8")
    section = text[text.find("### 7.2"):text.find("### 7.3")]
    for field in ("pattern", "location", "replaced_with"):
        assert f'"{field}"' in section, (
            f"§7.2 JSON example missing field {field!r}"
        )

    impl_fields = set(RedactionLogEntry.model_fields.keys())
    assert {"pattern", "location", "replaced_with"}.issubset(impl_fields)


def test_placeholder_format_matches_bible_12_5_1() -> None:
    """Bible 12 §5.1 line 84:
    ``placeholder = f"<redacted:{pattern_name}>"``.
    Every built-in pattern's placeholder must follow this format.
    """
    for pattern in _BUILTIN_PATTERNS:
        assert pattern.placeholder == f"<redacted:{pattern.name}>", (
            f"placeholder for {pattern.name!r} does not match bible §5.1"
        )
