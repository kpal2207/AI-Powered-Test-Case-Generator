"""FastAPI routes for generation and reviewed test execution."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.generator import (
    MAX_FEATURE_LENGTH,
    MAX_SOURCE_LENGTH,
    GenerationError,
    generate_tests,
    validate_generation_input,
)
from app.runner import RunnerError, run_generated_tests

app = FastAPI(title="AI Powered Test Case Generator", version="0.1.0")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerateRequest(StrictModel):
    feature_description: str = Field(min_length=1, max_length=MAX_FEATURE_LENGTH)
    source_filename: str = Field(min_length=1, max_length=100)
    source_code: str = Field(min_length=1, max_length=MAX_SOURCE_LENGTH)


class RunRequest(StrictModel):
    source_filename: str = Field(min_length=1, max_length=100)
    source_code: str = Field(min_length=1, max_length=MAX_SOURCE_LENGTH)
    test_code: str = Field(min_length=1, max_length=MAX_SOURCE_LENGTH)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/generate")
def generate(request: GenerateRequest) -> dict[str, str]:
    try:
        validate_generation_input(request.feature_description, request.source_code, request.source_filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        result = generate_tests(request.feature_description, request.source_code, request.source_filename)
    except GenerationError as exc:
        status = 503 if "OPENAI_API_KEY" in str(exc) or "OPENAI_MODEL" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"filename": result.filename, "test_code": result.code}


@app.post("/api/run")
def run(request: RunRequest) -> dict[str, object]:
    try:
        result = run_generated_tests(request.source_filename, request.source_code, request.test_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RunnerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return result.to_dict()
