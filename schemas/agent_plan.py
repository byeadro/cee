"""AgentPlan artifact schema.

Authorized by System Design Bible section 06 §7.1. Produced by AGENT_SELECTOR
from a Classification + IntentObject; persisted at
``~/cee/runs/<run_id>/agents.json``. Tier-based agent count caps (LOW=1,
MEDIUM=1–2, HIGH=3, EXTREME=4+) are runtime constraints applied by
AGENT_SELECTOR, not enforced here.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from roles import RoleEnum

# Bible 15 §5.1: kebab-case ASCII, 3–60 chars, starts with letter,
# ends with letter or digit. Same regex applies to agent slugs (bible 06 §11
# delegates slug rules to the shared kebab-case convention).
_KEBAB_CASE_PATTERN = r"^[a-z][a-z0-9-]{1,58}[a-z0-9]$"

Posture = Literal["primary", "critic", "optimizer", "orchestrator", "specialist"]


class AgentRef(BaseModel):
    """A single agent referenced by an AgentPlan.

    Per bible 06 §5.1: posture is one of the five closed values. The agent
    file lives at ``~/cee/.claude/agents/<slug>.md``; ``path`` is the file
    location. ``generated_in_run`` is True when AGENT_SELECTOR generated
    this agent in the current Run (bible 06 §5.5); review status lives in
    the agent file's frontmatter, not here.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    slug: Annotated[str, Field(pattern=_KEBAB_CASE_PATTERN)]
    posture: Posture
    path: Annotated[str, Field(min_length=1)]
    generated_in_run: bool = False


class AgentPlan(BaseModel):
    """The selected set of agents for the Run.

    Per bible 06 §7.1. Validators enforce: at least one agent in the list
    (a Run cannot proceed without a lead); at least one agent has
    posture in {primary, orchestrator} (bible Rule 2 — there is exactly
    one primary; on EXTREME the orchestrator coordinates and a primary still
    exists, so the lead may be either). Tier-based count caps are applied
    by AGENT_SELECTOR at runtime, not validated here.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    agents: Annotated[list[AgentRef], Field(min_length=1)]
    coordination: Annotated[str, Field(min_length=1)]
    produced_by: RoleEnum = RoleEnum.AGENT_SELECTOR

    @model_validator(mode="after")
    def _check_has_lead(self) -> "AgentPlan":
        leads = {"primary", "orchestrator"}
        if not any(agent.posture in leads for agent in self.agents):
            raise ValueError(
                "AgentPlan must contain at least one agent with posture "
                "'primary' or 'orchestrator'"
            )
        return self
