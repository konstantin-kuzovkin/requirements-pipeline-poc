"""Agent 3 -- combines 3a (deterministic) and 3b (LLM) into one artifacts.yaml."""
from __future__ import annotations

from . import agent3a_deterministic, agent3b_llm_diagrams
from .llm_client import LLMClient


def run(discovery: dict, requirements: dict, llm_client: LLMClient) -> dict:
    deterministic = agent3a_deterministic.run(discovery, requirements)
    llm_part = agent3b_llm_diagrams.run(llm_client, requirements, deterministic)
    return {**deterministic, **llm_part}
