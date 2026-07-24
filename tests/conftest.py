"""Put the flat src/ modules on the path for the test session.

The library is consumed by path-appending src/ (see the backend's
lucena_backend.plans.service._bootstrap), never pip-installed, so the tests
mirror that: add <repo>/src to sys.path. lucena_core must already be importable
(the tactics venv provides it) — run under:
    cd lucena-tactics && .venv/bin/python -m pytest ../lucena-plans/tests/
"""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
