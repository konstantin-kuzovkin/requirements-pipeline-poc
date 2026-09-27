"""
Seeded-error tests for the deterministic rule engine (agent4a_rules).

Methodology, matching agent-pipeline-design.md section 6: start from one
clean, valid (discovery, requirements, answers) triple, then for each rule
produce a mutated copy with exactly one seeded violation, and assert the
engine flags that rule and that mutation does not also trip unrelated
rules unexpectedly. This is what "100% precision/recall by construction"
means for the deterministic layer -- it is regular unit testing, not an
AI evaluation, and that distinction matters: see eval/run_eval.py for the
one part of this system where accuracy actually has to be measured.
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.agent4a_rules import run_deterministic_rules


def base_discovery():
    return {
        "discovery": {
            "stakeholders": [
                {"id": "STK-01", "name": "Employee", "interest": "x", "marker": "FACT"},
                {"id": "STK-02", "name": "Manager", "interest": "y", "marker": "FACT"},
            ],
            "assumptions": [
                {"id": "ASM-01", "text": "one currency", "marker": "INFERENCE", "reason": "not mentioned otherwise"},
            ],
            "open_questions": [
                {"id": "OQ-01", "question": "threshold amount?", "why_it_matters": "blocks FR-002"},
            ],
            "glossary": [],
        }
    }


def base_answers(answered=True):
    return {"answers": [{"open_question_id": "OQ-01", "answer": "$500" if answered else None}]}


def base_requirements():
    return {
        "requirements": {
            "functional": [
                {
                    "id": "FR-001",
                    "title": "Submit report",
                    "description": "An Employee submits an Expense Report.",
                    "actor": "STK-01",
                    "trigger": "t",
                    "acceptance_criteria": [{"given": "g", "when": "w", "then": "t"}],
                    "priority": "MUST",
                    "source": "raw_request",
                    "status": "CONFIRMED",
                },
                {
                    "id": "FR-002",
                    "title": "Approve report",
                    "description": "A Manager approves an Expense Report above the threshold.",
                    "actor": "STK-02",
                    "trigger": "t",
                    "acceptance_criteria": [{"given": "g", "when": "w", "then": "t"}],
                    "priority": "MUST",
                    "source": "OQ-01",
                    "status": "CONFIRMED",
                },
            ],
            "non_functional": [
                {
                    "id": "NFR-001",
                    "category": "AVAILABILITY",
                    "requirement": "available",
                    "metric": "99.5% availability per month",
                    "priority": "MUST",
                },
            ],
            "entities": [
                {"name": "Expense Report", "description": "d", "attributes": []},
            ],
            "state_models": [
                {
                    "entity": "Expense Report",
                    "values": ["SUBMITTED", "APPROVED", "REJECTED", "PAID"],
                    "transitions": [
                        {"from": "SUBMITTED", "to": "APPROVED", "trigger": "t1", "guard": None},
                        {"from": "SUBMITTED", "to": "REJECTED", "trigger": "t2", "guard": None},
                        {"from": "REJECTED", "to": "SUBMITTED", "trigger": "t3", "guard": None},
                        {"from": "APPROVED", "to": "PAID", "trigger": "t4", "guard": None},
                    ],
                }
            ],
            "open_items": [],
        }
    }


def run(discovery=None, requirements=None, answers=None):
    d = discovery if discovery is not None else base_discovery()
    r = requirements if requirements is not None else base_requirements()
    a = answers if answers is not None else base_answers()
    return run_deterministic_rules(d, r, a)


def rules_fired(issues):
    return {i.rule for i in issues}


class TestCleanBaselineHasNoIssues(unittest.TestCase):
    def test_clean_fixture_produces_zero_issues(self):
        issues = run()
        self.assertEqual(issues, [], f"expected no issues on the clean baseline, got: {issues}")


class TestSeededErrors(unittest.TestCase):
    """Each test mutates exactly one thing and asserts the matching rule fires."""

    def test_R0_inference_without_reason(self):
        d = base_discovery()
        d["discovery"]["assumptions"][0]["reason"] = ""
        issues = run(discovery=d)
        self.assertIn("R0", rules_fired(issues))

    def test_R1_fr_references_unknown_actor(self):
        r = base_requirements()
        r["requirements"]["functional"][0]["actor"] = "STK-99"
        issues = run(requirements=r)
        self.assertIn("R1", rules_fired(issues))

    def test_R2_duplicate_requirement_id(self):
        r = base_requirements()
        r["requirements"]["functional"][1]["id"] = "FR-001"  # collides with FR-001
        issues = run(requirements=r)
        self.assertIn("R2", rules_fired(issues))

    def test_R3_must_confirmed_on_unanswered_question(self):
        a = base_answers(answered=False)  # OQ-01 left unanswered
        # FR-002's source is OQ-01 and it is MUST + CONFIRMED in the baseline
        issues = run(answers=a)
        self.assertIn("R3", rules_fired(issues))

    def test_R3_does_not_fire_when_question_is_answered(self):
        issues = run()  # baseline answers OQ-01
        self.assertNotIn("R3", rules_fired(issues))

    def test_R4_fr_without_acceptance_criteria(self):
        r = base_requirements()
        r["requirements"]["functional"][0]["acceptance_criteria"] = []
        issues = run(requirements=r)
        self.assertIn("R4", rules_fired(issues))

    def test_R5_vague_nfr_metric(self):
        r = base_requirements()
        r["requirements"]["non_functional"][0]["metric"] = "should be fast"
        issues = run(requirements=r)
        self.assertIn("R5", rules_fired(issues))

    def test_R6_dropped_open_question(self):
        a = base_answers(answered=False)
        r = base_requirements()
        # Break the only link back to OQ-01: change FR-002's source so the
        # unanswered question is referenced nowhere.
        r["requirements"]["functional"][1]["source"] = "raw_request"
        r["requirements"]["functional"][1]["status"] = "DRAFT"  # avoid also tripping R3
        r["requirements"]["functional"][1]["priority"] = "SHOULD"
        issues = run(requirements=r, answers=a)
        self.assertIn("R6", rules_fired(issues))

    def test_R7_transition_references_undeclared_state(self):
        r = base_requirements()
        r["requirements"]["state_models"][0]["transitions"][0]["to"] = "APPRVED"  # typo
        issues = run(requirements=r)
        self.assertIn("R7", rules_fired(issues))

    def test_R8_unreachable_state(self):
        r = base_requirements()
        r["requirements"]["state_models"][0]["values"].append("ARCHIVED")  # never used
        issues = run(requirements=r)
        self.assertIn("R8", rules_fired(issues))

    def test_R9_entity_naming_drift(self):
        r = base_requirements()
        r["requirements"]["functional"][0]["description"] = (
            "An Employee submits a Reimbursement Request."  # not "Expense Report"
        )
        issues = run(requirements=r)
        self.assertIn("R9", rules_fired(issues))


class TestMutationIsolation(unittest.TestCase):
    """A seeded mutation should not spuriously trip unrelated rules."""

    def test_R4_mutation_does_not_also_trigger_R1_or_R2(self):
        r = base_requirements()
        r["requirements"]["functional"][0]["acceptance_criteria"] = []
        issues = run(requirements=r)
        fired = rules_fired(issues)
        self.assertNotIn("R1", fired)
        self.assertNotIn("R2", fired)

    def test_deep_copy_safety(self):
        # Guard against a mutation test accidentally sharing state with the
        # baseline fixture (would make other tests order-dependent).
        r1 = base_requirements()
        r2 = base_requirements()
        r1["requirements"]["functional"][0]["id"] = "CHANGED"
        self.assertEqual(r2["requirements"]["functional"][0]["id"], "FR-001")


if __name__ == "__main__":
    unittest.main(verbosity=2)
