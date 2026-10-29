from fastapi.testclient import TestClient
import pytest

from app import main
from app.generator import GeneratedTests, GenerationError
from app.main import app

client = TestClient(app)


def valid_generate_payload():
    return {
        "feature_description": "add two values",
        "source_filename": "calculator.py",
        "source_code": "def add(left, right):\n    return left + right\n",
    }


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generate_endpoint_returns_test_module(monkeypatch):
    monkeypatch.setattr(main, "generate_tests", lambda *_args: GeneratedTests("test_generated.py", "def test_add():\n    assert True\n"))
    response = client.post("/api/generate", json=valid_generate_payload())
    assert response.status_code == 200
    assert response.json()["filename"] == "test_generated.py"


def test_generate_endpoint_rejects_bad_source(monkeypatch):
    monkeypatch.setattr(main, "generate_tests", lambda *_args: pytest.fail("should not call model"))
    payload = valid_generate_payload()
    payload["source_filename"] = "../unsafe.py"
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 422


def test_generate_endpoint_reports_missing_configuration(monkeypatch):
    def fail(*_args):
        raise GenerationError("Set OPENAI_API_KEY in your local .env file before generating tests.")

    monkeypatch.setattr(main, "generate_tests", fail)
    response = client.post("/api/generate", json=valid_generate_payload())
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_run_endpoint_returns_results(monkeypatch):
    monkeypatch.setattr(main, "run_generated_tests", lambda *_args: type("Result", (), {
        "to_dict": lambda self: {
            "passed": True,
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "1 passed",
            "stderr": "",
        }
    })())
    payload = {
        "source_filename": "calculator.py",
        "source_code": "def add(left, right):\n    return left + right\n",
        "test_code": "from calculator import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    }
    response = client.post("/api/run", json=payload)
    assert response.status_code == 200
    assert response.json()["passed"] is True


def test_run_endpoint_rejects_bad_test_import():
    payload = {
        "source_filename": "calculator.py",
        "source_code": "def add(left, right):\n    return left + right\n",
        "test_code": "def test_add():\n    assert True\n",
    }
    response = client.post("/api/run", json=payload)
    assert response.status_code == 422
