"""
Agent 4a -- deterministic rule engine.

Every rule here is plain Python over the structured YAML from agents 1 and
2. No LLM call, no judgment call: either the data violates the rule or it
doesn't. This is what makes it possible to unit-test with seeded-error
fixtures and get 100% precision/recall by construction (see
tests/test_rules_seeded_errors.py) -- unlike the LLM-assisted pairwise
check in agent4b, whose accuracy has to be measured, not assumed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MEASURABLE_METRIC_RE = re.compile(
    r"(<=|>=|<|>|==)\s*\d|"  # comparison operator followed by a number
    # number + unit, longest unit names first so "sec" doesn't shadow "seconds",
    # and a plain (?=\W|$) lookahead instead of \b -- \b fails right after a
    # non-word character like "%", which is exactly the most common unit here.
    r"\d+(?:\.\d+)?\s*(milliseconds|seconds|minutes|hours|days|ms|sec|min|req|users|rps|tps|%|s)(?=\W|$)",
    re.IGNORECASE,
)


@dataclass
class Issue:
    id: str
    severity: str  # "ERROR" | "WARNING"
    rule: str
    message: str
    refs: list[str] = field(default_factory=list)


def next_issue_id(counter: list[int]) -> str:
    counter[0] += 1
    return f"ISS-{counter[0]:03d}"


def run_deterministic_rules(
    discovery: dict, requirements: dict, answers: dict, counter: list[int] | None = None
) -> list[Issue]:
    """`counter` is a shared [int] cell so IDs stay unique across the deterministic
    and LLM-assisted issue lists when the orchestrator merges both (pass the same
    list object to agent4b.run_pairwise_checks afterwards)."""
    issues: list[Issue] = []
    if counter is None:
        counter = [0]

    disc = discovery.get("discovery", {})
    reqs = requirements.get("requirements", {})

    stakeholder_ids = {s["id"] for s in disc.get("stakeholders", [])}
    answered_oq_ids = {
        a["open_question_id"] for a in answers.get("answers", []) if a.get("answer")
    }
    all_oq_ids = {oq["id"] for oq in disc.get("open_questions", [])}
    unanswered_oq_ids = all_oq_ids - answered_oq_ids

    fr_list = reqs.get("functional", [])
    nfr_list = reqs.get("non_functional", [])
    entities = reqs.get("entities", [])
    entity_names = {e["name"] for e in entities}
    state_models = reqs.get("state_models", [])
    open_items = reqs.get("open_items", [])

    # R0: every INFERENCE-marked item in discovery has a non-empty reason
    for section in ("stakeholders", "assumptions", "glossary"):
        for item in disc.get(section, []):
            if item.get("marker") == "INFERENCE" and not item.get("reason", "").strip():
                label = item.get("id") or item.get("term") or "?"
                issues.append(Issue(
                    next_issue_id(counter), "ERROR", "R0",
                    f"{section[:-1]} {label} is marked INFERENCE but has no reason",
                    refs=[str(label)],
                ))

    # R1: every FR's actor exists in discovery.stakeholders
    for fr in fr_list:
        if fr.get("actor") not in stakeholder_ids:
            issues.append(Issue(
                next_issue_id(counter), "ERROR", "R1",
                f"{fr.get('id', '?')} references actor {fr.get('actor')!r}, "
                f"which is not in discovery.stakeholders",
                refs=[fr.get("id", "?")],
            ))

    # R2: no duplicate requirement IDs (FR or NFR)
    seen_ids: dict[str, int] = {}
    for item in fr_list + nfr_list:
        rid = item.get("id", "?")
        seen_ids[rid] = seen_ids.get(rid, 0) + 1
    for rid, count in seen_ids.items():
        if count > 1:
            issues.append(Issue(
                next_issue_id(counter), "ERROR", "R2",
                f"requirement id {rid} is used {count} times", refs=[rid],
            ))

    # R3: a MUST-priority FR cannot be CONFIRMED if its `source` open question
    # is unanswered
    for fr in fr_list:
        if fr.get("priority") == "MUST" and fr.get("status") == "CONFIRMED":
            source = fr.get("source")
            if source in unanswered_oq_ids:
                issues.append(Issue(
                    next_issue_id(counter), "ERROR", "R3",
                    f"{fr.get('id', '?')} is MUST + CONFIRMED but its source "
                    f"{source} is an unanswered open question",
                    refs=[fr.get("id", "?"), source],
                ))

    # R4: every FR has at least one acceptance criterion
    for fr in fr_list:
        if not fr.get("acceptance_criteria"):
            issues.append(Issue(
                next_issue_id(counter), "ERROR", "R4",
                f"{fr.get('id', '?')} has no acceptance criteria",
                refs=[fr.get("id", "?")],
            ))

    # R5 (heuristic): every NFR metric looks measurable
    for nfr in nfr_list:
        metric = nfr.get("metric", "")
        if not MEASURABLE_METRIC_RE.search(metric):
            issues.append(Issue(
                next_issue_id(counter), "WARNING", "R5",
                f"{nfr.get('id', '?')} metric {metric!r} does not look measurable "
                f"(no comparison operator or number+unit found)",
                refs=[nfr.get("id", "?")],
            ))

    # R6: every unanswered open question is referenced by some open_item.blocks,
    # OR was answered. A dropped question is the worst failure mode.
    blocked_targets = {fr_id for oi in open_items for fr_id in oi.get("blocks", [])}
    referenced_oq_in_items = {oi.get("text", "") for oi in open_items}
    for oq_id in unanswered_oq_ids:
        referenced_somewhere = any(
            oq_id in oi.get("text", "") or oq_id in str(oi.get("blocks", []))
            for oi in open_items
        ) or any(fr.get("source") == oq_id for fr in fr_list)
        if not referenced_somewhere:
            issues.append(Issue(
                next_issue_id(counter), "ERROR", "R6",
                f"open question {oq_id} is unanswered and was silently dropped "
                f"(not referenced by any FR.source or open_item)",
                refs=[oq_id],
            ))

    # R7: every state transition's from/to exists in that entity's values
    for sm in state_models:
        values = set(sm.get("values", []))
        for t in sm.get("transitions", []):
            for endpoint in ("from", "to"):
                v = t.get(endpoint)
                if v not in values:
                    issues.append(Issue(
                        next_issue_id(counter), "ERROR", "R7",
                        f"{sm.get('entity', '?')} transition {t.get('trigger', '?')} "
                        f"references state {v!r} ({endpoint}) not in declared values {sorted(values)}",
                        refs=[sm.get("entity", "?")],
                    ))

    # R8 (heuristic): every declared state is reachable and (except terminal)
    # has an outgoing transition
    for sm in state_models:
        values = set(sm.get("values", []))
        transitions = sm.get("transitions", [])
        reachable = {t["to"] for t in transitions}
        has_outgoing = {t["from"] for t in transitions}
        for v in values:
            if v not in reachable and not _looks_initial(v, transitions):
                issues.append(Issue(
                    next_issue_id(counter), "WARNING", "R8",
                    f"{sm.get('entity', '?')} state {v!r} is never reached by any transition",
                    refs=[sm.get("entity", "?"), v],
                ))
            if v not in has_outgoing and not _looks_terminal(v):
                issues.append(Issue(
                    next_issue_id(counter), "WARNING", "R8",
                    f"{sm.get('entity', '?')} state {v!r} has no outgoing transition "
                    f"and is not an obviously terminal name",
                    refs=[sm.get("entity", "?"), v],
                ))

    # R9 (heuristic): capitalized entity-like phrases in FR descriptions that
    # do not match any declared entity name
    known = entity_names
    for fr in fr_list:
        for phrase in _capitalized_phrases(fr.get("description", "")):
            if phrase not in known and not _plausibly_not_an_entity(phrase):
                issues.append(Issue(
                    next_issue_id(counter), "WARNING", "R9",
                    f"{fr.get('id', '?')} description mentions {phrase!r}, which "
                    f"does not match any declared entity name -- possibly missing "
                    f"from requirements.entities, or a false positive",
                    refs=[fr.get("id", "?"), phrase],
                ))

    return issues


def _looks_initial(state: str, transitions: list[dict]) -> bool:
    return any(t["from"] == state for t in transitions) and not any(
        t["to"] == state for t in transitions
    )


CITATION_RE = re.compile(r"\((FR-\d+|NFR-\d+)\)")


def _known_requirement_ids(requirements: dict) -> set[str]:
    reqs = requirements.get("requirements", {})
    return {fr["id"] for fr in reqs.get("functional", [])} | {
        nfr["id"] for nfr in reqs.get("non_functional", [])
    }


def _known_coverage_targets(requirements: dict) -> set[str]:
    """FR/NFR ids plus entity names -- everything a `covers` field may cite."""
    reqs = requirements.get("requirements", {})
    ids = _known_requirement_ids(requirements)
    entity_names = {e["name"] for e in reqs.get("entities", [])}
    return ids | entity_names


def run_artifact_rules(
    requirements: dict, artifacts: dict, counter: list[int] | None = None
) -> list[Issue]:
    """R10-R13: check the citations Agent 3's outputs make against known-good data."""
    issues: list[Issue] = []
    if counter is None:
        counter = [0]

    known_ids = _known_requirement_ids(requirements)
    det = artifacts.get("deterministic_artifacts", {})
    llm = artifacts.get("llm_artifacts", {})

    llm_pieces = {
        "component_diagram": llm.get("component_diagram", {}),
        "sequence_diagram": llm.get("sequence_diagram", {}),
    }

    for name, piece in llm_pieces.items():
        mermaid_text = piece.get("mermaid", "")
        cited_in_text = set(CITATION_RE.findall(mermaid_text))

        # R10: every cited id in the mermaid text actually exists
        for cid in cited_in_text - known_ids:
            issues.append(Issue(
                next_issue_id(counter), "ERROR", "R10",
                f"{name} cites {cid!r} inline, which does not exist in requirements",
                refs=[name, cid],
            ))

        # R11: every id in `covers` actually appears in the mermaid text
        covers = set(piece.get("covers", []))
        for cid in covers - cited_in_text:
            issues.append(Issue(
                next_issue_id(counter), "ERROR", "R11",
                f"{name}.covers lists {cid!r} but it is not cited anywhere in the "
                f"diagram's mermaid text",
                refs=[name, cid],
            ))

    # R12: every unmatched transition from the process skeleton is surfaced
    for ps in det.get("process_skeleton", []):
        for u in ps.get("unmatched_transitions", []):
            issues.append(Issue(
                next_issue_id(counter), "WARNING", "R12",
                f"{ps.get('entity', '?')} transition {u.get('trigger', '?')!r} has no "
                f"matching FR (no FR.state_triggers lists it)",
                refs=[ps.get("entity", "?"), u.get("trigger", "?")],
            ))

    # R13: every MUST+CONFIRMED FR is cited by at least one artifact
    all_cited = set()
    for ps in det.get("process_skeleton", []):
        all_cited |= set(CITATION_RE.findall(ps.get("mermaid", "")))
    for piece in llm_pieces.values():
        all_cited |= set(CITATION_RE.findall(piece.get("mermaid", "")))

    for fr in requirements.get("requirements", {}).get("functional", []):
        if fr.get("priority") == "MUST" and fr.get("status") == "CONFIRMED":
            if fr["id"] not in all_cited:
                issues.append(Issue(
                    next_issue_id(counter), "WARNING", "R13",
                    f"{fr['id']} is MUST + CONFIRMED but is not represented in any "
                    f"diagram (process skeleton, component diagram, or sequence diagram)",
                    refs=[fr["id"]],
                ))

    return issues


