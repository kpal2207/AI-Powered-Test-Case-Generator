# AI Powered Test Case Generator

A local learning app that uses Gemini to draft pytest unit tests from a feature description and one pasted Python module. A LangGraph workflow generates tests, validates the Python and module import, and retries invalid drafts up to three times. The app shows test code for review, lets you download it, and runs it only after you click the run button.

## Requirements

- Python 3.12 or newer
- Docker Desktop (or another working Docker Engine)
- A Gemini API key

The generator uses Google's official `google-genai` Python SDK. LangGraph handles the generate → validate → retry route. Generated tests are never saved to the project automatically.

## Setup

From the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and replace `your-gemini-api-key-here` with your Gemini API key. Never commit `.env`.

Build the small image used to run generated tests:

```bash
docker build -t ai-test-case-generator-runner:local -f docker/runner.Dockerfile .
```

Start the API in one terminal:

```bash
uvicorn app.main:app --reload
```

Start the UI in a second terminal using the same virtual environment:

```bash
streamlit run app/ui.py
```

Open the local URL Streamlit prints. The API is at `http://127.0.0.1:8000`; interactive API docs are at `http://127.0.0.1:8000/docs`.

## Use the app

1. Describe the behavior you want tested.
2. Enter a simple source filename, such as `calculator.py`, and paste that module's code.
3. Generate and review the pytest code. Download it if you want to keep it.
4. Click **Run reviewed tests** to run the tests against the submitted source snapshot.

The runner creates a temporary folder with only the pasted source and test file. Docker runs with networking disabled, a read-only filesystem and input mount, dropped Linux capabilities, memory/CPU/PID limits, and a time limit. Tests should use only the standard library and pytest; this first version does not install project-specific dependencies.

## Core workflow

The API and UI are scaffolding. The core is in `app/generator.py`:

1. `build_prompt` tells Gemini to treat the user-provided requirement and source as data.
2. The `generate` LangGraph node calls Gemini.
3. The `validate` node extracts Python, parses it, checks for a pytest function, and requires an import of the supplied module.
4. A conditional edge either ends on valid code, retries with the validation error as feedback, or stops after three attempts.
5. FastAPI returns the validated code for review; the user explicitly decides whether to execute it.

## Benchmark

The fixed examples in `benchmarks/cases.json` include a reference implementation and a known mutant. The harness measures reference pass rate, mutation detection rate, Gemini generation latency, Docker test execution times, and retry attempts. It invokes the real Gemini API and Docker runner, so it requires `GEMINI_API_KEY` and the runner image built above; it may incur API usage.

Run it from the project root:

```bash
python -m benchmarks.run_benchmark
```

It writes `benchmark-results.json` (ignored by Git) and prints aggregate metrics. To choose another report path, add `--output path/to/report.json`. Run it again with the same cases and model to compare outcomes; model outputs and API latency can vary. Do not claim scores until the command has completed and you have inspected its report.

## CI and checks

GitHub Actions runs unit/API tests plus Docker runner integration tests on Python 3.12, 3.13, and 3.14 for pushes and pull requests to `main`. The CI tests mock Gemini and need no secrets.

Run checks locally:

```bash
python -m pytest -q
```

Docker integration cases are skipped unless `RUN_DOCKER_TESTS=1`; build the runner image first to execute them explicitly:

```bash
RUN_DOCKER_TESTS=1 python -m pytest -q tests/test_runner.py
```

## API

- `POST /api/generate` accepts `feature_description`, `source_filename`, and `source_code`; returns `filename` and `test_code`.
- `POST /api/run` accepts `source_filename`, `source_code`, and reviewed `test_code`; returns pass/fail, exit code, duration, and output.
- `GET /health` returns the API health status.

## Current limits

- One pasted Python module per generation.
- Standard-library dependencies only for test execution.
- This benchmark is a small reproducible baseline, not a statistically conclusive evaluation.
- No automatic file writes, commits, or hosted deployment.
