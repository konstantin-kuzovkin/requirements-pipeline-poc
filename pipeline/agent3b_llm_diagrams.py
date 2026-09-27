"""
Agent 3b -- LLM-assisted diagrams: component decomposition and one sequence
diagram. These need genuine judgment (system decomposition and interaction
ordering aren't explicit in requirements.yaml), unlike the ER/state/process
diagrams in agent3a_deterministic.py.
"""
from __future__ import annotations

import yaml

from .llm_client import LLMClient
from .yaml_io import parse_llm_yaml

SCHEMA_TEXT = """
llm_artifacts:
  component_diagram:
    mermaid: string
    covers: ["FR-001", "NFR-001"]
  sequence_diagram:
    scenario: string
    covers: ["FR-002", "FR-004"]
    mermaid: string
"""

SYSTEM_PROMPT = f"""You are the Artifacts Agent (LLM half). You will be given validated
requirements and already-generated entity/state diagrams. Produce ONLY a
YAML document matching the schema below. No text before or after the YAML.

Schema:
{SCHEMA_TEXT}

Rules:
- Do not redraw the ER diagram or state diagram -- they already exist and
  are correct by construction. Your job is the component diagram (system
  decomposition: which components exist and how they connect) and one
  sequence diagram (the interaction order for one representative scenario).
- Every node or edge in the component diagram that implements a
  requirement must cite that requirement's ID directly in its Mermaid
  label text, e.g. |"submits report (FR-001)"|. Do not cite an ID that is
  not in the given requirements.
- The sequence diagram must pick ONE scenario (state which one in
  `scenario`) and its `covers` list must be the FRs whose trigger or
  acceptance criteria that scenario actually enacts -- not every FR in the
  system.
- If you are not confident a component is implied by the requirements
  (rather than a reasonable but unstated architectural choice, e.g. "a
  message queue"), you may still include it, but do not cite a
  requirement ID next to it -- an uncited element is your own
  architectural judgment, not something the requirements demanded.
- Valid Mermaid syntax only. No prose commentary inside the mermaid block.
"""


def build_user_content(requirements: dict, deterministic_artifacts: dict) -> str:
    req_yaml = yaml.safe_dump(requirements, sort_keys=False, allow_unicode=True)
    det_yaml = yaml.safe_dump(deterministic_artifacts, sort_keys=False, allow_unicode=True)
    return (
        f"Requirements:\n{req_yaml}\n\n"
        f"Deterministic artifacts already produced:\n{det_yaml}\n\n"
        "Output the YAML now."
    )


def run(llm_client: LLMClient, requirements: dict, deterministic_artifacts: dict) -> dict:
    response_text = llm_client.complete(
        SYSTEM_PROMPT, build_user_content(requirements, deterministic_artifacts)
    )
    data = parse_llm_yaml(response_text)
    if "llm_artifacts" not in data:
        raise ValueError("Agent 3b response missing top-level 'llm_artifacts' key")
    return data