def run_test_rules(
    requirements: dict, tests: dict, counter: list[int] | None = None
) -> list[Issue]:
    """R14-R17: check test-case citations and coverage."""
    issues: list[Issue] = []
    if counter is None:
        counter = [0]

    known_targets = _known_coverage_targets(requirements)
    det_tests = tests.get("deterministic_tests", [])
    llm_tests = tests.get("llm_tests", {})
    edge_cases = llm_tests.get("edge_cases", [])
    example_data = llm_tests.get("example_data", [])

    det_test_ids = {t["id"] for t in det_tests}

    # R14: every covers id (deterministic + edge cases) exists in requirements
    for t in det_tests + edge_cases:
        for cid in t.get("covers", []):
            if cid not in known_targets:
                issues.append(Issue(
                    next_issue_id(counter), "ERROR", "R14",
                    f"{t.get('id', '?')} covers {cid!r}, which is not a known FR/NFR/entity",
                    refs=[t.get("id", "?"), cid],
                ))

    # R15: every example_data.test_id references an existing deterministic test
    for ed in example_data:
        if ed.get("test_id") not in det_test_ids:
            issues.append(Issue(
                next_issue_id(counter), "ERROR", "R15",
                f"example_data references test_id {ed.get('test_id')!r}, which does "
                f"not exist among the deterministic tests",
                refs=[str(ed.get("test_id"))],
            ))

    # R16: every MUST+CONFIRMED FR has at least one covering test case
    all_test_covers = set()
    for t in det_tests + edge_cases:
        all_test_covers |= set(t.get("covers", []))
    for fr in requirements.get("requirements", {}).get("functional", []):
        if fr.get("priority") == "MUST" and fr.get("status") == "CONFIRMED":
            if fr["id"] not in all_test_covers:
                issues.append(Issue(
                    next_issue_id(counter), "WARNING", "R16",
                    f"{fr['id']} is MUST + CONFIRMED but has no covering test case",
                    refs=[fr["id"]],
                ))

    # R17: every declared transition has at least one covering POSITIVE test
    # (should always pass by construction -- a failure here means agent5a
    # itself has a bug, not that "the AI got it wrong")
    positive_transition_tests = [
        t for t in det_tests if t.get("source") == "transition" and t.get("type") == "POSITIVE"
    ]
    for sm in requirements.get("requirements", {}).get("state_models", []):
        entity = sm["entity"]
        for tr in sm.get("transitions", []):
            covered = any(
                t.get("covers") == [entity]
                and f"in state {tr['from']}" in t.get("given", "")
                and tr["trigger"] in t.get("when", "")
                for t in positive_transition_tests
            )
            if not covered:
                issues.append(Issue(
                    next_issue_id(counter), "WARNING", "R17",
                    f"{entity} transition {tr['from']}->{tr['to']} ({tr['trigger']}) has "
                    f"no covering positive test case",
                    refs=[entity, tr["trigger"]],
                ))

    return issues


