"""Streamlit interface for generating, reviewing, running, and downloading tests."""

from __future__ import annotations

import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
REQUEST_TIMEOUT = (5, 55)

st.set_page_config(page_title="AI Test Case Generator", page_icon="🧪", layout="wide")
st.title("AI Powered Test Case Generator")
st.caption("Turn a feature description and one Python module into reviewable pytest unit tests.")
st.info("Generated code is a draft. Review it before running. Test execution uses a temporary, network-disabled Docker container.")

with st.form("generation_form"):
    feature_description = st.text_area(
        "What should the code do?",
        placeholder="Example: A login helper should reject a wrong password and return a clear error.",
        height=120,
    )
    left, right = st.columns([1, 2])
    with left:
        source_filename = st.text_input("Source filename", value="solution.py", help="Use a simple filename such as calculator.py")
    with right:
        source_code = st.text_area(
            "Paste the Python source",
            placeholder="def add(a, b):\n    return a + b",
            height=220,
        )
    generate_clicked = st.form_submit_button("Generate pytest tests", type="primary")

if generate_clicked:
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/generate",
            json={
                "feature_description": feature_description,
                "source_filename": source_filename,
                "source_code": source_code,
            },
            timeout=REQUEST_TIMEOUT,
        )
        if response.ok:
            result = response.json()
            st.session_state.generated_filename = result["filename"]
            st.session_state.generated_test_code = result["test_code"]
            st.session_state.generated_source_filename = source_filename
            st.session_state.generated_source_code = source_code
            st.session_state.run_result = None
        else:
            detail = response.json().get("detail", response.text)
            st.error(f"Generation failed: {detail}")
    except requests.RequestException as exc:
        st.error(f"Could not reach the API at {API_BASE_URL}. Start the FastAPI server and try again. ({exc})")

if st.session_state.get("generated_test_code"):
    st.subheader("Review generated tests")
    st.caption("These tests target the source snapshot submitted above. Generate again if you change the source.")
    st.code(st.session_state.generated_test_code, language="python", line_numbers=True)
    st.download_button(
        "Download test_generated.py",
        data=st.session_state.generated_test_code,
        file_name=st.session_state.generated_filename,
        mime="text/x-python",
    )
    if st.button("Run reviewed tests", type="primary"):
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/run",
                json={
                    "source_filename": st.session_state.generated_source_filename,
                    "source_code": st.session_state.generated_source_code,
                    "test_code": st.session_state.generated_test_code,
                },
                timeout=(5, 25),
            )
            if response.ok:
                st.session_state.run_result = response.json()
            else:
                detail = response.json().get("detail", response.text)
                st.error(f"Could not run tests: {detail}")
        except requests.RequestException as exc:
            st.error(f"Could not reach the API at {API_BASE_URL}. ({exc})")

run_result = st.session_state.get("run_result")
if run_result:
    if run_result["timed_out"]:
        st.warning("Test run timed out.")
    elif run_result["passed"]:
        st.success("All generated tests passed.")
    else:
        st.error("One or more generated tests failed.")
    st.caption(f"Exit code: {run_result['exit_code']} · Duration: {run_result['duration_seconds']} seconds")
    if run_result["stdout"]:
        st.text_area("Test output", run_result["stdout"], height=160)
    if run_result["stderr"]:
        st.text_area("Runner errors", run_result["stderr"], height=120)
