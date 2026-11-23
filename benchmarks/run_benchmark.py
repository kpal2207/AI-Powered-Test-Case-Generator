"""Run a repeatable Gemini pytest-generation benchmark against fixed examples.

The benchmark expects Docker and GEMINI_API_KEY. It reports latency, whether
generated tests pass the reference implementation, and whether they reject a
known mutant. It never stores generated test source in the project.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from app.generator import GenerationError, generate_tests
from app.runner import RunnerError, run_generated_tests

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = Path(__file__).with_name("cases.json")


def evaluate_cases(cases: list[dict[str, str]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        try:
            generated = generate_tests(
                case["feature_description"], case["source_code"], case["source_filename"]
            )
            generation_seconds = time.perf_counter() - started
            reference = run_generated_tests(
                case["source_filename"], case["source_code"], generated.code
            )
            mutant = run_generated_tests(
                case["source_filename"], case["mutant_source_code"], generated.code
            )
            records.append(
                {
                    "id": case["id"],
                    "generation_seconds": round(generation_seconds, 3),
                    "reference_passed": reference.passed,
                    "mutant_rejected": not mutant.passed,
                    "reference_test_seconds": reference.duration_seconds,
                    "mutant_test_seconds": mutant.duration_seconds,
                    "generation_attempts": generated.attempts,
                    "error": None,
                }
            )
        except (GenerationError, RunnerError, ValueError) as exc:
            records.append(
                {
                    "id": case["id"],
                    "generation_seconds": round(time.perf_counter() - started, 3),
                    "reference_passed": False,
                    "mutant_rejected": False,
                    "reference_test_seconds": None,
                    "mutant_test_seconds": None,
                    "generation_attempts": None,
                    "error": str(exc),
                }
            )

    valid_count = sum(record["reference_passed"] for record in records)
    rejected_count = sum(record["mutant_rejected"] for record in records)
    latencies = [record["generation_seconds"] for record in records]
    return {
        "benchmark_version": 1,
        "model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "python_version": sys.version.split()[0],
        "dataset_sha256": hashlib.sha256(CASES_PATH.read_bytes()).hexdigest(),
        "case_count": len(records),
        "reference_pass_rate": round(valid_count / len(records), 3) if records else 0.0,
        "mutation_detection_rate": round(rejected_count / len(records), 3) if records else 0.0,
        "mean_generation_seconds": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "cases": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark-results.json")
    args = parser.parse_args()
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    report = evaluate_cases(cases)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, indent=2))
    print(f"Detailed results: {args.output}")
    return 0 if report["reference_pass_rate"] == 1.0 and report["mutation_detection_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
