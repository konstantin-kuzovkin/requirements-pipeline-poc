"""
Agent 1 -- Discovery.

Reads a raw business request, produces stakeholders / scope / assumptions /
open questions / glossary as one YAML document. See
agent-pipeline-design.md section 3 for the full schema and rationale.
"""
from __future__ import annotations

from .llm_client import LLMClient
from .yaml_io import parse_llm_yaml

SCHEMA_TEXT = """
discovery:
  project_name: string
  raw_request: string
  stakeholders:
    - id: "STK-01"
      name: string
      interest: string
      marker: FACT | INFERENCE
      reason: string            # required if marker == INFERENCE
  scope:
    in_scope: [string]
    out_scope: [string]
  assumptions:
    - id: "ASM-01"
      text: string
      marker: INFERENCE
      reason: string
  open_questions:
    - id: "OQ-01"
      question: string
      why_it_matters: string
  glossary:
    - term: string
      definition: string
      marker: FACT | INFERENCE
"""

SYSTEM_PROMPT = f"""You are the Discovery Agent in a requirements-engineering pipeline.
Read the raw business request and produce ONLY a YAML document matching
the Discovery Output schema below. No text before or after the YAML.

Schema:
{SCHEMA_TEXT}

Rules:
- Every stakeholder, assumption, and glossary term is marked FACT (stated
  explicitly in the request) or INFERENCE (a reasonable deduction you are
  making -- you must give a one-clause reason). Never mark something FACT
  if it is not literally stated.
- Do not invent stakeholders, business rules, thresholds, or numbers that
  are not in the request and not a clearly labeled inference.
- If something is unclear or missing, put it in open_questions. Do not
  guess a value to fill a field instead.
- Every open question must state which future requirement area it blocks
  (why_it_matters), not just that something is unclear.
- If the request is unambiguous on a point, do not manufacture a question
  about it just to have more questions.
- IDs are sequential per section: STK-01, STK-02, ... ASM-01, ... OQ-01, ...
"""


def build_user_content(raw_request: str) -> str:
    return f"Raw request:\n{raw_request}\n\nOutput the YAML now."


def run(llm_client: LLMClient, raw_request: str) -> dict:
    response_text = llm_client.complete(SYSTEM_PROMPT, build_user_content(raw_request))
    data = parse_llm_yaml(response_text)
    if "discovery" not in data:
        raise ValueError("Agent 1 response missing top-level 'discovery' key")
    return data
