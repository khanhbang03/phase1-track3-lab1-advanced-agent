from __future__ import annotations
from typing import Literal, Optional, TypedDict
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    """Shared validation so malformed runtime output fails early and clearly."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class ContextChunk(StrictModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)

class QAExample(StrictModel):
    qid: str = Field(min_length=1)
    difficulty: Literal["easy", "medium", "hard"]
    question: str = Field(min_length=1)
    gold_answer: str = Field(min_length=1)
    context: list[ContextChunk] = Field(min_length=1)

class JudgeResult(StrictModel):
    score: Literal[0, 1]
    reason: str = Field(min_length=1)
    missing_evidence: list[str] = Field(default_factory=list)
    spurious_claims: list[str] = Field(default_factory=list)

class ReflectionEntry(StrictModel):
    attempt_id: int = Field(ge=1)
    failure_reason: str = Field(min_length=1)
    lesson: str = Field(min_length=1)
    next_strategy: str = Field(min_length=1)

class AttemptTrace(StrictModel):
    attempt_id: int = Field(ge=1)
    answer: str
    score: Literal[0, 1]
    reason: str = Field(min_length=1)
    reflection: Optional[ReflectionEntry] = None
    token_estimate: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)

class RunRecord(StrictModel):
    qid: str = Field(min_length=1)
    question: str = Field(min_length=1)
    gold_answer: str = Field(min_length=1)
    agent_type: Literal["react", "reflexion"]
    predicted_answer: str
    is_correct: bool
    attempts: int = Field(ge=1)
    token_estimate: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    failure_mode: Literal["none", "entity_drift", "incomplete_multi_hop", "wrong_final_answer", "looping", "reflection_overfit"]
    reflections: list[ReflectionEntry] = Field(default_factory=list)
    traces: list[AttemptTrace] = Field(default_factory=list)

    @field_validator("traces")
    @classmethod
    def traces_must_not_be_empty(cls, value: list[AttemptTrace]) -> list[AttemptTrace]:
        if not value:
            raise ValueError("a run record must contain at least one attempt trace")
        return value

class ReportPayload(StrictModel):
    meta: dict
    summary: dict
    failure_modes: dict
    examples: list[dict]
    extensions: list[str]
    discussion: str

class ReflexionState(TypedDict):
    question: str
    context: list[str]
    trajectory: list[str]
    reflection_memory: list[str]
    attempt_count: int
    success: bool
    final_answer: str
