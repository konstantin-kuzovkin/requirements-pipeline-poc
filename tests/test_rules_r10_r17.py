"""
Seeded-error tests for R10-R17 (artifact and test citation rules), same
methodology as test_rules_seeded_errors.py: one clean baseline, one seeded
mutation per rule, assert the matching rule fires and the clean baseline
fires nothing.
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.agent4a_rules import run_artifact_rules, run_test_rules


def base_requirements():
    return {
        "requirements": {
            "functional": [
                {"id": "FR-001", "priority": "MUST", "status": "CONFIRMED"},
                {"id": "FR-002", "priority": "SHOULD", "status": "CONFIRMED"},
            ],
            "non_functional": [{"id": "NFR-001"}],
            "entities": [{"name": "Widget"}],
            "state_models": [
                {
                    "entity": "Widget",
                    "values": ["A", "B"],
                    "transitions": [{"from": "A", "to": "B", "trigger": "go"}],
                }
            ],
        }
    }


def base_artifacts():
    return {
        "deterministic_artifacts": {
            "process_skeleton": [{"entity": "Widget", "mermaid": "", "unmatched_transitions": []}],
        },
        "llm_artifacts": {
            "component_diagram": {
                "mermaid": 'flowchart TB\n  A -->|"go (FR-001)"| B\n',
                "covers": ["FR-001"],
            },
            "sequence_diagram": {
                "scenario": "s",
                "mermaid": "sequenceDiagram\n  A->>B: go\n",
                "covers": [],
            },
        },
    }


def base_tests():
    return {
        "deterministic_tests": [
            {"id": "TC-001", "type": "POSITIVE", "covers": ["Widget"], "source": "transition",
             "given": "Widget is in state A", "when": "go occurs", "then": "state becomes B"},
        ],
        "llm_tests": {
            "example_data": [{"test_id": "TC-001", "data": {}}],
            "edge_cases": [{"id": "TC-101", "type": "EDGE", "covers": ["FR-001"],
                             "given": "g", "when": "w", "then": "t", "reason": "r"}],
        },
    }


class TestCleanBaselines(unittest.TestCase):
    def test_artifacts_baseline_has_no_errors(self):
        issues = run_artifact_rules(base_requirements(), base_artifacts())
        errors = [i for i in issues if i.severity == "ERROR"]
        self.assertEqual(errors, [], f"unexpected errors on clean baseline: {errors}")

    def test_tests_baseline_has_no_errors(self):
        issues = run_test_rules(base_requirements(), base_tests())
        errors = [i for i in issues if i.severity == "ERROR"]
        self.assertEqual(errors, [], f"unexpected errors on clean baseline: {errors}")

    def test_artifacts_baseline_no_r13_gap(self):
        # FR-001 is MUST+CONFIRMED and IS cited in the process skeleton's
        # sibling component diagram -- R13 should not fire.
        issues = run_artifact_rules(base_requirements(), base_artifacts())
        self.assertNotIn("R13", {i.rule for i in issues})

    def test_tests_baseline_no_r16_or_r17_gap(self):
        issues = run_test_rules(base_requirements(), base_tests())
        fired = {i.rule for i in issues}
        self.assertNotIn("R16", fired)
        self.assertNotIn("R17", fired)


class TestSeededArtifactErrors(unittest.TestCase):
    def test_R10_hallucinated_citation(self):
        a = base_artifacts()
        a["llm_artifacts"]["component_diagram"]["mermaid"] += '  B -->|"ghost (FR-999)"| A\n'
        a["llm_artifacts"]["component_diagram"]["covers"].append("FR-999")
        issues = run_artifact_rules(base_requirements(), a)
        self.assertIn("R10", {i.rule for i in issues})

    def test_R11_covers_not_actually_cited(self):
        a = base_artifacts()
        a["llm_artifacts"]["component_diagram"]["covers"].append("NFR-001")  # never cited in the mermaid text
        issues = run_artifact_rules(base_requirements(), a)
        self.assertIn("R11", {i.rule for i in issues})

    def test_R12_unmatched_transition_surfaced(self):
        a = base_artifacts()
        a["deterministic_artifacts"]["process_skeleton"][0]["unmatched_transitions"] = [
            {"trigger": "mystery"}
        ]
        issues = run_artifact_rules(base_requirements(), a)
        self.assertIn("R12", {i.rule for i in issues})

    def test_R13_must_requirement_with_zero_coverage(self):
        r = base_requirements()
        r["requirements"]["functional"].append(
            {"id": "FR-003", "priority": "MUST", "status": "CONFIRMED"}
        )
        # FR-003 is not cited anywhere in base_artifacts()
        issues = run_artifact_rules(r, base_artifacts())
        self.assertIn("R13", {i.rule for i in issues})


class TestSeededTestErrors(unittest.TestCase):
    def test_R14_covers_unknown_target(self):
        t = base_tests()
        t["llm_tests"]["edge_cases"][0]["covers"] = ["FR-999"]
        issues = run_test_rules(base_requirements(), t)
        self.assertIn("R14", {i.rule for i in issues})

    def test_R15_example_data_bad_test_id(self):
        t = base_tests()
        t["llm_tests"]["example_data"][0]["test_id"] = "TC-999"
        issues = run_test_rules(base_requirements(), t)
        self.assertIn("R15", {i.rule for i in issues})

    def test_R16_must_requirement_with_no_test(self):
        r = base_requirements()
        r["requirements"]["functional"].append(
            {"id": "FR-003", "priority": "MUST", "status": "CONFIRMED"}
        )
        issues = run_test_rules(r, base_tests())  # nothing covers FR-003
        self.assertIn("R16", {i.rule for i in issues})

    def test_R17_transition_with_no_positive_test(self):
        t = base_tests()
        t["deterministic_tests"] = []  # remove the only transition test
        issues = run_test_rules(base_requirements(), t)
        self.assertIn("R17", {i.rule for i in issues})


if __name__ == "__main__":
    unittest.main(verbosity=2)
