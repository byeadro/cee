"""Config schema — typed, schema-validated user configuration.

Authorized by System Design Bible section 04 §5.2 (canonical layout) and
§10.7 (regeneration semantics). Each nested section model is authorised by
the bible section called out in its docstring.

Structure: a top-level :class:`Config` model with one nested model per
``[section]`` in the rendered template at ``~/cee/.template/config.toml.default``.
The 1:1 correspondence between TOML headers and Config attribute names is
asserted by the bible-grounding test in ``test_config.py`` so future drift
is caught automatically.

Construction with no arguments produces a fully-valid Config because every
field carries a bible-mandated default. The loader (``config_loader.loader``)
calls :meth:`Config.model_validate` against the parsed TOML dict; missing
sections fall back to defaults.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Reused config dict — every section model is strict (extra="forbid") and
# strips whitespace from string fields, matching the convention in
# ~/cee/schemas/* established in tasks 8a–8c.
_SECTION_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=False,
    str_strip_whitespace=True,
)


# --------------------------------------------------------------------------- #
# Section models                                                              #
# --------------------------------------------------------------------------- #


class GeneralConfig(BaseModel):
    """``[general]`` — bible 04 §5.2."""

    model_config = _SECTION_MODEL_CONFIG

    auto_sync: bool = True
    fresh_boot: bool = False


class PathsConfig(BaseModel):
    """``[paths]`` — bible 04 §5.2.

    Path strings are stored verbatim; tilde expansion is the loader's
    concern, not this schema's. Validation only requires non-empty values.
    """

    model_config = _SECTION_MODEL_CONFIG

    cee_root: Annotated[str, Field(min_length=1)] = "~/cee"
    # The parent Obsidian vault root. Distinct from
    # :attr:`ObsidianConfig.vault_root` (the CEE-within-vault subdir);
    # both are bible-canonical and intentionally duplicated — see
    # bible 04 §5.2 (this field) and bible 13 §6.2 (the other).
    obsidian_vault: Annotated[str, Field(min_length=1)] = "~/SecondBrain"
    notion_bible_root_id: Annotated[str, Field(min_length=1)] = (
        "352e8536-d882-8050-aff6-f1dbcff68a09"
    )


class InterpreterConfig(BaseModel):
    """``[interpreter]`` — bible 04 §5.2 + bible 03 §5.2.

    Cross-validator: ``ambiguity_visible_threshold`` must be strictly
    less than ``ambiguity_clarification_threshold`` so the [visible,
    clarification) band remains a non-empty open interval.
    """

    model_config = _SECTION_MODEL_CONFIG

    ambiguity_clarification_threshold: Annotated[
        float, Field(ge=0.0, le=1.0)
    ] = 0.6
    ambiguity_visible_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.3

    @model_validator(mode="after")
    def _check_visible_below_clarification(self) -> "InterpreterConfig":
        if (
            self.ambiguity_visible_threshold
            >= self.ambiguity_clarification_threshold
        ):
            raise ValueError(
                "ambiguity_visible_threshold "
                f"({self.ambiguity_visible_threshold}) must be strictly less "
                "than ambiguity_clarification_threshold "
                f"({self.ambiguity_clarification_threshold}) per bible 03 §5.2"
            )
        return self


class ClassifierConfig(BaseModel):
    """``[classifier]`` — bible 08 §6.2."""

    model_config = _SECTION_MODEL_CONFIG

    ambiguity_halt_delta: Annotated[float, Field(ge=0.0, le=1.0)] = 0.10
    human_gate_for_destructive_irreversible: bool = True
    human_gate_for_external_effects: bool = True
    low_tier_escalation_strict: bool = True


class AgentSelectorConfig(BaseModel):
    """``[agent_selector]`` — bible 06 §6.3.

    Cross-validator: ``description_match_threshold`` must be strictly
    greater than ``generation_threshold`` so the "ask" zone (between
    them) is a non-empty open interval.
    """

    model_config = _SECTION_MODEL_CONFIG

    description_match_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.65
    generation_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.50
    recent_usage_bonus_window_days: Annotated[int, Field(ge=0)] = 30

    @model_validator(mode="after")
    def _check_match_above_generation(self) -> "AgentSelectorConfig":
        if self.description_match_threshold <= self.generation_threshold:
            raise ValueError(
                "description_match_threshold "
                f"({self.description_match_threshold}) must be strictly "
                "greater than generation_threshold "
                f"({self.generation_threshold}) per bible 06 §6.3 (the "
                "ask zone is the open interval between them)"
            )
        return self


class SkillEngineConfig(BaseModel):
    """``[skill_engine]`` — bible 04 §5.2 + bible 07 §6.3.

    Cross-validator: ``reuse_threshold`` must be strictly greater than
    ``ask_threshold`` so the three zones (reuse / ask / generate) are
    non-overlapping per bible 07 Rule 4.
    """

    model_config = _SECTION_MODEL_CONFIG

    reuse_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.85
    ask_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.60
    duplicate_levenshtein_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = (
        0.10
    )
    min_reuse_count_for_promotion_priority: Annotated[int, Field(ge=0)] = 3

    @model_validator(mode="after")
    def _check_reuse_above_ask(self) -> "SkillEngineConfig":
        if self.reuse_threshold <= self.ask_threshold:
            raise ValueError(
                f"reuse_threshold ({self.reuse_threshold}) must be strictly "
                f"greater than ask_threshold ({self.ask_threshold}) per "
                "bible 07 Rule 4 (zones must not overlap)"
            )
        return self


class SkillsConfig(BaseModel):
    """``[skills]`` — bible 15 §6.3."""

    model_config = _SECTION_MODEL_CONFIG

    max_body_words: Annotated[int, Field(ge=1)] = 1500
    max_total_lines: Annotated[int, Field(ge=1)] = 2000
    enforce_changelog_version_match: bool = True


class AgentsConfig(BaseModel):
    """``[agents]`` — bible 16 §6.3.

    Cross-validator: ``max_body_words_complex`` must be greater than or
    equal to ``max_body_words_simple`` so the "complex" tier is at least
    as permissive as "simple" (bible 16 §6.3).
    """

    model_config = _SECTION_MODEL_CONFIG

    max_body_words_simple: Annotated[int, Field(ge=1)] = 500
    max_body_words_complex: Annotated[int, Field(ge=1)] = 800
    enable_llm_body_validation: bool = False

    @model_validator(mode="after")
    def _check_complex_at_least_simple(self) -> "AgentsConfig":
        if self.max_body_words_complex < self.max_body_words_simple:
            raise ValueError(
                "max_body_words_complex "
                f"({self.max_body_words_complex}) must be >= "
                f"max_body_words_simple ({self.max_body_words_simple}) per "
                "bible 16 §6.3"
            )
        return self


class PromptBuilderConfig(BaseModel):
    """``[prompt_builder]`` — bible 09 §6.2."""

    model_config = _SECTION_MODEL_CONFIG

    safety_buffer_tokens: Annotated[int, Field(ge=0)] = 4000
    enable_role_smoothing: bool = True
    chunking_strategy: Literal["context_then_plan"] = "context_then_plan"


class OutputFormatConfig(BaseModel):
    """``[output_format]`` — bible 10 §6.3.

    Cross-validator: ``prose_long_max_words`` must be greater than or
    equal to ``prose_short_max_words`` so the long form is never
    capped tighter than the short form.
    """

    model_config = _SECTION_MODEL_CONFIG

    auto_rerun_on_hard_fail: bool = False
    acceptance_check_uses_llm: bool = True
    prose_short_max_words: Annotated[int, Field(ge=1)] = 500
    prose_long_max_words: Annotated[int, Field(ge=1)] = 5000

    @model_validator(mode="after")
    def _check_long_at_least_short(self) -> "OutputFormatConfig":
        if self.prose_long_max_words < self.prose_short_max_words:
            raise ValueError(
                f"prose_long_max_words ({self.prose_long_max_words}) must "
                f"be >= prose_short_max_words ({self.prose_short_max_words})"
            )
        return self


class GroundingConfig(BaseModel):
    """``[grounding]`` — bible 11 §6.2."""

    model_config = _SECTION_MODEL_CONFIG

    coverage_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.90
    auto_rerun_on_violation: bool = False
    acceptance_check_uses_llm: bool = True
    default_citation_format: Annotated[str, Field(min_length=1)] = (
        "inline_bracket"
    )


class SecurityConfig(BaseModel):
    """``[security]`` — bible 12 §6.2."""

    model_config = _SECTION_MODEL_CONFIG

    confirmation_timeout_hours: Annotated[int, Field(ge=0)] = 24
    notion_strict_redaction: bool = True
    obsidian_redaction_pass: bool = True
    audit_hash_chain: bool = True
    purge_raw_input_after_days: Annotated[int, Field(ge=0)] = 90


class ObsidianConfig(BaseModel):
    """``[obsidian]`` — bible 13 §6.2.

    The :attr:`vault_root` field is the CEE-within-vault subdir, distinct
    from :attr:`PathsConfig.obsidian_vault` (the parent vault root).
    Both are bible-canonical and intentionally duplicated.
    """

    model_config = _SECTION_MODEL_CONFIG

    vault_root: Annotated[str, Field(min_length=1)] = "~/SecondBrain/cee"
    enable_daily_sync: bool = False
    regenerate_indexes_on_run: bool = False
    preserve_manual_edits: bool = True


class ClaudeCodeConfig(BaseModel):
    """``[claude_code]`` — bible 14 §6.4."""

    model_config = _SECTION_MODEL_CONFIG

    claude_md_auto_sync: bool = False
    hooks_installed: bool = False
    slash_commands_installed: bool = False


class ExecutorConfig(BaseModel):
    """``[executor]`` — bible 04 §5.2."""

    model_config = _SECTION_MODEL_CONFIG

    default_target: Literal["claude_code", "claude_ai", "api"] = "claude_code"


class Phase2Config(BaseModel):
    """``[phase2]`` — bible 04 §5.2 + bible 14 Rule 10."""

    model_config = _SECTION_MODEL_CONFIG

    api_enabled: bool = False
    api_model: Annotated[str, Field(min_length=1)] = "claude-opus-4-7"


class ErrorsConfig(BaseModel):
    """``[errors]`` — bible 19 §6.2."""

    model_config = _SECTION_MODEL_CONFIG

    verbose_messages: bool = True
    auto_open_run_dir_on_halt: bool = False
    treat_warnings_as_errors: bool = False


# --------------------------------------------------------------------------- #
# Top-level Config                                                            #
# --------------------------------------------------------------------------- #


class Config(BaseModel):
    """The full ``~/.cee/config.toml`` document.

    Section order matches the rendered template at
    ``~/cee/.template/config.toml.default`` (bible 04 §5.2 first, then
    pipeline-stage sections in pipeline order, then external integrations,
    then operational tail). The bible-grounding test asserts the section
    set in this model matches the headers parsed from the template.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    interpreter: InterpreterConfig = Field(default_factory=InterpreterConfig)
    classifier: ClassifierConfig = Field(default_factory=ClassifierConfig)
    agent_selector: AgentSelectorConfig = Field(
        default_factory=AgentSelectorConfig
    )
    skill_engine: SkillEngineConfig = Field(default_factory=SkillEngineConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    prompt_builder: PromptBuilderConfig = Field(
        default_factory=PromptBuilderConfig
    )
    output_format: OutputFormatConfig = Field(
        default_factory=OutputFormatConfig
    )
    grounding: GroundingConfig = Field(default_factory=GroundingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    claude_code: ClaudeCodeConfig = Field(default_factory=ClaudeCodeConfig)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    phase2: Phase2Config = Field(default_factory=Phase2Config)
    errors: ErrorsConfig = Field(default_factory=ErrorsConfig)
