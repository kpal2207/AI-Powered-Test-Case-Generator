# AI Powered Test Case Generator

A local learning app that uses an OpenAI model to draft pytest unit tests from a feature description and one pasted Python module. The app shows the test code for review, lets you download it, and runs it only after you click the run button.

## Requirements

- Python 3.14 or newer in the local development environment
- Docker Desktop (or another working Docker Engine)
- An OpenAI API key and access to the model configured in `OPENAI_MODEL`

The generator uses the official OpenAI Python SDK and Responses API. The app sends the feature description and pasted Python source to the configured model; set `store=False` is used for the response request.

## Setup

From the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and replace `your-api-key-here` with your key. Never commit `.env`.

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

Open the local URL Streamlit prints in the terminal. The API is available at `http://127.0.0.1:8000`; interactive API docs are at `http://127.0.0.1:8000/docs`.

## Use the app

1. Describe the behavior you want tested.
2. Enter a simple source filename, such as `calculator.py`, and paste that module's code.
3. Generate and review the pytest code. Download it if you want to keep it.
4. Click **Run reviewed tests** to run the generated tests against the submitted source snapshot.

The runner creates a temporary folder with only the pasted source and test file. Docker runs with networking disabled, a read-only filesystem and input mount, dropped Linux capabilities, memory/CPU/PID limits, and a time limit. The temporary folder is removed after the run. Tests should use only Python's standard library and pytest; this first version does not install project-specific dependencies.

## Learning path: the core logic

The app separates the API and UI scaffolding from the generation pipeline in `app/generator.py`:

1. `build_prompt` defines the task and separates the user's requirement/source from model instructions.
2. `generate_tests` sends the prompt through the OpenAI Responses API.
3. `extract_python_code` removes an optional single Markdown code fence.
4. `validate_generated_tests` parses the result and checks that pytest can discover a test and that it imports the supplied module.

Try changing one part at a time: first ask for boundary cases, then add an edge-case requirement to the prompt, and finally write a test for how the output validator handles invalid code. The model output is a draft and should be reviewed before execution.

## API

- `POST /api/generate` accepts `feature_description`, `source_filename`, and `source_code`; returns `filename` and `test_code`.
- `POST /api/run` accepts `source_filename`, `source_code`, and `test_code`; returns `passed`, `exit_code`, `timed_out`, `duration_seconds`, `stdout`, and `stderr`.
- `GET /health` returns the API health status.

## Checks

Run unit and API tests:

```bash
pytest -q
```

Run Docker integration checks (after building the runner image):

```bash
RUN_DOCKER_TESTS=1 pytest -q tests/test_runner.py
```

The generation tests use a fake Responses API client, so they do not use an API key or incur model usage.

## Current limits

- One pasted Python module per generation.
- Standard-library dependencies only for executed code.
- Tests are generated as unit tests, not project-wide integration tests.
- No automatic file writes, commits, CI/CD, or hosted deployment.
