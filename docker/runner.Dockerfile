FROM python:3.14-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m pip install --no-cache-dir "pytest>=8,<10"

USER 65532:65532
WORKDIR /workspace
