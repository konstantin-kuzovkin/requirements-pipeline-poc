#!/usr/bin/env python3
"""
Run: python3 demo.py

Runs the Discovery -> Requirements -> Validate slice end to end WITHOUT any
network access, using FixtureLLMClient loaded with hand-written recorded
responses (fixtures/*.yaml). This proves the orchestration, schema
handling, and validation logic actually work -- it does NOT prove
anything about live model output quality. For that, run the same
pipeline with AnthropicLLMClient (see run_pipeline.py and eval/run_eval.py).

The requirements fixture contains two deliberate mistakes, planted by hand
to prove the validator actually catches them rather than rubber-stamping
whatever the "agent" produced:
  1. FR-005 is MUST + CONFIRMED but its source open question (OQ-03) was
     left unanswered -- rule R3 must catch this.
  2. FR-002's description calls the entity "Reimbursement Request" instead
     of the declared entity name "Expense Report" -- rule R9 must catch
     this naming drift.
"""
import os

from pipeline import agent1_discovery, agent2_requirements, agent3a_deterministic, agent5a_deterministic
from pipeline.agent4a_rules import (
    run_artifact_rules,
    run_deterministic_rules,
    run_test_rules,
)
from pipeline.agent4b_semantic import find_candidate_pairs
from pipeline.llm_client import FixtureLLMClient
from pipeline.yaml_io import load_yaml_file

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _read_fixture_text(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


# Hand-authored verdicts for the pairwise semantic check, keyed by the
# sorted pair of requirement IDs. Anything not listed here defaults to
# CONSISTENT, so the demo stays honest about which pairs were actually
# thought through versus defaulted.
PAIRWISE_VERDICTS = {
    ("FR-004", "FR-005"): (
        "UNCLEAR",
        "FR-004 triggers payment when status becomes APPROVED, and FR-005 also "
        "sets status to APPROVED via override -- it is not specified whether "
        "Finance's override on its own re-triggers FR-004's payment step, or "
        "whether that needs a separate action.",
    ),
}


def _verdict_for(req_a: dict, req_b: dict) -> tuple[str, str]:
    key = tuple(sorted([req_a.get("id", "?"), req_b.get("id", "?")]))
    return PAIRWISE_VERDICTS.get(key, ("CONSISTENT", ""))


def main():
    print("=" * 70)
    print("STEP 1 -- Discovery (offline, fixture response)")
    print("=" * 70)
    discovery_client = FixtureLLMClient(responses=[_read_fixture_text("discovery_fixture.yaml")])
    discovery = agent1_discovery.run(discovery_client, open("raw_request.txt", encoding="utf-8").read())
    oqs = discovery["discovery"]["open_questions"]
    print(f"{len(discovery['discovery']['stakeholders'])} stakeholders, "
          f"{len(oqs)} open questions:")
    for oq in oqs:
        print(f"  {oq['id']}: {oq['question']}")

    print("\n" + "=" * 70)
    print("STEP 2 -- Human checkpoint (loading pre-filled answers.yaml)")
    print("=" * 70)
    answers = load_yaml_file(os.path.join(FIXTURES_DIR, "answers_fixture.yaml"))
    for a in answers["answers"]:
        status = a["answer"] if a["answer"] else "(left unanswered on purpose)"
        print(f"  {a['open_question_id']}: {status}")

    print("\n" + "=" * 70)
    print("STEP 3 -- Requirements (offline, fixture response)")
    print("=" * 70)
    req_client = FixtureLLMClient(responses=[_read_fixture_text("requirements_fixture.yaml")])
    requirements = agent2_requirements.run(req_client, discovery, answers)
    reqs = requirements["requirements"]
    print(f"{len(reqs['functional'])} FRs, {len(reqs['non_functional'])} NFRs, "
          f"{len(reqs['entities'])} entities, {len(reqs['state_models'])} state model(s)")

    print("\n" + "=" * 70)
    print("STEP 4a -- Deterministic validation (no LLM)")
    print("=" * 70)
    counter = [0]
    det_issues = run_deterministic_rules(discovery, requirements, answers, counter)
    if not det_issues:
        print("  no issues found")
    for issue in det_issues:
        print(f"  [{issue.severity:7s}] {issue.rule:5s} {issue.message}")

    print("\n" + "=" * 70)
    print("STEP 4b -- Scoped LLM pairwise check (offline, fixture verdicts)")
    print("=" * 70)
    pairs = find_candidate_pairs(requirements)
    print(f"{len(pairs)} candidate pair(s) found by structural pre-filtering:")
    sem_issues = []
    for req_a, req_b in pairs:
        result, reason = _verdict_for(req_a, req_b)
        marker = " " if result == "CONSISTENT" else "!"
        print(f"  {marker} {req_a['id']} vs {req_b['id']}: {result}"
              + (f" -- {reason}" if reason else ""))
        if result != "CONSISTENT":
            sem_issues.append((req_a["id"], req_b["id"], result, reason))

    print("\n" + "=" * 70)
    print("STEP 5 -- Artifacts (Agent 3): deterministic (3a) + LLM (3b, fixture)")
    print("=" * 70)
    det_artifacts = agent3a_deterministic.run(discovery, requirements)
    print(f"  ER diagram: {len(reqs['entities'])} entit{'y' if len(reqs['entities'])==1 else 'ies'} rendered")
    for sm in det_artifacts["deterministic_artifacts"]["state_diagrams"]:
        print(f"  State diagram rendered for: {sm['entity']}")
    for ps in det_artifacts["deterministic_artifacts"]["process_skeleton"]:
        n_unmatched = len(ps["unmatched_transitions"])
        print(f"  Process skeleton for {ps['entity']}: "
              f"{'0 unmatched transitions' if n_unmatched == 0 else f'{n_unmatched} UNMATCHED transitions'}")

    llm_artifacts = load_yaml_file(os.path.join(FIXTURES_DIR, "artifacts_llm_fixture.yaml"))
    artifacts = {**det_artifacts, **llm_artifacts}
    print("  Component diagram + sequence diagram loaded (fixture, contains 2 deliberate mistakes)")

    print("\n" + "=" * 70)
    print("STEP 6 -- Test design (Agent 5): deterministic (5a) + LLM (5b, fixture)")
    print("=" * 70)
    det_tests = agent5a_deterministic.run(requirements)
    pos = sum(1 for t in det_tests["deterministic_tests"] if t["type"] == "POSITIVE")
    neg = sum(1 for t in det_tests["deterministic_tests"] if t["type"] == "NEGATIVE")
    print(f"  {len(det_tests['deterministic_tests'])} deterministic test cases "
          f"({pos} positive, {neg} negative -- every invalid transition gets its own test)")

    llm_tests = load_yaml_file(os.path.join(FIXTURES_DIR, "tests_llm_fixture.yaml"))
    tests = {**det_tests, **llm_tests}
    print(f"  {len(llm_tests['llm_tests']['edge_cases'])} LLM-proposed edge cases loaded "
          f"(fixture, contains 2 deliberate mistakes)")

    print("\n" + "=" * 70)
    print("STEP 7 -- Extended validation (R10-R17): artifact and test citations")
    print("=" * 70)
    artifact_issues = run_artifact_rules(requirements, artifacts)
    test_issues = run_test_rules(requirements, tests)
    for issue in artifact_issues + test_issues:
        print(f"  [{issue.severity:7s}] {issue.rule:5s} {issue.message}")

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    all_issues = det_issues + artifact_issues + test_issues
    errors = sum(1 for i in all_issues if i.severity == "ERROR") + sum(
        1 for _, _, r, _ in sem_issues if r == "CONTRADICTION"
    )
    warnings = len(all_issues) - errors + sum(1 for _, _, r, _ in sem_issues if r != "CONTRADICTION")
    print(f"{len(det_issues)} issue(s) from R0-R9, {len(artifact_issues)} from R10-R13, "
          f"{len(test_issues)} from R14-R17, {len(sem_issues)} from the LLM pairwise layer")
    print("\nSix deliberately planted mistakes across the whole run were caught:")
    checks = [
        ("R3  (MUST+CONFIRMED on unanswered question)", any(i.rule == "R3" for i in det_issues)),
        ("R9  (entity naming drift)", any(i.rule == "R9" for i in det_issues)),
        ("R10 (hallucinated citation in component diagram)", any(i.rule == "R10" for i in artifact_issues)),
        ("R11 (covers/mermaid citation mismatch)", any(i.rule == "R11" for i in artifact_issues)),
        ("R14 (edge case citing a nonexistent FR)", any(i.rule == "R14" for i in test_issues)),
        ("R15 (example_data citing a nonexistent test id)", any(i.rule == "R15" for i in test_issues)),
    ]
    for label, caught in checks:
        print(f"  - {label}: {'CAUGHT' if caught else 'MISSED'}")


if __name__ == "__main__":
    main()
