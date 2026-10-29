"""Run reviewed generated tests in a short-lived Docker container."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4
from dataclasses import asdict, dataclass
from pathlib import Path

from app.generator import validate_generated_tests, validate_generation_input

DEFAULT_IMAGE = "ai-test-case-generator-runner:local"
MAX_RUN_SECONDS = 15
OUTPUT_LIMIT = 12_000


class RunnerError(Exception):
    """The isolated test runner could not be started safely."""


@dataclass(frozen=True)
class TestRunResult:
    passed: bool
    exit_code: int | None
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _docker_command(workdir: Path, image: str, container_name: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--memory=256m",
        "--cpus=0.5",
        "--user=65532:65532",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
        "--volume",
        f"{workdir}:/workspace:ro",
        "--workdir=/workspace",
        "--env=HOME=/tmp",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        "--env=PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        image,
        "python",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "test_generated.py",
    ]


def run_generated_tests(
    source_filename: str,
    source_code: str,
    test_code: str,
    *,
    timeout_seconds: int = MAX_RUN_SECONDS,
) -> TestRunResult:
    """Execute only the two submitted files in an isolated, networkless container."""
    source_filename = validate_generation_input("Run reviewed tests", source_code, source_filename)
    if not test_code.strip():
        raise ValueError("Generated test code is required.")
    validate_generated_tests(test_code, source_filename)

    docker = shutil.which("docker")
    if docker is None:
        raise RunnerError("Docker is not installed or is not available on PATH.")
    image = os.getenv("TEST_RUNNER_IMAGE", DEFAULT_IMAGE)
    container_name = f"ai-test-run-{uuid4().hex[:12]}"
    try:
        inspect = subprocess.run(
            [docker, "image", "inspect", image], capture_output=True, text=True, check=False, timeout=5
        )
    except subprocess.TimeoutExpired as exc:
        raise RunnerError("Docker Engine did not respond in time. Check that Docker Desktop is running.") from exc
    if inspect.returncode != 0:
        diagnostic = (inspect.stderr or "").lower()
        if any(marker in diagnostic for marker in ("daemon", "connect", "permission denied", "socket")):
            raise RunnerError("Docker Engine is not running or is not accessible. Start Docker Desktop and retry.")
        raise RunnerError(
            "The test runner image is missing. Build it with: "
            "docker build -t ai-test-case-generator-runner:local -f docker/runner.Dockerfile ."
        )

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ai-test-run-") as temp_dir:
        directory = Path(temp_dir)
        (directory / source_filename).write_text(source_code, encoding="utf-8")
        (directory / "test_generated.py").write_text(test_code, encoding="utf-8")
        command = _docker_command(directory, image, container_name)
        command[0] = docker
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
            return TestRunResult(
                passed=completed.returncode == 0,
                exit_code=completed.returncode,
                timed_out=False,
                duration_seconds=round(time.monotonic() - started, 3),
                stdout=completed.stdout[-OUTPUT_LIMIT:],
                stderr=completed.stderr[-OUTPUT_LIMIT:],
            )
        except subprocess.TimeoutExpired as exc:
            # The CLI may be killed before Docker's daemon has stopped the
            # container, so explicitly remove the named container as well.
            try:
                subprocess.run(
                    [docker, "rm", "--force", container_name],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=5,
                )
            except subprocess.TimeoutExpired:
                pass
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            return TestRunResult(
                passed=False,
                exit_code=None,
                timed_out=True,
                duration_seconds=round(time.monotonic() - started, 3),
                stdout=stdout[-OUTPUT_LIMIT:],
                stderr=(stderr + "\nTest execution exceeded the time limit.")[-OUTPUT_LIMIT:],
            )
