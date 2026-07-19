"""LLM generation backends. Same Embedder-style split: an interface plus a
Groq implementation for fast/free iteration, and a Bedrock (Claude)
implementation with the identical call shape for the production swap.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

SYSTEM_PROMPT = """Du bist der Vermio-Assistent für deutsches Mietrecht \
(Betriebskosten, Kaution). Du beantwortest Fragen AUSSCHLIESSLICH auf Basis \
der bereitgestellten Quellenausschnitte.

Regeln:
1. Jede sachliche Aussage muss durch eine Quelle im Kontext gedeckt sein. \
Zitiere die Quelle in eckigen Klammern, z. B. [BGB §551 Abs. 1].
2. Wenn die bereitgestellten Quellen die Frage nicht (oder nur teilweise) \
beantworten, sage das explizit — erfinde keine Paragraphen oder Fristen.
3. Antworte auf Deutsch, präzise, ohne Rechtsberatung im Einzelfall zu \
suggerieren (füge bei komplexeren Fällen den Hinweis "im Zweifel anwaltlich \
prüfen lassen" an).
"""

USER_TEMPLATE = """Frage: {question}

Quellen:
{context}

Beantworte die Frage ausschließlich anhand der obigen Quellen."""


@dataclass
class GenerationResult:
    answer: str
    latency_ms: float
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class Generator(ABC):
    @abstractmethod
    def generate(self, question: str, context_blocks: list[str]) -> GenerationResult: ...

    @staticmethod
    def _format_context(context_blocks: list[str]) -> str:
        return "\n\n---\n\n".join(context_blocks)


class GroqGenerator(Generator):
    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        from groq import Groq

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set — see .env.example")
        self._client = Groq(api_key=api_key)
        self._model = model

    def generate(self, question: str, context_blocks: list[str]) -> GenerationResult:
        t0 = time.perf_counter()
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=0.0,  # deterministic — this is a legal Q&A tool, not a creative one
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_TEMPLATE.format(
                    question=question, context=self._format_context(context_blocks)
                )},
            ],
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        usage = resp.usage
        return GenerationResult(
            answer=resp.choices[0].message.content,
            latency_ms=latency_ms,
            model=self._model,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )


class BedrockGenerator(Generator):
    """Claude on Bedrock via the Messages API shape. Same SYSTEM_PROMPT /
    USER_TEMPLATE as Groq — only the transport differs, which is the point:
    the prompt and the eval harness in eval.py don't need to change when you
    swap providers, only this class does."""

    def __init__(self, model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0", region: str = "eu-central-1"):
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id

    def generate(self, question: str, context_blocks: list[str]) -> GenerationResult:
        import json

        t0 = time.perf_counter()
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "temperature": 0.0,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": USER_TEMPLATE.format(
                question=question, context=self._format_context(context_blocks)
            )}],
        })
        resp = self._client.invoke_model(modelId=self._model_id, body=body)
        payload = json.loads(resp["body"].read())
        latency_ms = (time.perf_counter() - t0) * 1000
        return GenerationResult(
            answer=payload["content"][0]["text"],
            latency_ms=latency_ms,
            model=self._model_id,
            prompt_tokens=payload.get("usage", {}).get("input_tokens"),
            completion_tokens=payload.get("usage", {}).get("output_tokens"),
        )