def _looks_terminal(state: str) -> bool:
    return state.upper() in {"PAID", "REJECTED", "CANCELLED", "CANCELED", "CLOSED", "DONE", "COMPLETED", "FAILED"}


_CAP_PHRASE_RE = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){0,2})\b")
# Leading articles/determiners: stripped from the front of a match before it
# is considered a candidate entity name ("An Employee" -> "Employee").
_LEADING_STOPWORDS = {"The", "A", "An", "If", "When", "This", "It", "These", "Those"}
# Role/actor words: usually an actor, not an entity -- a lone match is
# suppressed, but "Manager Approval" (role + noun) is still a candidate.
_ROLE_WORDS = {"Finance", "Manager", "Employee"}


def _capitalized_phrases(text: str) -> set[str]:
    phrases: set[str] = set()
    for m in _CAP_PHRASE_RE.finditer(text):
        words = m.group(1).split()
        while words and words[0] in _LEADING_STOPWORDS:
            words = words[1:]
        if not words:
            continue
        if len(words) == 1 and words[0] in _ROLE_WORDS:
            continue
        if len(words) == 1 and words[0].isupper() and len(words[0]) <= 5:
            continue  # likely an acronym or currency code (USD, ABS, API), not an entity
        phrases.add(" ".join(words))
    return phrases


def _plausibly_not_an_entity(phrase: str) -> bool:
    # Kept for callers that already have a phrase and want the same check
    # applied standalone (used by tests).
    words = phrase.split()
    return len(words) == 1 and words[0] in _ROLE_WORDS
