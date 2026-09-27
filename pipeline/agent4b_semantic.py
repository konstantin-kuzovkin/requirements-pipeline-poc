"""
Agent 4b -- scoped LLM pairwise contradiction check.

Only called on candidate pairs pre-filtered by agent4a-style structural
overlap (same actor, or same entity mentioned, or same NFR category). This
keeps the number of LLM calls at O(candidates) instead of O(n^2) over all
requirements, and keeps each call narrow enough that its accuracy can
actually be measured (see eval/run_eval.py) instead of assumed.
"""
from __future__ import annotations

import itertools

import yaml

from .agent4a_rules import Issue, next_issue_id  # reuse Issue + id counter shape
from .llm_client import LLMClient
from .yaml_io import parse_llm_yaml

PAIRWISE_SYSTEM_PROMPT = """You are the semantic consistency checker. You will be given exactly two
requirements. Decide only whether they contradict each other. Do not
comment on style, completeness, or anything else. Answer ONLY with YAML:

result: CONSISTENT | CONTRADICTION | UNCLEAR
reason: string   # one sentence, required only if result != CONSISTENT
"""


def find_candidate_pairs(requirements: dict) -> list[tuple[dict, dict]]:
    """
    Note on the shared-word heuristic below: in a small requirement set that
    revolves around one core entity, almost every description mentions that
    entity's name, so a naive "shared capitalized word" check matches most
    pairs and saves little over checking everything. We exclude words that
    are part of a *declared entity name* from counting as a shared-word
    signal, so the filter reacts to unrelated overlap (two requirements that
    happen to both mention "Threshold", say) rather than the expected,
    uninformative overlap of every requirement mentioning "Expense Report".
    This still is a heuristic pre-filter, not a precision instrument -- see
    agent-pipeline-design.md section 5b.
    """
    reqs = requirements.get("requirements", {})
    fr_list = reqs.get("functional", [])
    nfr_list = reqs.get("non_functional", [])
    entity_name_tokens = {
        w for e in reqs.get("entities", []) for w in e.get("name", "").split()
    }

    pairs: list[tuple[dict, dict]] = []

    # FRs sharing the same actor are candidates for behavioural contradictions
    # (e.g. two rules about who is allowed to approve).
    for a, b in itertools.combinations(fr_list, 2):
        if a.get("actor") and a.get("actor") == b.get("actor"):
            pairs.append((a, b))
            continue
        # or both descriptions mention the same capitalized word, excluding
        # words that are just the shared entity's own name (see note above)
        words_a = set(a.get("description", "").split())
        words_b = set(b.get("description", "").split())
        shared_caps = {w for w in words_a & words_b if w[:1].isupper()} - entity_name_tokens
        if shared_caps:
            pairs.append((a, b))

    # NFRs of the same category are candidates for numeric contradictions
    # (e.g. two conflicting latency targets).
    for a, b in itertools.combinations(nfr_list, 2):
        if a.get("category") == b.get("category"):
            pairs.append((a, b))

    return pairs


def _build_user_content(req_a: dict, req_b: dict) -> str:
    a_yaml = yaml.safe_dump(req_a, sort_keys=False, allow_unicode=True)
    b_yaml = yaml.safe_dump(req_b, sort_keys=False, allow_unicode=True)
    return f"Requirement A:\n{a_yaml}\n\nRequirement B:\n{b_yaml}"


def check_pair(llm_client: LLMClient, req_a: dict, req_b: dict) -> dict:
    """Returns the parsed {result, reason} dict for one pair."""
    response_text = llm_client.complete(PAIRWISE_SYSTEM_PROMPT, _build_user_content(req_a, req_b))
    parsed = parse_llm_yaml(response_text)
    if "result" not in parsed:
        raise ValueError(f"pairwise check response missing 'result': {parsed}")
    return parsed


def run_pairwise_checks(
    llm_client: LLMClient, requirements: dict, counter: list[int]
) -> list[Issue]:
    issues: list[Issue] = []
    for req_a, req_b in find_candidate_pairs(requirements):
        result = check_pair(llm_client, req_a, req_b)
        if result["result"] in ("CONTRADICTION", "UNCLEAR"):
            severity = "ERROR" if result["result"] == "CONTRADICTION" else "WARNING"
            issues.append(Issue(
                next_issue_id(counter),
                severity,
                "LLM-pairwise",
                f"{result['result']} between {req_a.get('id')} and {req_b.get('id')}: "
                f"{result.get('reason', '')}",
                refs=[req_a.get("id", "?"), req_b.get("id", "?")],
            ))
    return issues
