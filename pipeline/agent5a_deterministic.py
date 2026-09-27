"""
Agent 5a -- deterministic test case generator. No LLM call.

One POSITIVE test per acceptance criterion (already fully specified by
Agent 2) and one POSITIVE + N NEGATIVE tests per state transition: the
negative cases are every trigger that appears somewhere in the entity's
transition table but is NOT a valid outgoing trigger from a given state --
i.e. systematically generated "invalid transition is rejected" tests, the
same idea already hand-written once in outbox-poc's
test_invalid_transition_is_rejected, here generated for every state.
"""
from __future__ import annotations


def _next_id(counter: list[int]) -> str:
    counter[0] += 1
    return f"TC-{counter[0]:03d}"


def generate_acceptance_tests(requirements: dict, counter: list[int]) -> list[dict]:
    tests = []
    for fr in requirements.get("requirements", {}).get("functional", []):
        for ac in fr.get("acceptance_criteria", []):
            tests.append({
                "id": _next_id(counter),
                "type": "POSITIVE",
                "covers": [fr["id"]],
                "source": "acceptance_criterion",
                "given": ac["given"],
                "when": ac["when"],
                "then": ac["then"],
            })
    return tests


def generate_transition_tests(requirements: dict, counter: list[int]) -> list[dict]:
    tests = []
    for sm in requirements.get("requirements", {}).get("state_models", []):
        entity = sm["entity"]
        transitions = sm.get("transitions", [])
        values = sm.get("values", [])
        all_triggers = {t["trigger"] for t in transitions}

        valid_from = {}  # state -> {trigger: to}
        for t in transitions:
            valid_from.setdefault(t["from"], {})[t["trigger"]] = t["to"]

        # one POSITIVE test per declared transition
        for t in transitions:
            tests.append({
                "id": _next_id(counter),
                "type": "POSITIVE",
                "covers": [entity],
                "source": "transition",
                "given": f"{entity} is in state {t['from']}",
                "when": f"{t['trigger']} occurs",
                "then": f"the state becomes {t['to']}",
            })

        # one NEGATIVE test per (state, trigger) pair where the trigger
        # exists somewhere in this entity's lifecycle but not from this state
        for state in values:
            allowed = valid_from.get(state, {})
            for trigger in sorted(all_triggers - set(allowed.keys())):
                tests.append({
                    "id": _next_id(counter),
                    "type": "NEGATIVE",
                    "covers": [entity],
                    "source": "transition",
                    "given": f"{entity} is in state {state}",
                    "when": f"{trigger} is attempted",
                    "then": "the transition is rejected (INVALID_STATE_TRANSITION); "
                            f"state remains {state}",
                })
    return tests


def run(requirements: dict) -> dict:
    counter = [0]
    tests = generate_acceptance_tests(requirements, counter) + generate_transition_tests(
        requirements, counter
    )
    return {"deterministic_tests": tests}
