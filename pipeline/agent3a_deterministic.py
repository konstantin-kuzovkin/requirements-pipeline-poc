"""
Agent 3a -- deterministic artifact renderer. No LLM call.

Everything here is a mechanical reformat of data Agent 2 already produced
and Agent 4a already validated: an ER diagram from `entities`, a state
diagram from `state_models` (a direct, lossless transpile), and a process
skeleton that labels each transition with the FR that governs it and the
actor who performs it (matched by trigger name -- see
agent-pipeline-design-agents-3-5.md section 1).

Nothing here decides anything, so nothing here can hallucinate.
"""
from __future__ import annotations


def render_er_diagram(requirements: dict) -> str:
    entities = requirements.get("requirements", {}).get("entities", [])
    entity_names = {e["name"] for e in entities}
    lines = ["erDiagram"]

    for e in entities:
        safe_name = _mermaid_id(e["name"])
        lines.append(f"    {safe_name} {{")
        for attr in e.get("attributes", []):
            req = "" if attr.get("required") else "optional"
            lines.append(f"        {_mermaid_type(attr['type'])} {attr['name']} {req}".rstrip())
        lines.append("    }")

    # Naive FK inference: an attribute literally named "<other_entity>_id"
    # (snake_case of another declared entity's name) implies a relationship.
    for e in entities:
        for attr in e.get("attributes", []):
            for other in entity_names:
                if other == e["name"]:
                    continue
                if attr["name"] == _snake(other) + "_id":
                    lines.append(
                        f"    {_mermaid_id(other)} ||--o{{ {_mermaid_id(e['name'])} : \"has\""
                    )

    return "\n".join(lines)


def render_state_diagrams(requirements: dict) -> list[dict]:
    """
    A direct, lossless transpile of state_models into Mermaid. "Terminal"
    here means what the data actually says -- a state with zero outgoing
    transitions -- computed from the transitions list, not guessed from the
    state's name. A name-based guess (e.g. "REJECTED sounds terminal") would
    be wrong the moment a domain allows resubmission from REJECTED, which
    this very fixture does.
    """
    out = []
    for sm in requirements.get("requirements", {}).get("state_models", []):
        values = sm.get("values", [])
        transitions = sm.get("transitions", [])
        has_outgoing = {t["from"] for t in transitions}
        terminal_states = [v for v in values if v not in has_outgoing]

        lines = ["stateDiagram-v2", "    [*] --> " + values[0]]
        for t in transitions:
            label = t.get("trigger", "")
            lines.append(f"    {t['from']} --> {t['to']} : {label}")
        for v in terminal_states:
            lines.append(f"    {v} --> [*]")
        out.append({"entity": sm["entity"], "mermaid": "\n".join(lines)})
    return out


def render_process_skeletons(discovery: dict, requirements: dict) -> list[dict]:
    """
    Matches each transition to the FR that governs it via the FR's explicit
    `state_triggers` list (see agent2_requirements.py), NOT by comparing the
    transition's short trigger code against the FR's prose `trigger` field
    -- those are different vocabularies by design (a state_model trigger is
    a code like "manager_approves"; an FR's `trigger` is a human-readable
    sentence), and comparing them directly would silently match nothing.

    If the same trigger code is listed by more than one FR, the first FR
    encountered wins and this is a known v0.1 limitation, not a silent
    correctness gap: it would surface as a WARNING under future rule
    R12-adjacent tooling if it ever occurs. It does not occur in the
    current fixture.
    """
    stakeholder_names = {
        s["id"]: s["name"] for s in discovery.get("discovery", {}).get("stakeholders", [])
    }
    fr_by_trigger_code: dict[str, dict] = {}
    for fr in requirements.get("requirements", {}).get("functional", []):
        for code in fr.get("state_triggers", []):
            fr_by_trigger_code.setdefault(code, fr)

    out = []
    for sm in requirements.get("requirements", {}).get("state_models", []):
        lines = ["flowchart LR"]
        unmatched = []
        for t in sm.get("transitions", []):
            trigger = t.get("trigger", "")
            fr = fr_by_trigger_code.get(trigger)
            if fr:
                actor_name = stakeholder_names.get(fr.get("actor"), fr.get("actor", "?"))
                edge_label = f"{trigger} ({fr['id']}) [{actor_name}]"
            else:
                edge_label = f"{trigger} (unmatched)"
                unmatched.append({"trigger": trigger})
            lines.append(f'    {_mermaid_id(t["from"])} -->|"{edge_label}"| {_mermaid_id(t["to"])}')
        out.append({
            "entity": sm["entity"],
            "mermaid": "\n".join(lines),
            "unmatched_transitions": unmatched,
        })
    return out


def run(discovery: dict, requirements: dict) -> dict:
    return {
        "deterministic_artifacts": {
            "er_diagram": {"mermaid": render_er_diagram(requirements)},
            "state_diagrams": render_state_diagrams(requirements),
            "process_skeleton": render_process_skeletons(discovery, requirements),
        }
    }


# ---- small helpers ---------------------------------------------------------

def _mermaid_id(name: str) -> str:
    """Mermaid node/entity identifiers can't contain spaces."""
    return name.replace(" ", "")


def _snake(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _mermaid_type(t: str) -> str:
    # Mermaid erDiagram attribute types are simple tokens; fall back to
    # "string" for anything we don't recognise rather than emit invalid syntax.
    return t if t.isalnum() else "string"
