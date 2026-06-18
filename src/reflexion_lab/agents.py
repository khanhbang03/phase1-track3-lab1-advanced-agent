from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from .mock_runtime import FAILURE_MODE_BY_QID, canonical_qid
from .runtime import AgentRuntime, MockRuntime
from .schemas import AttemptTrace, QAExample, ReflectionEntry, RunRecord

def _estimate_tokens(*parts: str) -> int:
    """Deterministic fallback for runtimes that do not expose token usage."""
    text = "\n".join(parts)
    return max(1, (len(text) + 3) // 4)

@dataclass
class BaseAgent:
    agent_type: Literal["react", "reflexion"]
    max_attempts: int = 1
    runtime: AgentRuntime = field(default_factory=MockRuntime)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

    def run(self, example: QAExample) -> RunRecord:
        reflection_memory: list[str] = []
        reflections: list[ReflectionEntry] = []
        traces: list[AttemptTrace] = []
        final_answer = ""
        final_score = 0
        for attempt_id in range(1, self.max_attempts + 1):
            actor_result = self.runtime.actor(example, attempt_id, self.agent_type, reflection_memory)
            answer = actor_result.value
            judge_result = self.runtime.evaluator(example, answer)
            judge = judge_result.value
            latency_ms = actor_result.latency_ms + judge_result.latency_ms
            context_text = "\n".join(f"{chunk.title}: {chunk.text}" for chunk in example.context)
            measured_tokens = [
                count for count in (actor_result.token_count, judge_result.token_count) if count is not None
            ]
            token_estimate = sum(measured_tokens) if measured_tokens else _estimate_tokens(
                    example.question,
                    context_text,
                    *reflection_memory,
                    answer,
                    judge.reason,
                    *judge.missing_evidence,
                    *judge.spurious_claims,
                )
            reflection: ReflectionEntry | None = None
            final_answer = answer
            final_score = judge.score
            if judge.score == 0 and self.agent_type == "reflexion" and attempt_id < self.max_attempts:
                reflection_result = self.runtime.reflector(example, attempt_id, judge)
                reflection = reflection_result.value
                reflections.append(reflection)
                reflection_memory.append(
                    f"Attempt {attempt_id}: {reflection.lesson} Next strategy: {reflection.next_strategy}"
                )
                latency_ms += reflection_result.latency_ms
                token_estimate += (
                    reflection_result.token_count
                    if reflection_result.token_count is not None
                    else _estimate_tokens(
                        reflection.failure_reason,
                        reflection.lesson,
                        reflection.next_strategy,
                    )
                )
            trace = AttemptTrace(
                attempt_id=attempt_id,
                answer=answer,
                score=judge.score,
                reason=judge.reason,
                reflection=reflection,
                token_estimate=token_estimate,
                latency_ms=latency_ms,
            )
            traces.append(trace)
            if judge.score == 1:
                break
        total_tokens = sum(t.token_estimate for t in traces)
        total_latency = sum(t.latency_ms for t in traces)
        failure_mode = "none" if final_score == 1 else FAILURE_MODE_BY_QID.get(canonical_qid(example.qid), "wrong_final_answer")
        return RunRecord(qid=example.qid, question=example.question, gold_answer=example.gold_answer, agent_type=self.agent_type, predicted_answer=final_answer, is_correct=bool(final_score), attempts=len(traces), token_estimate=total_tokens, latency_ms=total_latency, failure_mode=failure_mode, reflections=reflections, traces=traces)

class ReActAgent(BaseAgent):
    def __init__(self, runtime: AgentRuntime | None = None) -> None:
        super().__init__(agent_type="react", max_attempts=1, runtime=runtime or MockRuntime())

class ReflexionAgent(BaseAgent):
    def __init__(self, max_attempts: int = 3, runtime: AgentRuntime | None = None) -> None:
        super().__init__(agent_type="reflexion", max_attempts=max_attempts, runtime=runtime or MockRuntime())
