"""The package root exposes only the documented, single-registry surface."""

import atlawire


def test_public_exports_resolve_and_are_declared():
    for name in atlawire.__all__:
        assert hasattr(atlawire, name), name


def test_version_is_present():
    assert isinstance(atlawire.__version__, str)
    assert atlawire.__version__


def test_facade_class_is_not_part_of_the_public_surface():
    assert not hasattr(atlawire, "AtlaWire")
    assert not hasattr(atlawire, "facade")


def test_product_and_helper_modules_import():
    from atlawire import bitbucket, confluence, federated, identity, jira
    from atlawire import operations, repo_grep, repo_scan, sdk

    for module in (
        bitbucket,
        confluence,
        federated,
        identity,
        jira,
        operations,
        repo_grep,
        repo_scan,
        sdk,
    ):
        assert module.__name__.startswith("atlawire.")


def test_atlawire_error_is_the_shared_transport_error():
    from atlawire.http import AtlaWireError

    assert atlawire.AtlaWireError is AtlaWireError
