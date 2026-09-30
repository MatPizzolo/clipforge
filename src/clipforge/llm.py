"""LLM client for highlight selection (ADR-4). Stages depend on the `LLMClient` protocol, so
tests use a fake and the Anthropic SDK stays at the edge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from clipforge.pipeline.errors import PermanentError


@dataclass(frozen=True)
class LLMReply:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMClient(Protocol):
    model: str

    def complete(self, messages: list[dict[str, str]], max_tokens: int = 2048) -> LLMReply: ...


class AnthropicClient:
    """Messages API via the official SDK (which retries 429/5xx itself before raising)."""

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self.model = model
        self._client: Any = client or anthropic.Anthropic(
            api_key=api_key, max_retries=3, timeout=120.0
        )

    def complete(self, messages: list[dict[str, str]], max_tokens: int = 2048) -> LLMReply:
        try:
            response = self._client.messages.create(
                model=self.model, max_tokens=max_tokens, messages=messages
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise PermanentError("the Anthropic API key was rejected") from exc
        except anthropic.NotFoundError as exc:
            raise PermanentError(f"the LLM model {self.model!r} is not available") from exc
        except anthropic.BadRequestError as exc:
            raise PermanentError(f"the LLM rejected the request: {exc.message}") from exc
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMReply(
            text=text,
            input_tokens=int(response.usage.input_tokens),
            output_tokens=int(response.usage.output_tokens),
            model=self.model,
        )
