"""
Correctness tests for the deterministic diagram renderer. Unlike the rule
engine, there's no "seeded error" here to detect -- the point of agent3a
is that it CANNOT diverge from its input, so these tests check the
transpile is faithful and, specifically, that terminal-state detection is
computed from the actual transition graph, not guessed from state names
(this was a real bug caught during development: a name-based guess wrongly
marked REJECTED as terminal even though this fixture allows resubmission).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import agent3a_deterministic as a3a


def sample_requirements():
    return {
        "requirements": {
            "functional": [
                {"id": "FR-002", "actor": "STK-02", "trigger": "t", "priority": "MUST",
                 "status": "CONFIRMED", "acceptance_criteria": [{"given": "g", "when": "w", "then": "t"}],
                 "description": "d", "source": "s", "state_triggers": ["approve", "reject"]},
            ],
            "entities": [
                {"name": "Widget", "attributes": [
                    {"name": "id", "type": "string", "required": True},
                    {"name": "owner_id", "type": "string", "required": True},
                ]},
                {"name": "Owner", "attributes": [{"name": "id", "type": "string", "required": True}]},
            ],
            "state_models": [
                {
                    "entity": "Widget",
                    "values": ["OPEN", "CLOSED", "REOPENED"],
                    "transitions": [
                        {"from": "OPEN", "to": "CLOSED", "trigger": "approve", "guard": None},
                        {"from": "CLOSED", "to": "REOPENED", "trigger": "reopen", "guard": None},
                        {"from": "REOPENED", "to": "CLOSED", "trigger": "approve", "guard": None},
                    ],
                }
            ],
        }
    }


def sample_discovery():
    return {"discovery": {"stakeholders": [{"id": "STK-02", "name": "Manager"}]}}


class TestERDiagram(unittest.TestCase):
    def test_fk_inferred_from_naming_convention(self):
        mermaid = a3a.render_er_diagram(sample_requirements())
        self.assertIn('Owner ||--o{ Widget : "has"', mermaid)

    def test_all_entities_present(self):
        mermaid = a3a.render_er_diagram(sample_requirements())
        self.assertIn("Widget {", mermaid)
        self.assertIn("Owner {", mermaid)


class TestStateDiagram(unittest.TestCase):
    def test_terminal_state_computed_from_graph_not_name(self):
        """
        CLOSED has an outgoing transition (CLOSED -> REOPENED) in this
        fixture, so it must NOT be marked terminal, even though "CLOSED"
        is exactly the kind of name a heuristic might wrongly guess as
        terminal (as REJECTED was, in the real fixture, before this was
        fixed during development).
        """
        diagrams = a3a.render_state_diagrams(sample_requirements())
        mermaid = diagrams[0]["mermaid"]
        self.assertNotIn("CLOSED --> [*]", mermaid)

    def test_only_true_sink_state_is_terminal(self):
        # In this fixture every state has an outgoing transition, so there
        # should be no terminal marker at all.
        diagrams = a3a.render_state_diagrams(sample_requirements())
        mermaid = diagrams[0]["mermaid"]
        self.assertNotIn("--> [*]\n", mermaid.replace("[*] --> OPEN", ""))

    def test_lossless_transition_count(self):
        diagrams = a3a.render_state_diagrams(sample_requirements())
        mermaid = diagrams[0]["mermaid"]
        # 3 transitions in the fixture -> 3 " --> " lines beyond the initial marker
        transition_lines = [l for l in mermaid.split("\n") if " --> " in l and "[*]" not in l]
        self.assertEqual(len(transition_lines), 3)


class TestProcessSkeleton(unittest.TestCase):
    def test_matches_via_state_triggers_not_prose_trigger(self):
        skeletons = a3a.render_process_skeletons(sample_discovery(), sample_requirements())
        mermaid = skeletons[0]["mermaid"]
        self.assertIn("FR-002", mermaid)
        self.assertIn("Manager", mermaid)

    def test_unmatched_trigger_is_reported_not_dropped(self):
        r = sample_requirements()
        r["requirements"]["state_models"][0]["transitions"].append(
            {"from": "CLOSED", "to": "OPEN", "trigger": "escalate", "guard": None}
        )
        skeletons = a3a.render_process_skeletons(sample_discovery(), r)
        unmatched_triggers = {u["trigger"] for u in skeletons[0]["unmatched_transitions"]}
        self.assertIn("escalate", unmatched_triggers)
        # and it must still appear in the diagram, not be silently dropped
        self.assertIn("escalate", skeletons[0]["mermaid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
