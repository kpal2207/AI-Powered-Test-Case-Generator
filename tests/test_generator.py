from types import SimpleNamespace

import pytest

from app.generator import (
    GenerationError,
    build_prompt,
    extract_python_code,
    generate_tests,
    validate_generated_tests,
    validate_generation_input,
    validate_source_filename,
)


SOURCE = "def add(left, right):\n    return left + right\n"
TESTS = "from calculator import add\n\ndef test_adds_numbers():\n    assert add(2, 3) == 5\n"


class FakeResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.arguments = None

    def create(self, **kwargs):
        self.arguments = kwargs
        return SimpleNamespace(output_text=self.output_text)


class FakeClient:
    def __init__(self, output_text: str):
        self.responses = FakeResponses(output_text)


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


def test_generate_tests_calls_responses_api_and_returns_validated_code():
    client = FakeClient(f"```python\n{TESTS}```")

    result = generate_tests("add two numbers", SOURCE, "calculator.py", client=client)

    assert result.filename == "test_generated.py"
    assert result.code == TESTS
    assert client.responses.arguments["store"] is False
    assert "calculator.py" in client.responses.arguments["input"]
    assert "calculator" in client.responses.arguments["input"]


def test_generate_tests_rejects_malformed_model_output():
    with pytest.raises(GenerationError, match="not valid Python"):
        generate_tests("add two numbers", SOURCE, "calculator.py", client=FakeClient("def test_add(:"))
