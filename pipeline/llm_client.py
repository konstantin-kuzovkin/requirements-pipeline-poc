"""
LLMClient abstraction used by agents 1, 2 and 4b.

There are two implementations on purpose:

- AnthropicLLMClient: a real client. Requires `pip install anthropic` and an
  ANTHROPIC_API_KEY environment variable. This is what you run locally to
  get real agent output and real evaluation numbers.

- FixtureLLMClient: a offline, no-network replay client used by demo.py and
  the tests in this sandbox. It returns pre-recorded YAML strings keyed by
  a lookup you provide. It never calls a model. Anything it returns is
  clearly a fixture, not a live model output -- do not read fixture
  content as evidence of model quality. Its only job is to let the
  orchestration and validation logic be exercised end to end without
  network access.
"""
from __future__ import annotations

import os
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_content: str) -> str:
        """Return the model's raw text response (expected to be one YAML document)."""
        ...


class AnthropicLLMClient:
    """Real client. Not used inside this sandbox (no network here) -- run it
    on your own machine with `pip install anthropic` and a real API key."""

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 2000):
        try:
            import anthropic  # noqa: F401  (imported lazily so the rest of the
            # package works even where the SDK is not installed, e.g. this sandbox)
        except ImportError as e:
            raise RuntimeError(
                "pip install anthropic  # then set ANTHROPIC_API_KEY and retry"
            ) from e
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("Set the ANTHROPIC_API_KEY environment variable.")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system_prompt: str, user_content: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class FixtureLLMClient:
    """
    Offline replay client for demos and tests run without network access.

    Implements the same `.complete(system_prompt, user_content)` interface
    as AnthropicLLMClient, so agents never know they are talking to a
    fixture. Responses are consumed in the order they were recorded --
    this mirrors the fixed call order of the pipeline (discovery once,
    requirements once, one pairwise check per candidate pair) and needs no
    prompt matching. Calling complete() more times than there are recorded
    responses raises, so a code path with no recorded example is never
    silently skipped.

    Every response returned here is a recorded fixture, written by hand for
    this PoC to exercise the parsing and validation logic -- it is NOT live
    model output and must not be read as evidence of model quality.
    """

    def __init__(self, responses: list[str]):
        self._queue = list(responses)
        self.calls_made = 0

    def complete(self, system_prompt: str, user_content: str) -> str:
        if not self._queue:
            raise RuntimeError(
                f"FixtureLLMClient exhausted after {self.calls_made} call(s); "
                "no more recorded responses for this run."
            )
        self.calls_made += 1
        return self._queue.pop(0)
