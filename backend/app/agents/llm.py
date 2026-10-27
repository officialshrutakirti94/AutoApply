"""Provider-agnostic LLM access with fallback.

Both providers speak the OpenAI chat-completions shape, so one small client covers
Groq (fast, frequent) and NVIDIA Nemotron (resume parsing, harder answers). Model
names live in config, never in code.

Callers always tolerate failure: every task here can degrade to rules-only mode,
which is what keeps the product working with no API keys and no surprise bill.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.prompts import (
    SCREENING_ANSWER_SYSTEM,
    SCREENING_CLASSIFY_SYSTEM,
    build_answer_user,
    build_classify_user,
)

log = get_logger("llm")

TASK_RESUME_PARSE = "resume_parse"
TASK_CLASSIFY = "classify"
TASK_ANSWER = "answer"

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LlmUnavailable(RuntimeError):
    """No provider could answer. Callers must have a deterministic fallback."""


@dataclass(frozen=True, slots=True)
class LlmCall:
    text: str
    provider: str
    model: str
    task: str


@dataclass(frozen=True, slots=True)
class _Provider:
    name: str
    base_url: str
    api_key: str
    model: str


class _Retryable(Exception):
    pass


class _Fatal(Exception):
    pass


def available_providers(task: str) -> list[_Provider]:
    if not settings.llm_enabled:
        return []

    providers: list[_Provider] = []

    def add(name: str, base_url: str, api_key: str, model: str) -> None:
        if api_key and model:
            providers.append(_Provider(name=name, base_url=base_url.rstrip("/"), api_key=api_key, model=model))

    nemotron = (settings.nvidia_base_url, settings.nvidia_api_key, settings.nemotron_model)
    groq_fast = (GROQ_BASE_URL, settings.groq_api_key, settings.groq_model_fast)
    groq_small = (GROQ_BASE_URL, settings.groq_api_key, settings.groq_model_small)

    if task == TASK_CLASSIFY:
        add("groq-small", *groq_small)
        add("groq", *groq_fast)
        add("nvidia", *nemotron)
    elif task in {TASK_RESUME_PARSE, TASK_ANSWER}:
        add("nvidia", *nemotron)
        add("groq", *groq_fast)
    else:
        add("groq", *groq_fast)
        add("nvidia", *nemotron)

    return providers


def llm_available(task: str = TASK_ANSWER) -> bool:
    return bool(available_providers(task))


async def chat(
    task: str,
    *,
    system: str,
    user: str,
    json_mode: bool = False,
    temperature: float = 0.2,
    max_tokens: int = 900,
) -> LlmCall:
    providers = available_providers(task)
    if not providers:
        raise LlmUnavailable(f"No LLM provider configured for task '{task}'")

    failures: list[str] = []
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        for provider in providers:
            for attempt in range(settings.llm_max_retries + 1):
                try:
                    text = await _request(
                        client,
                        provider,
                        system=system,
                        user=user,
                        json_mode=json_mode,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    return LlmCall(text=text, provider=provider.name, model=provider.model, task=task)
                except _Retryable as exc:
                    failures.append(f"{provider.name}:{exc}")
                    if attempt < settings.llm_max_retries:
                        await asyncio.sleep(min(0.4 * (2**attempt), 4.0))
                except _Fatal as exc:
                    failures.append(f"{provider.name}:{exc}")
                    break

    log.warning("llm_all_providers_failed", task=task, failures=failures[-4:])
    raise LlmUnavailable("; ".join(failures[-2:]) or "all providers failed")


async def _request(
    client: httpx.AsyncClient,
    provider: _Provider,
    *,
    system: str,
    user: str,
    json_mode: bool,
    temperature: float,
    max_tokens: int,
) -> str:
    payload: dict = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = await client.post(
            f"{provider.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {provider.api_key}"},
            json=payload,
        )
    except httpx.HTTPError as exc:
        raise _Retryable(f"transport error ({type(exc).__name__})") from exc

    # Some hosted models reject response_format; retry once as plain text and let
    # the JSON extractor do the work.
    if response.status_code == 400 and json_mode:
        payload.pop("response_format", None)
        try:
            response = await client.post(
                f"{provider.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {provider.api_key}"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise _Retryable(f"transport error ({type(exc).__name__})") from exc

    if response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
        raise _Retryable(f"http {response.status_code}")
    if response.status_code >= 400:
        raise _Fatal(f"http {response.status_code}")

    try:
        data = response.json()
        text = data["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError) as exc:
        raise _Retryable("malformed completion") from exc

    text = text.strip()
    if not text:
        raise _Retryable("empty completion")
    return text


def extract_json(text: str) -> dict | None:
    """Pull a JSON object out of a completion that may be fenced or chatty."""
    candidate = text.strip()
    fenced = _JSON_FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        pass

    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def complete_json(
    task: str, *, system: str, user: str, max_tokens: int = 900
) -> dict | None:
    try:
        call = await chat(task, system=system, user=user, json_mode=True, max_tokens=max_tokens)
    except LlmUnavailable:
        return None
    return extract_json(call.text)


async def classify_question(question: str, options: list[str]) -> str | None:
    """Returns ``standard``, ``sensitive`` or ``unknown``; ``None`` means no provider."""
    result = await complete_json(
        TASK_CLASSIFY,
        system=SCREENING_CLASSIFY_SYSTEM,
        user=build_classify_user(question, options),
        max_tokens=60,
    )
    if not result:
        return None
    label = str(result.get("class") or "").strip().lower()
    return label if label in {"standard", "sensitive", "unknown"} else None


async def answer_screening_question(
    question: str, options: list[str], facts: dict
) -> str | None:
    result = await complete_json(
        TASK_ANSWER,
        system=SCREENING_ANSWER_SYSTEM,
        user=build_answer_user(question, options, facts),
        max_tokens=200,
    )
    if not result:
        return None
    answer = result.get("answer")
    if not isinstance(answer, str):
        return None
    answer = answer.strip()
    return answer or None


def provider_status() -> dict:
    return {
        "enabled": settings.llm_enabled,
        "resume_parse": [p.name for p in available_providers(TASK_RESUME_PARSE)],
        "classify": [p.name for p in available_providers(TASK_CLASSIFY)],
        "answer": [p.name for p in available_providers(TASK_ANSWER)],
        "max_calls_per_run": settings.llm_max_calls_per_run,
    }
