import os
import shutil
import subprocess

import pytest

from app.runner import run_generated_tests

requires_docker = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_TESTS") != "1" or shutil.which("docker") is None,
    reason="Set RUN_DOCKER_TESTS=1 and install the local runner image to run Docker integration checks.",
)

SOURCE = "def add(left, right):\n    return left + right\n"


@requires_docker
def test_runner_reports_passing_generated_test():
    tests = "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    result = run_generated_tests("calculator.py", SOURCE, tests)
    assert result.passed is True
    assert "1 passed" in result.stdout


@requires_docker
def test_runner_reports_failing_generated_test():
    tests = "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 99\n"
    result = run_generated_tests("calculator.py", SOURCE, tests)
    assert result.passed is False
    assert result.exit_code != 0
    assert "1 failed" in result.stdout


@requires_docker
def test_runner_enforces_timeout():
    tests = (
        "from calculator import add\n\ndef test_slow():\n"
        "    while True:\n        pass\n"
    )
    result = run_generated_tests("calculator.py", SOURCE, tests, timeout_seconds=2)
    assert result.timed_out is True
    assert result.passed is False


def test_runner_cleans_up_named_container_after_timeout(monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[1] == "run":
            raise subprocess.TimeoutExpired(command, timeout=1, output="", stderr="")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.runner.shutil.which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr("app.runner.subprocess.run", fake_run)
    tests = "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"

    result = run_generated_tests("calculator.py", SOURCE, tests, timeout_seconds=1)

    assert result.timed_out is True
    run_command = calls[1]
    container_name = run_command[run_command.index("--name") + 1]
    assert calls[2] == ["/usr/bin/docker", "rm", "--force", container_name]
