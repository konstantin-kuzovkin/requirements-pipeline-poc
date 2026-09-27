#!/usr/bin/env python3
"""
Run: python3 eval/run_eval.py

Requires `pip install anthropic` and ANTHROPIC_API_KEY -- this makes real
LLM calls and reports real, measured accuracy of the pairwise contradiction
checker (pipeline/agent4b_semantic.py) against eval/pairwise_pairs.yaml.

This is deliberately not run inside the sandbox that built this PoC: that
sandbox has no network access, so the numbers below have never been
measured yet. Run this yourself and the printed numbers are real. Do not
copy placeholder numbers into a portfolio and call them measured -- that
was exactly the mistake we corrected in case 06's evaluation.md.

Optional: --dry-run uses a FixtureLLMClient that always answers
CONSISTENT, to smoke-test the scoring code itself (parsing, confusion
matrix, precision/recall math) without a network call. Its printed
"accuracy" measures nothing about model quality -- it exists only to prove
the harness's arithmetic is correct before you spend real API calls.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml

from pipeline.agent4b_semantic import check_pair
from pipeline.llm_client import AnthropicLLMClient, FixtureLLMClient


def load_cases():
    path = os.path.join(os.path.dirname(__file__), "pairwise_pairs.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["cases"]


def run(llm_client, cases):
    rows = []
    for case in cases:
        try:
            result = check_pair(llm_client, case["req_a"], case["req_b"])
            predicted = result["result"]
        except Exception as e:  # noqa: BLE001 -- report the failure as a row, don't crash the run
            predicted = f"ERROR: {e}"
        rows.append({"id": case["id"], "expected": case["expected"], "predicted": predicted})
    return rows


def score(rows):
    correct = sum(1 for r in rows if r["predicted"] == r["expected"])
    unclear = sum(1 for r in rows if r["predicted"] == "UNCLEAR")
    errored = sum(1 for r in rows if str(r["predicted"]).startswith("ERROR"))

    tp = sum(1 for r in rows if r["expected"] == "CONTRADICTION" and r["predicted"] == "CONTRADICTION")
    fp = sum(1 for r in rows if r["expected"] == "CONSISTENT" and r["predicted"] == "CONTRADICTION")
    fn = sum(1 for r in rows if r["expected"] == "CONTRADICTION" and r["predicted"] != "CONTRADICTION")
    tn = sum(1 for r in rows if r["expected"] == "CONSISTENT" and r["predicted"] == "CONSISTENT")

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")

    return {
        "n": len(rows),
        "accuracy": correct / len(rows),
        "unclear_rate": unclear / len(rows),
        "error_rate": errored / len(rows),
        "contradiction_precision": precision,
        "contradiction_recall": recall,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                         help="smoke-test the harness with a fixture client that always answers CONSISTENT; "
                              "does not measure real model accuracy")
    args = parser.parse_args()

    cases = load_cases()

    if args.dry_run:
        print("DRY RUN: using a fixture client that always answers CONSISTENT.")
        print("The numbers below test the harness's own arithmetic, NOT model quality.\n")
        fixture_response = "result: CONSISTENT\nreason: \"\"\n"
        llm_client = FixtureLLMClient(responses=[fixture_response] * len(cases))
    else:
        llm_client = AnthropicLLMClient()

    rows = run(llm_client, cases)
    for r in rows:
        mark = "OK " if r["predicted"] == r["expected"] else "!! "
        print(f"{mark}{r['id']:5s} expected={r['expected']:13s} predicted={r['predicted']}")

    result = score(rows)
    print("\n--- results ---")
    print(f"n = {result['n']}")
    print(f"accuracy         = {result['accuracy']:.2f}")
    print(f"unclear_rate     = {result['unclear_rate']:.2f}")
    print(f"error_rate       = {result['error_rate']:.2f}")
    print(f"contradiction precision = {result['contradiction_precision']:.2f}")
    print(f"contradiction recall    = {result['contradiction_recall']:.2f}")
    print(f"confusion (expected CONTRADICTION/CONSISTENT x predicted CONTRADICTION/other) = "
          f"{result['confusion']}")

    if args.dry_run:
        print("\nReminder: these numbers are from the dry-run fixture client, not a real model.")
        print("Run without --dry-run (with ANTHROPIC_API_KEY set) for real numbers.")


if __name__ == "__main__":
    main()
