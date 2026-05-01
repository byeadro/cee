"""Tests for the Credentials schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import AnthropicCredentials, Credentials


_BIBLE_PATH = Path.home() / "cee" / "bible" / "04_database_file_structure.md"


def _valid_anthropic_kwargs() -> dict:
    return {
        "api_key": "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    }


# --------------------------------------------------------------------------- #
# Standard schema tests — Credentials                                         #
# --------------------------------------------------------------------------- #


def test_credentials_minimal_valid() -> None:
    """Empty Credentials() must construct cleanly so Phase 1 — which ships
    an empty/commented-out credentials.toml per bible 21 task 10 — can
    load it without errors. The required-when-Phase-2-enabled invariant
    is enforced at APIExecutor construction (bible 14 §9 EC12), not here.
    """
    obj = Credentials()
    assert obj.anthropic is None
    assert obj.schema_version == "1.0.0"


def test_credentials_full_valid() -> None:
    obj = Credentials(
        anthropic=AnthropicCredentials(**_valid_anthropic_kwargs()),
    )
    assert obj.anthropic is not None
    assert obj.anthropic.api_key.startswith("sk-ant-")


def test_credentials_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Credentials(unknown_field="x")


def test_credentials_string_whitespace_stripped() -> None:
    obj = Credentials(schema_version="  1.0.0  ")
    assert obj.schema_version == "1.0.0"


def test_credentials_schema_version_present() -> None:
    assert Credentials.SCHEMA_VERSION == "1.0.0"
    assert AnthropicCredentials.SCHEMA_VERSION == "1.0.0"


def test_credentials_json_round_trip() -> None:
    original = Credentials(
        anthropic=AnthropicCredentials(**_valid_anthropic_kwargs()),
    )
    payload = original.model_dump_json()
    restored = Credentials.model_validate_json(payload)
    assert restored == original


def test_credentials_dict_round_trip() -> None:
    original = Credentials(
        anthropic=AnthropicCredentials(**_valid_anthropic_kwargs()),
    )
    payload = original.model_dump()
    restored = Credentials.model_validate(payload)
    assert restored == original


def test_credentials_field_order_stable() -> None:
    """Field order: schema_version, anthropic. schema_version comes first
    by Phase 2 convention (matches SyncMeta from task 1).
    """
    obj = Credentials()
    expected_order = ["schema_version", "anthropic"]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Standard schema tests — AnthropicCredentials                                #
# --------------------------------------------------------------------------- #


def test_anthropic_credentials_minimal_valid() -> None:
    obj = AnthropicCredentials(**_valid_anthropic_kwargs())
    assert obj.api_key.startswith("sk-ant-")


def test_anthropic_credentials_missing_api_key_raises() -> None:
    with pytest.raises(ValidationError):
        AnthropicCredentials()


def test_anthropic_credentials_extra_field_rejected() -> None:
    kwargs = _valid_anthropic_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        AnthropicCredentials(**kwargs)


def test_anthropic_credentials_string_whitespace_stripped() -> None:
    obj = AnthropicCredentials(api_key="  sk-ant-api03-test  ")
    assert obj.api_key == "sk-ant-api03-test"


def test_anthropic_credentials_field_order_stable() -> None:
    obj = AnthropicCredentials(**_valid_anthropic_kwargs())
    expected_order = ["api_key"]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific                                                              #
# --------------------------------------------------------------------------- #


def test_anthropic_field_defaults_to_none() -> None:
    """The top-level ``anthropic`` field is Optional so Phase 1's
    empty/commented-out credentials.toml constructs without errors. The
    required-when-api_enabled invariant lives at APIExecutor (bible 14
    §9 EC12), not in this schema.
    """
    obj = Credentials()
    assert obj.anthropic is None


def test_anthropic_field_can_be_explicitly_none() -> None:
    obj = Credentials(anthropic=None)
    assert obj.anthropic is None


def test_credentials_constructs_from_empty_dict() -> None:
    """Mirrors loading from an empty/commented-out credentials.toml file:
    a TOML parser that finds no sections produces ``{}`` and Credentials
    must accept it.
    """
    obj = Credentials.model_validate({})
    assert obj.anthropic is None
    assert obj.schema_version == "1.0.0"


def test_schema_version_defaults_to_one_zero_zero() -> None:
    obj = Credentials()
    assert obj.schema_version == "1.0.0"
    assert obj.schema_version == Credentials.SCHEMA_VERSION


def test_schema_version_appears_in_json_dump() -> None:
    """Phase 2 convention (set by SyncMeta in task 1): persistent
    user-config files carry schema_version on disk for migration routing
    per bible 04 §6.1. Credentials follows the same pattern.
    """
    obj = Credentials()
    payload = obj.model_dump()
    assert "schema_version" in payload
    assert payload["schema_version"] == "1.0.0"


def test_api_key_must_match_anthropic_prefix() -> None:
    """Anthropic API keys begin with ``sk-ant-``; values without the
    prefix (placeholder strings, keys from other providers) are rejected.
    """
    bad_values = [
        "sk-test-1234567890",      # OpenAI-style
        "AKIA1234567890ABCDEF",     # AWS-style
        "your-api-key-here",        # placeholder
        "ant-sk-1234",              # transposed prefix
        "SK-ANT-UPPER",             # case-sensitive — pattern is lowercase
    ]
    for bad in bad_values:
        with pytest.raises(ValidationError):
            AnthropicCredentials(api_key=bad)


def test_api_key_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        AnthropicCredentials(api_key="")
    # Whitespace-only also rejected (str_strip_whitespace + min_length=1).
    with pytest.raises(ValidationError):
        AnthropicCredentials(api_key="   ")


def test_api_key_accepts_realistic_anthropic_format() -> None:
    """Real Anthropic keys are ~108 chars: sk-ant-api03-<long opaque>.
    The schema enforces the prefix; the rest is opaque length.
    """
    realistic = "sk-ant-api03-" + ("X" * 95)
    obj = AnthropicCredentials(api_key=realistic)
    assert obj.api_key == realistic


def test_anthropic_credentials_class_name_does_not_collide_with_sdk() -> None:
    """Design call: nested class is ``AnthropicCredentials`` (not
    ``Anthropic``) to avoid colliding with ``anthropic.Anthropic`` (the
    SDK client class that Phase 2 task 6/7 will import).
    """
    assert AnthropicCredentials.__name__ == "AnthropicCredentials"


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_credentials_field_set_matches_bible() -> None:
    """Bible 04 §5.2's ``credentials.toml`` schema declares one section
    (``[anthropic]``) with one field (``api_key``). Implementation must
    include that field on AnthropicCredentials and expose [anthropic] as
    the named attribute on Credentials.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")

    section_start = bible_text.find("#### `credentials.toml` schema:")
    section_end = bible_text.find("### 5.3", section_start)
    assert section_start != -1, "§5.2 credentials.toml schema block not found in bible 04"
    assert section_end != -1, "§5.3 boundary not found in bible 04"
    section = bible_text[section_start:section_end]

    # Bible declares the [anthropic] TOML section.
    assert "[anthropic]" in section, (
        "§5.2 credentials.toml schema block missing [anthropic] section header"
    )
    # Bible declares the api_key field.
    assert "api_key" in section, (
        "§5.2 credentials.toml schema block missing api_key field"
    )
    # Bible specifies the sk-ant- prefix.
    assert "sk-ant-" in section, (
        "§5.2 credentials.toml schema block missing sk-ant- prefix example"
    )

    # Implementation has [anthropic] section as the ``anthropic`` attribute.
    assert "anthropic" in Credentials.model_fields, (
        "Credentials missing ``anthropic`` field for bible §5.2 [anthropic] section"
    )
    # Implementation has api_key field on AnthropicCredentials.
    assert "api_key" in AnthropicCredentials.model_fields, (
        "AnthropicCredentials missing ``api_key`` field per bible §5.2"
    )


def test_credentials_section_attribute_lowercase_matches_toml() -> None:
    """The ``[anthropic]`` TOML section maps to the lowercase ``anthropic``
    attribute (Python convention; TOML is case-sensitive). This test
    pins that lowercase mapping so a future rename to ``Anthropic`` (or
    similar) breaks loudly here rather than silently mis-loading user
    credentials.toml files.
    """
    assert "anthropic" in Credentials.model_fields
    assert "Anthropic" not in Credentials.model_fields
