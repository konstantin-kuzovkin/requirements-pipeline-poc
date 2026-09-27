"""Correctness tests for the deterministic test-case generator (agent5a)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import agent5a_deterministic as a5a


def sample_requirements():
    return {
        "requirements": {
            "functional": [
                {
                    "id": "FR-001",
                    "acceptance_criteria": [
                        {"given": "g1", "when": "w1", "then": "t1"},
                        {"given": "g2", "when": "w2", "then": "t2"},
                    ],
                },
            ],
            "state_models": [
                {
                    "entity": "Widget",
                    "values": ["A", "B", "C"],
                    "transitions": [
                        {"from": "A", "to": "B", "trigger": "go_b"},
                        {"from": "B", "to": "C", "trigger": "go_c"},
                    ],
                }
            ],
        }
    }


class TestAcceptanceTests(unittest.TestCase):
    def test_one_test_per_acceptance_criterion(self):
        out = a5a.generate_acceptance_tests(sample_requirements(), [0])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["covers"], ["FR-001"])
        self.assertEqual(out[0]["type"], "POSITIVE")


class TestTransitionTests(unittest.TestCase):
    def test_positive_test_per_declared_transition(self):
        out = a5a.generate_transition_tests(sample_requirements(), [0])
        positive = [t for t in out if t["type"] == "POSITIVE"]
        self.assertEqual(len(positive), 2)  # go_b, go_c

    def test_negative_test_for_every_invalid_trigger_per_state(self):
        out = a5a.generate_transition_tests(sample_requirements(), [0])
        negative = [t for t in out if t["type"] == "NEGATIVE"]
        # triggers = {go_b, go_c}; states = {A, B, C}
        # A: valid={go_b} -> invalid={go_c}            -> 1 negative
        # B: valid={go_c} -> invalid={go_b}             -> 1 negative
        # C: valid={}     -> invalid={go_b, go_c}        -> 2 negative
        self.assertEqual(len(negative), 4)

    def test_negative_test_content_is_specific(self):
        out = a5a.generate_transition_tests(sample_requirements(), [0])
        c_state_negatives = [t for t in out if t["type"] == "NEGATIVE" and "state C" in t["given"]]
        triggers_tested = {t["when"].split(" is attempted")[0] for t in c_state_negatives}
        self.assertEqual(triggers_tested, {"go_b", "go_c"})

    def test_no_negative_test_for_a_states_only_valid_trigger(self):
        out = a5a.generate_transition_tests(sample_requirements(), [0])
        a_state_negatives = [t for t in out if t["type"] == "NEGATIVE" and "state A" in t["given"]]
        for t in a_state_negatives:
            self.assertNotIn("go_b is attempted", t["when"])  # go_b IS valid from A


class TestIdsAreUnique(unittest.TestCase):
    def test_full_run_produces_unique_ids(self):
        out = a5a.run(sample_requirements())
        ids = [t["id"] for t in out["deterministic_tests"]]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
