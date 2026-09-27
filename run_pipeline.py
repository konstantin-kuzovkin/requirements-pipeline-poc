#!/usr/bin/env python3
"""
CLI orchestrator for the Discovery -> Requirements -> Validator slice.

Deliberately a plain script, not a workflow engine: per ADR-004 in the
portfolio, orchestration tooling is justified by long waits, human tasks
measured in hours, or multi-step compensation -- none of which apply here.
The one human checkpoint (answering open questions) is just editing a file
between two script invocations.

Usage:
    python3 run_pipeline.py discovery    --request raw_request.txt --out runs/demo
    # ... edit runs/demo/answers.yaml by hand ...
    python3 run_pipeline.py requirements --run-dir runs/demo
    python3 run_pipeline.py validate     --run-dir runs/demo          # R0-R9 (+ LLM pairwise)
    python3 run_pipeline.py artifacts    --run-dir runs/demo          # Agent 3: diagrams
    python3 run_pipeline.py testdesign   --run-dir runs/demo          # Agent 5: test cases
    python3 run_pipeline.py validate     --run-dir runs/demo          # re-run: adds R10-R17

Requires a real ANTHROPIC_API_KEY and `pip install anthropic` for every LLM
step (discovery, requirements, artifacts, testdesign, and the semantic
half of validate). The deterministic rule checks in validate need neither.
"""
from __future__ import annotations

import argparse
import os
import sys

from pipeline import (
    agent1_discovery,
    agent2_requirements,
    agent3_artifacts,
    agent4_validator,
    agent5_testdesign,
)
from pipeline.llm_client import AnthropicLLMClient
from pipeline.yaml_io import dump_yaml_file, load_yaml_file


def cmd_discovery(args):
    os.makedirs(args.out, exist_ok=True)
    with open(args.request, encoding="utf-8") as f:
        raw_request = f.read()

    client = AnthropicLLMClient()
    discovery = agent1_discovery.run(client, raw_request)
    dump_yaml_file(os.path.join(args.out, "01-discovery.yaml"), discovery)

    # Scaffold an answers file the analyst edits by hand before the next step.
    answers_path = os.path.join(args.out, "answers.yaml")
    if not os.path.exists(answers_path):
        oqs = discovery.get("discovery", {}).get("open_questions", [])
        dump_yaml_file(answers_path, {
            "answers": [{"open_question_id": oq["id"], "answer": None} for oq in oqs]
        })
    print(f"Wrote {args.out}/01-discovery.yaml")
    print(f"{len(discovery.get('discovery', {}).get('open_questions', []))} open question(s) "
          f"-- edit {answers_path} before running the requirements step.")


def cmd_requirements(args):
    discovery = load_yaml_file(os.path.join(args.run_dir, "01-discovery.yaml"))
    answers = load_yaml_file(os.path.join(args.run_dir, "answers.yaml"))

    unanswered = [a["open_question_id"] for a in answers.get("answers", []) if not a.get("answer")]
    if unanswered:
        print(f"NOTE: {len(unanswered)} open question(s) still unanswered: {unanswered}")
        print("Agent 2 will mark dependent requirements as DRAFT rather than guess.")

    client = AnthropicLLMClient()
    requirements = agent2_requirements.run(client, discovery, answers)
    dump_yaml_file(os.path.join(args.run_dir, "02-requirements.yaml"), requirements)
    print(f"Wrote {args.run_dir}/02-requirements.yaml")


def cmd_validate(args):
    discovery = load_yaml_file(os.path.join(args.run_dir, "01-discovery.yaml"))
    requirements = load_yaml_file(os.path.join(args.run_dir, "02-requirements.yaml"))
    answers = load_yaml_file(os.path.join(args.run_dir, "answers.yaml"))

    artifacts_path = os.path.join(args.run_dir, "03-artifacts.yaml")
    artifacts = load_yaml_file(artifacts_path) if os.path.exists(artifacts_path) else None
    tests_path = os.path.join(args.run_dir, "05-tests.yaml")
    tests = load_yaml_file(tests_path) if os.path.exists(tests_path) else None

    client = None if args.no_semantic else AnthropicLLMClient()
    report = agent4_validator.run(
        discovery, requirements, answers, client, run_semantic=not args.no_semantic,
        artifacts=artifacts, tests=tests,
    )
    out_name = "04-validation.yaml" if artifacts or tests else "03-validation.yaml"
    dump_yaml_file(os.path.join(args.run_dir, out_name), report)

    summary = report["validation_report"]["summary"]
    print(f"Wrote {args.run_dir}/{out_name}")
    print(f"{summary['errors']} error(s), {summary['warnings']} warning(s)")


def cmd_artifacts(args):
    discovery = load_yaml_file(os.path.join(args.run_dir, "01-discovery.yaml"))
    requirements = load_yaml_file(os.path.join(args.run_dir, "02-requirements.yaml"))

    client = AnthropicLLMClient()
    artifacts = agent3_artifacts.run(discovery, requirements, client)
    dump_yaml_file(os.path.join(args.run_dir, "03-artifacts.yaml"), artifacts)
    print(f"Wrote {args.run_dir}/03-artifacts.yaml")


def cmd_testdesign(args):
    requirements = load_yaml_file(os.path.join(args.run_dir, "02-requirements.yaml"))

    client = AnthropicLLMClient()
    tests = agent5_testdesign.run(requirements, client)
    dump_yaml_file(os.path.join(args.run_dir, "05-tests.yaml"), tests)
    print(f"Wrote {args.run_dir}/05-tests.yaml")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("discovery")
    p1.add_argument("--request", required=True)
    p1.add_argument("--out", required=True)
    p1.set_defaults(func=cmd_discovery)

    p2 = sub.add_parser("requirements")
    p2.add_argument("--run-dir", required=True)
    p2.set_defaults(func=cmd_requirements)

    p3 = sub.add_parser("validate")
    p3.add_argument("--run-dir", required=True)
    p3.add_argument("--no-semantic", action="store_true", help="skip the LLM pairwise layer, deterministic rules only")
    p3.set_defaults(func=cmd_validate)

    p4 = sub.add_parser("artifacts")
    p4.add_argument("--run-dir", required=True)
    p4.set_defaults(func=cmd_artifacts)

    p5 = sub.add_parser("testdesign")
    p5.add_argument("--run-dir", required=True)
    p5.set_defaults(func=cmd_testdesign)

    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
