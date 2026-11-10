"""Develop against a selected host; reuse its short owned pytest workspace."""

import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOST_ROOT = Path(os.environ.get("DSH_HOST_ROOT", str(PROJECT_ROOT.parents[1]))).resolve()
if not (HOST_ROOT / "dsh" / "plugin_api.py").is_file():
    raise RuntimeError("Set DSH_HOST_ROOT to the DSH Win7 source checkout.")
sys.path.insert(0, str(HOST_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from scripts.process_artifact_retention import configure_pytest_workspace, prune_pytest_session


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    configure_pytest_workspace(config, HOST_ROOT / ".goose" / "out")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    prune_pytest_session(session, exitstatus, HOST_ROOT / ".goose" / "out")
