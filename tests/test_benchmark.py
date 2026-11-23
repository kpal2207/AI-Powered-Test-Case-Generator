from types import SimpleNamespace

from benchmarks.run_benchmark import evaluate_cases


def test_benchmark_computes_pass_rate_mutation_detection_and_latency(monkeypatch):
    monkeypatch.setattr(
        "benchmarks.run_benchmark.generate_tests",
        lambda *_args: SimpleNamespace(code="generated tests", attempts=2),
    )
    results = iter(
        [
            SimpleNamespace(passed=True, duration_seconds=0.12),
            SimpleNamespace(passed=False, duration_seconds=0.10),
        ]
    )
    monkeypatch.setattr("benchmarks.run_benchmark.run_generated_tests", lambda *_args: next(results))
    report = evaluate_cases(
        [
            {
                "id": "toy",
                "feature_description": "does the thing",
                "source_filename": "toy.py",
                "source_code": "def thing(): return True",
                "mutant_source_code": "def thing(): return False",
            }
        ]
    )

    assert report["case_count"] == 1
    assert report["reference_pass_rate"] == 1.0
    assert report["mutation_detection_rate"] == 1.0
    assert report["cases"][0]["generation_attempts"] == 2


def test_benchmark_records_case_errors_and_returns_zero_rates(monkeypatch):
    def fail(*_args):
        raise ValueError("test runner unavailable")

    monkeypatch.setattr("benchmarks.run_benchmark.generate_tests", fail)
    report = evaluate_cases(
        [{
            "id": "toy",
            "feature_description": "does the thing",
            "source_filename": "toy.py",
            "source_code": "def thing(): return True",
            "mutant_source_code": "def thing(): return False",
        }]
    )

    assert report["reference_pass_rate"] == 0.0
    assert report["mutation_detection_rate"] == 0.0
    assert report["cases"][0]["error"] == "test runner unavailable"
