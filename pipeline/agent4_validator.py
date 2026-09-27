"""
Agent 4 -- combines the deterministic layer (4a) and the scoped LLM
pairwise layer (4b) into one validation_report.
"""
from __future__ import annotations

import datetime as dt

from .agent4a_rules import Issue, run_artifact_rules, run_deterministic_rules, run_test_rules
from .agent4b_semantic import run_pairwise_checks
from .llm_client import LLMClient


def run(
    discovery: dict,
    requirements: dict,
    answers: dict,
    llm_client: LLMClient | None,
    run_semantic: bool = True,
    artifacts: dict | None = None,
    tests: dict | None = None,
) -> dict:
    counter = [0]
    issues: list[Issue] = run_deterministic_rules(discovery, requirements, answers, counter)
    rules_run = [f"R{i}" for i in range(10)]

    if run_semantic and llm_client is not None:
        issues += run_pairwise_checks(llm_client, requirements, counter)
        rules_run.append("LLM-pairwise")

    if artifacts is not None:
        issues += run_artifact_rules(requirements, artifacts, counter)
        rules_run += ["R10", "R11", "R12", "R13"]

    if tests is not None:
        issues += run_test_rules(requirements, tests, counter)
        rules_run += ["R14", "R15", "R16", "R17"]

    errors = sum(1 for i in issues if i.severity == "ERROR")
    warnings = sum(1 for i in issues if i.severity == "WARNING")

    return {
        "validation_report": {
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "rules_run": rules_run,
            "issues": [
                {
                    "id": i.id,
                    "severity": i.severity,
                    "rule": i.rule,
                    "message": i.message,
                    "refs": i.refs,
                }
                for i in issues
            ],
            "summary": {"errors": errors, "warnings": warnings},
        }
    }
