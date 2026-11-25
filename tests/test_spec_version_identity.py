"""C8: the installed distribution must report one version everywhere.

A stale ``.dist-info`` from an earlier install makes `atlawire --version`
disagree with `importlib.metadata.version`, and an agent cannot tell which code
it is running. The check compares the two values that a caller can observe.
"""

import importlib.metadata

import pytest

import atlawire


def test_metadata_and_module_version_agree():
    try:
        reported = importlib.metadata.version("atlawire")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("atlawire is not installed as a distribution here")

    assert reported == atlawire.__version__, (
        "atlawire.__version__ and the installed distribution disagree; a stale "
        ".dist-info is on sys.path - reinstall with "
        "`python -m pip install --user --force-reinstall <wheel>`"
    )
