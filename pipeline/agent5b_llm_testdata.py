"""
Agent 5b -- LLM-assisted test data and edge cases. Genuine judgment needed:
concrete realistic values, and boundary/negative cases beyond the literal
acceptance criteria (the deterministic layer in agent5a can't invent "what
if the amount is exactly at the threshold" -- that requires understanding
what's *interesting* about a threshold, not just transcribing structure).
"""
from __future__ import annotations

import yaml

from .llm_client import LLMClient
from .yaml_io import parse_llm_yaml

SCHEMA_TEXT = """
llm_tests:
  example_data:
    - test_id: "TC-001"
      data: {employee_id: "EMP-1042", amount: "612.40", currency: "USD", category: "travel"}
  edge_cases:
    - id: "TC-201"
      type: EDGE | NEGATIVE
      covers: ["FR-002"]
      given: string
      when: string
      then: string
      reason: string
"""

SYSTEM_PROMPT = f"""You are the Test Designer Agent (LLM half). You are given validated
requirements and a set of already-generated deterministic test case
skeletons. Produce ONLY a YAML document matching the schema below.

Schema:
{SCHEMA_TEXT}

Rules:
- For `example_data`: invent realistic, concrete example values for each
  deterministic test case's `given`/`when` fields (e.g. actual amounts,
  IDs, categories) -- these are illustrative examples, not real user data.
  Every test_id must match an id that exists in the deterministic test
  list given to you.
- For `edge_cases`: propose additional boundary and negative cases the
  deterministic list does not already cover -- e.g. a value exactly at a
  stated threshold, a value one unit below/above it, an empty/missing
  required field, a duplicate submission. Every edge case's `covers` must
  cite an FR, NFR, or entity id that exists in the given requirements. Do
  not invent a business rule that is not implied by the requirements -- if
  a genuinely useful edge case cannot be derived from anything given, do
  not include it.
- Give a one-sentence `reason` for every edge case: why this is worth
  testing, not just that it exists.
"""


def build_user_content(requirements: dict, deterministic_tests: dict) -> str:
    req_yaml = yaml.safe_dump(requirements, sort_keys=False, allow_unicode=True)
    tests_yaml = yaml.safe_dump(deterministic_tests, sort_keys=False, allow_unicode=True)
    return (
        f"Requirements:\n{req_yaml}\n\n"
        f"Deterministic test skeletons:\n{tests_yaml}\n\n"
        "Output the YAML now."
    )


def run(llm_client: LLMClient, requirements: dict, deterministic_tests: dict) -> dict:
    response_text = llm_client.complete(
        SYSTEM_PROMPT, build_user_content(requirements, deterministic_tests)
    )
    data = parse_llm_yaml(response_text)
    if "llm_tests" not in data:
        raise ValueError("Agent 5b response missing top-level 'llm_tests' key")
    return data
