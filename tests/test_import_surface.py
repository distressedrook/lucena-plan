"""The installed-surface smoke test: every module named in pyproject's
py-modules must import. This is the cheapest, highest-yield regression — it
would have caught `dynamism` being absent from py-modules (which silently
broke every sheet build of an installed package)."""
import importlib
import os

try:
    import tomllib
except ModuleNotFoundError:            # py<3.11
    tomllib = None

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _py_modules():
    if tomllib is None:
        pytest.skip("tomllib unavailable (py<3.11)")
    with open(os.path.join(_ROOT, "pyproject.toml"), "rb") as fh:
        return tomllib.load(fh)["tool"]["setuptools"]["py-modules"]


def test_every_py_module_imports():
    mods = _py_modules()
    assert mods, "py-modules is empty"
    for m in mods:
        importlib.import_module(m)


def test_py_modules_matches_src_dir():
    """Every src/*.py (except dunder/CLI-only helpers) is declared, and every
    declared module has a file — the omission that bit `dynamism` cannot recur
    silently."""
    mods = set(_py_modules())
    on_disk = {f[:-3] for f in os.listdir(os.path.join(_ROOT, "src"))
               if f.endswith(".py") and not f.startswith("_")}
    missing = on_disk - mods
    assert not missing, f"src modules not in py-modules: {sorted(missing)}"
    phantom = mods - on_disk
    assert not phantom, f"py-modules entries with no src file: {sorted(phantom)}"
