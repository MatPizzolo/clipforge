import os
from types import SimpleNamespace as NS
from typing import Any

import anthropic
import httpx2
import pytest

from clipforge.llm import AnthropicClient
from clipforge.pipeline.errors import PermanentError


class StubMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response, self.error = response, error
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response


def reply(text: str) -> NS:
    return NS(
        content=[NS(type="text", text=text)],
        usage=NS(input_tokens=1200, output_tokens=80),
        stop_reason="end_turn",
    )


def api_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


def client_with(messages: StubMessages) -> AnthropicClient:
    return AnthropicClient(api_key="x", model="claude-haiku-4-5", client=NS(messages=messages))


def test_complete_returns_text_and_usage() -> None:
    stub = StubMessages(response=reply('{"clips": []}'))
    out = client_with(stub).complete([{"role": "user", "content": "hi"}], max_tokens=100)
    assert (out.text, out.input_tokens, out.output_tokens) == ('{"clips": []}', 1200, 80)
    assert out.model == "claude-haiku-4-5"
    assert stub.kwargs["model"] == "claude-haiku-4-5" and stub.kwargs["max_tokens"] == 100


@pytest.mark.parametrize(
    ("cls", "status"),
    [
        (anthropic.AuthenticationError, 401),
        (anthropic.PermissionDeniedError, 403),
        (anthropic.NotFoundError, 404),
        (anthropic.BadRequestError, 400),
    ],
)
def test_configuration_errors_are_permanent(
    cls: type[anthropic.APIStatusError], status: int
) -> None:
    with pytest.raises(PermanentError):
        client_with(StubMessages(error=api_error(cls, status))).complete([])


def test_rate_limits_propagate_for_the_step_to_retry() -> None:
    with pytest.raises(anthropic.RateLimitError):
        client_with(StubMessages(error=api_error(anthropic.RateLimitError, 429))).complete([])


@pytest.mark.slow
def test_real_haiku_call() -> None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    out = AnthropicClient(api_key=key, model="claude-haiku-4-5").complete(
        [
            {
                "role": "user",
                "content": 'Reply with exactly this JSON and nothing else: {"ok": true}',
            }
        ],
        max_tokens=50,
    )
    assert '"ok"' in out.text and out.input_tokens > 0 and out.output_tokens > 0
