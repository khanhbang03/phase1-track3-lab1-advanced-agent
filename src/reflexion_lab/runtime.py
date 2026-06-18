from __future__ import annotations

import json
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Generic, Protocol, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import mock_runtime
from .prompts import ACTOR_SYSTEM, EVALUATOR_SYSTEM, REFLECTOR_SYSTEM
from .schemas import JudgeResult, QAExample, ReflectionEntry

T = TypeVar("T")


@dataclass(frozen=True)
class RuntimeResult(Generic[T]):
    value: T
    token_count: int | None
    latency_ms: int


class AgentRuntime(Protocol):
    mode: str

    def actor(
        self,
        example: QAExample,
        attempt_id: int,
        agent_type: str,
        reflection_memory: list[str],
    ) -> RuntimeResult[str]: ...

    def evaluator(self, example: QAExample, answer: str) -> RuntimeResult[JudgeResult]: ...

    def reflector(
        self,
        example: QAExample,
        attempt_id: int,
        judge: JudgeResult,
    ) -> RuntimeResult[ReflectionEntry]: ...


class MockRuntime:
    mode = "mock"

    @staticmethod
    def _timed(call, *args) -> RuntimeResult:
        started = perf_counter()
        value = call(*args)
        return RuntimeResult(
            value=value,
            token_count=None,
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
        )

    def actor(
        self,
        example: QAExample,
        attempt_id: int,
        agent_type: str,
        reflection_memory: list[str],
    ) -> RuntimeResult[str]:
        return self._timed(
            mock_runtime.actor_answer,
            example,
            attempt_id,
            agent_type,
            reflection_memory,
        )

    def evaluator(self, example: QAExample, answer: str) -> RuntimeResult[JudgeResult]:
        return self._timed(mock_runtime.evaluator, example, answer)

    def reflector(
        self,
        example: QAExample,
        attempt_id: int,
        judge: JudgeResult,
    ) -> RuntimeResult[ReflectionEntry]:
        return self._timed(mock_runtime.reflector, example, attempt_id, judge)


class OpenAICompatibleRuntime:
    """Minimal chat-completions client for OpenAI-compatible hosted/local APIs."""

    mode = "llm"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 120,
    ) -> None:
        self.model = model or os.getenv("LLM_MODEL", "")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        self.timeout_s = timeout_s
        if not self.model:
            raise ValueError("LLM model is required; set --model or LLM_MODEL")

    def _chat(self, system: str, user: str, *, json_mode: bool) -> RuntimeResult[str]:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system.strip()},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        started = perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach LLM API at {self.base_url}: {exc.reason}") from exc
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM response did not contain choices[0].message.content") from exc
        token_count = body.get("usage", {}).get("total_tokens")
        return RuntimeResult(value=content.strip(), token_count=token_count, latency_ms=latency_ms)

    @staticmethod
    def _context(example: QAExample) -> str:
        return "\n\n".join(f"[{chunk.title}]\n{chunk.text}" for chunk in example.context)

    @staticmethod
    def _json_object(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            cleaned = cleaned.removesuffix("```").strip()
        value = json.loads(cleaned)
        if not isinstance(value, dict):
            raise ValueError("structured LLM output must be a JSON object")
        return value

    def actor(
        self,
        example: QAExample,
        attempt_id: int,
        agent_type: str,
        reflection_memory: list[str],
    ) -> RuntimeResult[str]:
        memory = "\n".join(f"- {item}" for item in reflection_memory) or "(none)"
        user = (
            f"Question: {example.question}\n\nContext:\n{self._context(example)}\n\n"
            f"Previous reflections:\n{memory}\n\nAttempt: {attempt_id}; agent: {agent_type}"
        )
        return self._chat(ACTOR_SYSTEM, user, json_mode=False)

    def evaluator(self, example: QAExample, answer: str) -> RuntimeResult[JudgeResult]:
        result = self._chat(
            EVALUATOR_SYSTEM,
            f"Question: {example.question}\nReference answer: {example.gold_answer}\nPredicted answer: {answer}",
            json_mode=True,
        )
        return RuntimeResult(
            value=JudgeResult.model_validate(self._json_object(result.value)),
            token_count=result.token_count,
            latency_ms=result.latency_ms,
        )

    def reflector(
        self,
        example: QAExample,
        attempt_id: int,
        judge: JudgeResult,
    ) -> RuntimeResult[ReflectionEntry]:
        result = self._chat(
            REFLECTOR_SYSTEM,
            (
                f"Question: {example.question}\nAttempt id: {attempt_id}\n"
                f"Evaluator diagnosis: {judge.model_dump_json()}\nContext:\n{self._context(example)}"
            ),
            json_mode=True,
        )
        payload = self._json_object(result.value)
        payload["attempt_id"] = attempt_id
        return RuntimeResult(
            value=ReflectionEntry.model_validate(payload),
            token_count=result.token_count,
            latency_ms=result.latency_ms,
        )
