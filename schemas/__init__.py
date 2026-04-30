"""CEE artifact schemas.

Re-exports the seven core pipeline artifact models from bible task 8a:
``RawInput``, ``IntentObject``, ``Classification``, ``AgentPlan``,
``SkillSet``, ``ExecutionStrategy``, and ``FinalPrompt``, plus their
nested sub-models.

Task 8b adds three satellite artifacts:

* ``ClarificationRequest`` (with nested ``ClarificationQuestion``) —
  emitted by INTERPRETER on ``paused_for_clarification`` halts.
* ``RunErrorArtifact`` — the on-disk ``error.json`` written when a Run
  fails terminally. Re-exported under the alias ``RunErrorArtifact`` to
  avoid colliding with the exception class :class:`cee.errors.RunError`
  (bible 19 §5.7); both can coexist, one is the persisted data and the
  other is the runtime signal.
* ``RunSummary`` — the ``summary.json`` finalize artifact.

Task 8c adds four sub-structure schemas (frontmatter blocks and
prompt-tag declarations):

* ``SkillFrontmatter`` — YAML frontmatter at the top of a Skill file
  (bible 15 §5.2).
* ``AgentFrontmatter`` — YAML frontmatter at the top of an agent file
  (bible 06 §5.2.1).
* ``GroundingDeclaration`` (with nested ``Source``) — contents of the
  FinalPrompt's ``<grounding_rules>`` tag (bible 11 §5.4).
* ``FormatDeclaration`` — contents of the FinalPrompt's
  ``<output_format>`` tag (bible 10 §5.6).
"""

from schemas.agent_frontmatter import AgentFrontmatter
from schemas.agent_plan import AgentPlan, AgentRef
from schemas.clarification_request import (
    ClarificationQuestion,
    ClarificationRequest,
)
from schemas.classification import (
    CandidateScore,
    Classification,
    ClassificationAudit,
    ClassificationFlags,
    ComplexityComponents,
    FlagTriggers,
)
from schemas.execution_strategy import ExecutionStrategy, StepSpec
from schemas.final_prompt import (
    AgentEntry,
    Agents,
    AssumptionsMade,
    AttachmentSummary,
    Chunking,
    Context,
    ExecutionPlan,
    FinalPrompt,
    GroundingRules,
    OutputFormat,
    PlanStep,
    RunMetadata,
    SkillEntry,
    Skills,
    StopConditions,
)
from schemas.format_declaration import FormatDeclaration
from schemas.grounding_declaration import GroundingDeclaration, Source
from schemas.intent_object import IntentObject
from schemas.raw_input import Attachment, RawInput
# Aliased to avoid colliding with cee.errors.RunError (the exception class).
# The schema models the on-disk ``error.json`` artifact (bible 03 §7.3 /
# bible 19 §5.5); the exception class signals the failure at runtime.
from schemas.run_error import RunError as RunErrorArtifact
from schemas.run_summary import RunSummary
from schemas.skill_frontmatter import SkillFrontmatter
from schemas.skill_set import SkillRef, SkillSet

__all__ = [
    # Top-level artifact models — task 8a
    "RawInput",
    "IntentObject",
    "Classification",
    "AgentPlan",
    "SkillSet",
    "ExecutionStrategy",
    "FinalPrompt",
    # Top-level artifact models — task 8b
    "ClarificationRequest",
    "RunErrorArtifact",
    "RunSummary",
    # Top-level sub-structure models — task 8c
    "SkillFrontmatter",
    "AgentFrontmatter",
    "GroundingDeclaration",
    "FormatDeclaration",
    # Nested — RawInput
    "Attachment",
    # Nested — Classification
    "ComplexityComponents",
    "ClassificationFlags",
    "CandidateScore",
    "FlagTriggers",
    "ClassificationAudit",
    # Nested — AgentPlan
    "AgentRef",
    # Nested — SkillSet
    "SkillRef",
    # Nested — ExecutionStrategy
    "StepSpec",
    # Nested — FinalPrompt
    "Context",
    "AttachmentSummary",
    "ExecutionPlan",
    "PlanStep",
    "OutputFormat",
    "StopConditions",
    "RunMetadata",
    "Agents",
    "AgentEntry",
    "Skills",
    "SkillEntry",
    "GroundingRules",
    "AssumptionsMade",
    "Chunking",
    # Nested — ClarificationRequest
    "ClarificationQuestion",
    # Nested — GroundingDeclaration
    "Source",
]
