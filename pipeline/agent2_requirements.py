"""
Agent 2 -- Requirements.

Consumes the Discovery output plus answers to its open questions, produces
FR / NFR / entities / state models as one YAML document. See
agent-pipeline-design.md section 4.
"""
from __future__ import annotations

import yaml

from .llm_client import LLMClient
from .yaml_io import parse_llm_yaml

SCHEMA_TEXT = """
requirements:
  functional:
    - id: "FR-001"
      title: string
      description: string
      actor: "STK-01"
      trigger: string
      acceptance_criteria:
        - given: string
          when: string
          then: string
      priority: MUST | SHOULD | COULD
      source: "OQ-01" | "ASM-02" | "raw_request"
      status: CONFIRMED | DRAFT
      state_triggers: ["manager_approves"]   # optional: transition trigger codes
                                               # (from state_models) that this FR governs
  non_functional:
    - id: "NFR-001"
      category: PERFORMANCE | AVAILABILITY | SECURITY | AUDITABILITY | USABILITY
      requirement: string
      metric: string
      priority: MUST | SHOULD | COULD
  entities:
    - name: string
      description: string
      attributes:
        - name: string
          type: string
          required: boolean
  state_models:
    - entity: string
      values: [string]
      transitions:
        - from: string
          to: string
          trigger: string
          guard: string
  open_items:
    - id: "OI-01"
      text: string
      blocks: ["FR-003"]
"""

SYSTEM_PROMPT = f"""You are the Requirements Agent. Input: the Discovery YAML and a set of
answers to its open questions (some may be unanswered). Produce ONLY a
YAML document matching the Requirements Output schema. No text before or
after the YAML.

Schema:
{SCHEMA_TEXT}

Rules:
- Every FR's `actor` must be a stakeholder id that exists in the Discovery
  output. Do not introduce a new actor.
- Every FR has at least one acceptance criterion in Given/When/Then form.
- If a requirement depends on an open question that was NOT answered, do
  not guess the missing value. Write the requirement with status: DRAFT,
  leave the dependent detail as a placeholder in the description (e.g.
  "[pending OQ-03: reimbursement threshold]"), and add an open_item that
  lists it under `blocks`. Never mark a requirement CONFIRMED if it relies
  on an unanswered question.
- Every NFR's `metric` must be a measurable statement, not a vague
  adjective. "The system should be fast" is not acceptable; "p95 response
  time <= 2s under 50 concurrent users" is.
- Reuse entity and field names consistently. Do not introduce a second
  name for a concept that already has one.
- state_models must only be produced for entities that clearly have a
  lifecycle with distinct states.
- If an FR causes one or more state transitions, list their exact
  `trigger` codes (as they appear in state_models.transitions) in
  `state_triggers`. Do not use prose here -- reuse the same short trigger
  code you used in state_models, so the two can be matched exactly. Omit
  `state_triggers` entirely for FRs that don't cause a transition (e.g. a
  validation rule).
- Do not add requirements that are not implied by the discovery output or
  the given answers.
"""


def build_user_content(discovery: dict, answers: dict) -> str:
    discovery_yaml = yaml.safe_dump(discovery, sort_keys=False, allow_unicode=True)
    answers_yaml = yaml.safe_dump(answers, sort_keys=False, allow_unicode=True)
    return (
        f"Discovery YAML:\n{discovery_yaml}\n\n"
        f"Answers:\n{answers_yaml}\n\n"
        "Output the YAML now."
    )


def run(llm_client: LLMClient, discovery: dict, answers: dict) -> dict:
    response_text = llm_client.complete(SYSTEM_PROMPT, build_user_content(discovery, answers))
    data = parse_llm_yaml(response_text)
    if "requirements" not in data:
        raise ValueError("Agent 2 response missing top-level 'requirements' key")
    return data
