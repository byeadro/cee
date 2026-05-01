"""Tests for the Config schema (task 10).

Verifies all 17 nested section models from bible 04 §5.2 + section-specific
configuration declarations, with bible-grounding that compares the rendered
template's section headers against the Config model's attribute names.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

import paths
from schemas import (
    AgentSelectorConfig,
    AgentsConfig,
    ClassifierConfig,
    ClaudeCodeConfig,
    Config,
    ErrorsConfig,
    ExecutorConfig,
    GeneralConfig,
    GroundingConfig,
    InterpreterConfig,
    ObsidianConfig,
    OutputFormatConfig,
    PathsConfig,
    Phase2Config,
    PromptBuilderConfig,
    SecurityConfig,
    SkillEngineConfig,
    SkillsConfig,
)


# Section names in bible-template order.
_EXPECTED_SECTIONS: tuple[str, ...] = (
    "general",
    "paths",
    "interpreter",
    "classifier",
    "agent_selector",
    "skill_engine",
    "skills",
    "agents",
    "prompt_builder",
    "output_format",
    "grounding",
    "security",
    "obsidian",
    "claude_code",
    "executor",
    "phase2",
    "errors",
)

# Section name → expected nested model class.
_SECTION_MODEL_MAP: dict[str, type[BaseModel]] = {
    "general": GeneralConfig,
    "paths": PathsConfig,
    "interpreter": InterpreterConfig,
    "classifier": ClassifierConfig,
    "agent_selector": AgentSelectorConfig,
    "skill_engine": SkillEngineConfig,
    "skills": SkillsConfig,
    "agents": AgentsConfig,
    "prompt_builder": PromptBuilderConfig,
    "output_format": OutputFormatConfig,
    "grounding": GroundingConfig,
    "security": SecurityConfig,
    "obsidian": ObsidianConfig,
    "claude_code": ClaudeCodeConfig,
    "executor": ExecutorConfig,
    "phase2": Phase2Config,
    "errors": ErrorsConfig,
}


# --------------------------------------------------------------------------- #
# Construction & defaults                                                     #
# --------------------------------------------------------------------------- #


def test_config_minimal_valid() -> None:
    """Constructing with no args yields a fully-valid object — every field
    has a bible-mandated default."""
    obj = Config()
    for section_name in _EXPECTED_SECTIONS:
        assert hasattr(obj, section_name), section_name
        assert isinstance(
            getattr(obj, section_name), _SECTION_MODEL_MAP[section_name]
        )


def test_config_full_valid() -> None:
    """Constructing with every field explicitly set still validates."""
    obj = Config(
        general=GeneralConfig(auto_sync=False, fresh_boot=True),
        paths=PathsConfig(
            cee_root="/tmp/cee",
            obsidian_vault="/tmp/SecondBrain",
            notion_bible_root_id="abc123",
        ),
        interpreter=InterpreterConfig(
            ambiguity_clarification_threshold=0.7,
            ambiguity_visible_threshold=0.4,
        ),
        classifier=ClassifierConfig(
            ambiguity_halt_delta=0.05,
            human_gate_for_destructive_irreversible=False,
            human_gate_for_external_effects=False,
            low_tier_escalation_strict=False,
        ),
        agent_selector=AgentSelectorConfig(
            description_match_threshold=0.7,
            generation_threshold=0.4,
            recent_usage_bonus_window_days=14,
        ),
        skill_engine=SkillEngineConfig(
            reuse_threshold=0.9,
            ask_threshold=0.5,
            duplicate_levenshtein_threshold=0.05,
            min_reuse_count_for_promotion_priority=5,
        ),
        skills=SkillsConfig(
            max_body_words=2000,
            max_total_lines=2500,
            enforce_changelog_version_match=False,
        ),
        agents=AgentsConfig(
            max_body_words_simple=400,
            max_body_words_complex=900,
            enable_llm_body_validation=True,
        ),
        prompt_builder=PromptBuilderConfig(
            safety_buffer_tokens=2000,
            enable_role_smoothing=False,
        ),
        output_format=OutputFormatConfig(
            auto_rerun_on_hard_fail=True,
            acceptance_check_uses_llm=False,
            prose_short_max_words=300,
            prose_long_max_words=4000,
        ),
        grounding=GroundingConfig(
            coverage_threshold=0.95,
            auto_rerun_on_violation=True,
            acceptance_check_uses_llm=False,
            default_citation_format="footnote",
        ),
        security=SecurityConfig(
            confirmation_timeout_hours=12,
            notion_strict_redaction=False,
            obsidian_redaction_pass=False,
            audit_hash_chain=False,
            purge_raw_input_after_days=180,
        ),
        obsidian=ObsidianConfig(
            vault_root="/tmp/SecondBrain/cee",
            enable_daily_sync=True,
            regenerate_indexes_on_run=True,
            preserve_manual_edits=False,
        ),
        claude_code=ClaudeCodeConfig(
            claude_md_auto_sync=True,
            hooks_installed=True,
            slash_commands_installed=True,
        ),
        executor=ExecutorConfig(default_target="api"),
        phase2=Phase2Config(api_enabled=True, api_model="claude-sonnet-4-6"),
        errors=ErrorsConfig(
            verbose_messages=False,
            auto_open_run_dir_on_halt=True,
            treat_warnings_as_errors=True,
        ),
    )
    assert obj.general.auto_sync is False
    assert obj.executor.default_target == "api"


def test_config_schema_version_present() -> None:
    assert Config.SCHEMA_VERSION == "1.0.0"


# --------------------------------------------------------------------------- #
# Per-section default values (bible-mandated)                                 #
# --------------------------------------------------------------------------- #


def test_general_defaults() -> None:
    g = GeneralConfig()
    assert g.auto_sync is True
    assert g.fresh_boot is False


def test_paths_defaults() -> None:
    p = PathsConfig()
    assert p.cee_root == "~/cee"
    assert p.obsidian_vault == "~/SecondBrain"
    assert p.notion_bible_root_id == "352e8536-d882-8050-aff6-f1dbcff68a09"


def test_interpreter_defaults_per_bible_03_5_2() -> None:
    i = InterpreterConfig()
    assert i.ambiguity_clarification_threshold == 0.6
    assert i.ambiguity_visible_threshold == 0.3


def test_classifier_defaults_per_bible_08_6_2() -> None:
    c = ClassifierConfig()
    assert c.ambiguity_halt_delta == 0.10
    assert c.human_gate_for_destructive_irreversible is True
    assert c.human_gate_for_external_effects is True
    assert c.low_tier_escalation_strict is True


def test_agent_selector_thresholds_default_to_bible_values() -> None:
    a = AgentSelectorConfig()
    assert a.description_match_threshold == 0.65
    assert a.generation_threshold == 0.50
    assert a.recent_usage_bonus_window_days == 30


def test_skill_engine_defaults_per_bible_07_6_3() -> None:
    s = SkillEngineConfig()
    assert s.reuse_threshold == 0.85
    assert s.ask_threshold == 0.60
    assert s.duplicate_levenshtein_threshold == 0.10
    assert s.min_reuse_count_for_promotion_priority == 3


def test_skills_defaults_per_bible_15_6_3() -> None:
    s = SkillsConfig()
    assert s.max_body_words == 1500
    assert s.max_total_lines == 2000
    assert s.enforce_changelog_version_match is True


def test_agents_defaults_per_bible_16_6_3() -> None:
    a = AgentsConfig()
    assert a.max_body_words_simple == 500
    assert a.max_body_words_complex == 800
    assert a.enable_llm_body_validation is False


def test_prompt_builder_defaults_per_bible_09_6_2() -> None:
    p = PromptBuilderConfig()
    assert p.safety_buffer_tokens == 4000
    assert p.enable_role_smoothing is True
    assert p.chunking_strategy == "context_then_plan"


def test_output_format_defaults_per_bible_10_6_3() -> None:
    o = OutputFormatConfig()
    assert o.auto_rerun_on_hard_fail is False
    assert o.acceptance_check_uses_llm is True
    assert o.prose_short_max_words == 500
    assert o.prose_long_max_words == 5000


def test_grounding_defaults_per_bible_11_6_2() -> None:
    g = GroundingConfig()
    assert g.coverage_threshold == 0.90
    assert g.auto_rerun_on_violation is False
    assert g.acceptance_check_uses_llm is True
    assert g.default_citation_format == "inline_bracket"


def test_security_defaults_per_bible_12_6_2() -> None:
    s = SecurityConfig()
    assert s.confirmation_timeout_hours == 24
    assert s.notion_strict_redaction is True
    assert s.obsidian_redaction_pass is True
    assert s.audit_hash_chain is True
    assert s.purge_raw_input_after_days == 90


def test_obsidian_defaults_per_bible_13_6_2() -> None:
    o = ObsidianConfig()
    assert o.vault_root == "~/SecondBrain/cee"
    assert o.enable_daily_sync is False
    assert o.regenerate_indexes_on_run is False
    assert o.preserve_manual_edits is True


def test_claude_code_defaults_per_bible_14_6_4() -> None:
    c = ClaudeCodeConfig()
    assert c.claude_md_auto_sync is False
    assert c.hooks_installed is False
    assert c.slash_commands_installed is False


def test_executor_default_target_is_claude_code() -> None:
    assert ExecutorConfig().default_target == "claude_code"


def test_phase2_defaults_disable_api_per_bible_14_rule_10() -> None:
    p = Phase2Config()
    assert p.api_enabled is False
    assert p.api_model == "claude-opus-4-7"


def test_errors_defaults_per_bible_19_6_2() -> None:
    e = ErrorsConfig()
    assert e.verbose_messages is True
    assert e.auto_open_run_dir_on_halt is False
    assert e.treat_warnings_as_errors is False


# --------------------------------------------------------------------------- #
# Strictness — extra fields rejected                                          #
# --------------------------------------------------------------------------- #


def test_extra_field_at_top_level_rejected() -> None:
    with pytest.raises(ValidationError):
        Config(unknown_section={"x": 1})


@pytest.mark.parametrize(
    "section_model",
    list(_SECTION_MODEL_MAP.values()),
    ids=lambda m: m.__name__,
)
def test_extra_field_in_section_rejected(
    section_model: type[BaseModel],
) -> None:
    with pytest.raises(ValidationError):
        section_model(unknown_field="x")


# --------------------------------------------------------------------------- #
# Range validation                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reuse_threshold": -0.1},
        {"reuse_threshold": 1.5},
        {"ask_threshold": -0.1},
        {"ask_threshold": 1.5},
        {"min_reuse_count_for_promotion_priority": -1},
    ],
)
def test_skill_engine_invalid_threshold_value_rejected(kwargs: dict) -> None:
    base = {
        "reuse_threshold": 0.85,
        "ask_threshold": 0.60,
        "duplicate_levenshtein_threshold": 0.10,
        "min_reuse_count_for_promotion_priority": 3,
    }
    base.update(kwargs)
    with pytest.raises(ValidationError):
        SkillEngineConfig(**base)


def test_executor_invalid_target_rejected() -> None:
    with pytest.raises(ValidationError):
        ExecutorConfig(default_target="unknown")


# --------------------------------------------------------------------------- #
# Cross-validators                                                            #
# --------------------------------------------------------------------------- #


def test_skill_engine_reuse_threshold_must_exceed_ask_threshold() -> None:
    with pytest.raises(ValidationError) as ei:
        SkillEngineConfig(reuse_threshold=0.5, ask_threshold=0.6)
    assert "reuse_threshold" in str(ei.value)
    assert "ask_threshold" in str(ei.value)


def test_skill_engine_reuse_equal_to_ask_rejected() -> None:
    """The cross-validator requires *strict* greater-than per bible 07
    Rule 4 (zones must not overlap). Equality is a degenerate case."""
    with pytest.raises(ValidationError):
        SkillEngineConfig(reuse_threshold=0.7, ask_threshold=0.7)


def test_interpreter_visible_must_be_strictly_below_clarification() -> None:
    with pytest.raises(ValidationError):
        InterpreterConfig(
            ambiguity_clarification_threshold=0.5,
            ambiguity_visible_threshold=0.6,
        )
    with pytest.raises(ValidationError):
        InterpreterConfig(
            ambiguity_clarification_threshold=0.5,
            ambiguity_visible_threshold=0.5,
        )


def test_agent_selector_match_must_be_strictly_above_generation() -> None:
    with pytest.raises(ValidationError):
        AgentSelectorConfig(
            description_match_threshold=0.4,
            generation_threshold=0.5,
        )
    with pytest.raises(ValidationError):
        AgentSelectorConfig(
            description_match_threshold=0.5,
            generation_threshold=0.5,
        )


def test_agents_complex_at_least_simple() -> None:
    with pytest.raises(ValidationError):
        AgentsConfig(max_body_words_simple=900, max_body_words_complex=500)


def test_output_format_long_at_least_short() -> None:
    with pytest.raises(ValidationError):
        OutputFormatConfig(prose_short_max_words=600, prose_long_max_words=400)


# --------------------------------------------------------------------------- #
# Round-trip                                                                  #
# --------------------------------------------------------------------------- #


def test_config_round_trip_dict() -> None:
    original = Config()
    payload = original.model_dump()
    restored = Config.model_validate(payload)
    assert restored == original


def test_config_round_trip_json() -> None:
    original = Config()
    payload = original.model_dump_json()
    restored = Config.model_validate_json(payload)
    assert restored == original


def test_config_round_trip_preserves_overrides() -> None:
    """Round-trip a non-default Config and verify all overrides survive."""
    original = Config(
        general=GeneralConfig(auto_sync=False),
        executor=ExecutorConfig(default_target="api"),
        phase2=Phase2Config(api_enabled=True),
    )
    payload = json.loads(original.model_dump_json())
    restored = Config.model_validate(payload)
    assert restored.general.auto_sync is False
    assert restored.executor.default_target == "api"
    assert restored.phase2.api_enabled is True


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #

# A TOML section header at the start of a line: ``[section_name]``. Excludes
# array-of-tables ``[[...]]`` and quoted/dotted forms (none used here).
_SECTION_HEADER = re.compile(r"^\[([a-z][a-z0-9_]*)\]\s*$")

_TEMPLATE_PATH = paths.TEMPLATE_CONFIG_FILE


def _extract_section_headers(template_text: str) -> list[str]:
    headers: list[str] = []
    for raw_line in template_text.splitlines():
        match = _SECTION_HEADER.match(raw_line)
        if match:
            headers.append(match.group(1))
    return headers


def test_template_section_headers_match_config_attributes() -> None:
    """1:1 correspondence between template ``[section]`` headers and
    Config's nested-model attribute names. Catches future drift in either
    direction (renamed section in template, missing model in code)."""
    if not _TEMPLATE_PATH.exists():
        pytest.skip(f"Template not found at {_TEMPLATE_PATH}")

    template_text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    template_sections = _extract_section_headers(template_text)
    config_attrs = [name for name in Config.model_fields]

    assert template_sections == list(_EXPECTED_SECTIONS), (
        f"Template section order changed.\n"
        f"  template: {template_sections}\n"
        f"  expected: {list(_EXPECTED_SECTIONS)}"
    )
    assert config_attrs == list(_EXPECTED_SECTIONS), (
        f"Config attribute order changed.\n"
        f"  Config:   {config_attrs}\n"
        f"  expected: {list(_EXPECTED_SECTIONS)}"
    )
    assert set(template_sections) == set(config_attrs), (
        f"Template / Config section set mismatch.\n"
        f"  Only in template: {set(template_sections) - set(config_attrs)}\n"
        f"  Only in Config:   {set(config_attrs) - set(template_sections)}"
    )


def test_template_loads_into_default_config() -> None:
    """Parsing the shipped template through tomllib + Config.model_validate
    yields the same object as Config() — the template's literal values
    must equal the schema's default values."""
    if not _TEMPLATE_PATH.exists():
        pytest.skip(f"Template not found at {_TEMPLATE_PATH}")

    import tomllib

    template_dict = tomllib.loads(
        _TEMPLATE_PATH.read_text(encoding="utf-8")
    )
    parsed = Config.model_validate(template_dict)
    defaults = Config()
    assert parsed == defaults, (
        "Template's literal values diverge from Config's defaults; "
        "either the template or the schema has drifted."
    )


def test_section_count_is_seventeen() -> None:
    """Bible mapping for task 10 enumerates 17 sections exactly."""
    assert len(_EXPECTED_SECTIONS) == 17
    assert len(Config.model_fields) == 17
