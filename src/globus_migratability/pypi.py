"""Helper for polling PyPI for the latest published globus-sdk release.

GitHub Actions has no native trigger for "a release was published on a
different project's PyPI/GitHub", so the workflow polls on a schedule and
uses this module to detect a version change before doing a full run.
"""

from __future__ import annotations

import requests

PYPI_URL = "https://pypi.org/pypi/globus-sdk/json"


def latest_version(timeout: float = 15.0) -> str:
    resp = requests.get(PYPI_URL, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["info"]["version"]
