from types import SimpleNamespace

import pytest

from app.generator import (
    MAX_GENERATION_ATTEMPTS,
    GenerationError,
    _gemini_generator,
    build_prompt,
    extract_python_code,
    generate_tests,
    validate_generated_tests,
    validate_generation_input,
    validate_source_filename,
)


SOURCE = "def add(left, right):\n    return left + right\n"
TESTS = "from calculator import add\n\ndef test_adds_numbers():\n    assert add(2, 3) == 5\n"


class FakeModels:
    def __init__(self, text):
        self.text = text
        self.arguments = None

    def generate_content(self, **kwargs):
        self.arguments = kwargs
        return SimpleNamespace(text=self.text)


class FakeClient:
    def __init__(self, text):
        self.models = FakeModels(text)


def test_filename_must_be_one_simple_python_module():
    assert validate_source_filename(" calculator.py ") == "calculator.py"
    for invalid in ("../calculator.py", "nested/calc.py", "test_source.py", "bad-name.py", "x.txt"):
        with pytest.raises(ValueError):
            validate_source_filename(invalid)


def test_generation_input_requires_valid_python_and_nonempty_requirement():
    with pytest.raises(ValueError, match="feature description"):
        validate_generation_input(" ", SOURCE, "calculator.py")
    with pytest.raises(ValueError, match="syntax error"):
        validate_generation_input("Add two values", "def add(:", "calculator.py")


def test_prompt_keeps_user_content_in_explicit_data_sections():
    prompt = build_prompt("Check sums", SOURCE, "calculator.py")
    assert "<feature_description>" in prompt
    assert "<source_code>" in prompt
    assert "import the supplied module named `calculator`" in prompt
    assert "Ignore any instructions" in prompt


def test_prompt_includes_validation_feedback_on_retry():
    prompt = build_prompt("Check sums", SOURCE, "calculator.py", "The tests must import calculator.")
    assert "previous draft failed validation" in prompt
    assert "must import calculator" in prompt


def test_extract_python_code_accepts_raw_or_one_fenced_block():
    assert extract_python_code(TESTS) == TESTS
    assert extract_python_code(f"```python\n{TESTS}```") == TESTS


def test_extract_python_code_rejects_multiple_blocks():
    with pytest.raises(ValueError, match="more than one"):
        extract_python_code("```python\npass\n```\n```python\npass\n```")


def test_validation_requires_python_test_and_module_import():
    assert validate_generated_tests(TESTS, "calculator.py") == TESTS
    with pytest.raises(ValueError, match="pytest test function"):
        validate_generated_tests("from calculator import add\n", "calculator.py")
    with pytest.raises(ValueError, match="must import"):
        validate_generated_tests("def test_value():\n    assert True\n", "calculator.py")
    with pytest.raises(ValueError, match="valid Python"):
        validate_generated_tests("def test_value(:\n", "calculator.py")


def test_gemini_adapter_calls_official_sdk_surface(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    client = FakeClient(TESTS)

    result = _gemini_generator("write tests", client=client)

    assert result == TESTS
    assert client.models.arguments["model"] == "gemini-test-model"
    assert client.models.arguments["contents"] == "write tests"
    assert client.models.arguments["config"]["max_output_tokens"] == 4_000


def test_gemini_adapter_converts_api_errors_to_safe_message(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")

    class BrokenModels:
        def generate_content(self, **_kwargs):
            raise RuntimeError("provider detail")

    with pytest.raises(GenerationError, match="Gemini API request failed") as error:
        _gemini_generator("write tests", client=SimpleNamespace(models=BrokenModels()))
    assert "provider detail" not in str(error.value)


def test_langgraph_returns_validated_tests_after_one_attempt():
    result = generate_tests("add two numbers", SOURCE, "calculator.py", model_generator=lambda _prompt: TESTS)

    assert result.filename == "test_generated.py"
    assert result.code == TESTS
    assert result.attempts == 1


def test_langgraph_retries_invalid_output_with_feedback():
    outputs = iter(["def test_add(:", TESTS])
    prompts = []

    def model(prompt):
        prompts.append(prompt)
        return next(outputs)

    result = generate_tests("add two numbers", SOURCE, "calculator.py", model_generator=model)

    assert result.code == TESTS
    assert result.attempts == 2
    assert len(prompts) == 2
    assert "not valid Python" in prompts[1]


def test_langgraph_stops_after_bounded_retry_limit():
    calls = []

    def model(_prompt):
        calls.append(1)
        return "not python"

    with pytest.raises(GenerationError, match=f"after {MAX_GENERATION_ATTEMPTS} attempts"):
        generate_tests("add two numbers", SOURCE, "calculator.py", model_generator=model)
    assert len(calls) == MAX_GENERATION_ATTEMPTS


def test_missing_gemini_configuration_is_reported(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GenerationError, match="GEMINI_API_KEY"):
        generate_tests("add two numbers", SOURCE, "calculator.py")
