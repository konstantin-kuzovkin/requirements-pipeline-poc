"""Agent 5 -- combines 5a (deterministic) and 5b (LLM) into one test document."""
from __future__ import annotations

from . import agent5a_deterministic, agent5b_llm_testdata
from .llm_client import LLMClient


def run(requirements: dict, llm_client: LLMClient) -> dict:
    deterministic = agent5a_deterministic.run(requirements)
    llm_part = agent5b_llm_testdata.run(llm_client, requirements, deterministic)
    return {**deterministic, **llm_part}
