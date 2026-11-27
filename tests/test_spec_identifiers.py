"""Pin the identifier grammar each product actually enforces.

These tests exist before the refactor and must pass after it unchanged. They state
the behaviour, not the implementation: a Bitbucket project key and a Jira project
key are different grammars, and a refactor that unifies them is a defect.
"""

import pytest

from atlawire import (
    bitbucket,
    bitbucket_attachment,
    bitbucket_search,
    jira_comments_search,
    jira_metadata,
    pr_review,
    repo_grep,
    repo_scan,
)

# Values a Bitbucket project key must accept: it allows a personal-project prefix,
# lowercase, dots and dashes.
BITBUCKET_ACCEPTED = ["DEMO", "demo", "~user", "AB-1", "A_B.C", "1", "~a"]
BITBUCKET_REJECTED = ["", "-x", "A B", "a/b", ".leading", "КИРИЛЛИЦА"]

# A Jira project key is uppercase letters, digits and underscore, and nothing else.
JIRA_ACCEPTED = ["DEMO", "AB", "A_B", "A1", "PROJ_2024"]
JIRA_REJECTED = ["", "demo", "~user", "AB-1", "A.B", "1", "A B", "A/B"]

BITBUCKET_MODULES = (
    bitbucket,
    bitbucket_attachment,
    bitbucket_search,
    pr_review,
    repo_grep,
    repo_scan,
)
JIRA_MODULES = (jira_comments_search, jira_metadata)


@pytest.mark.parametrize("module", BITBUCKET_MODULES, ids=lambda m: m.__name__)
@pytest.mark.parametrize("value", BITBUCKET_ACCEPTED)
def test_bitbucket_project_key_accepts(module, value):
    assert module._PROJECT_KEY.fullmatch(value), f"{module.__name__} rejected {value!r}"


@pytest.mark.parametrize("module", BITBUCKET_MODULES, ids=lambda m: m.__name__)
@pytest.mark.parametrize("value", BITBUCKET_REJECTED)
def test_bitbucket_project_key_rejects(module, value):
    assert module._PROJECT_KEY.fullmatch(value) is None, (
        f"{module.__name__} accepted {value!r}"
    )


@pytest.mark.parametrize("module", JIRA_MODULES, ids=lambda m: m.__name__)
@pytest.mark.parametrize("value", JIRA_ACCEPTED)
def test_jira_project_key_accepts(module, value):
    assert module._PROJECT_KEY.fullmatch(value), f"{module.__name__} rejected {value!r}"


@pytest.mark.parametrize("module", JIRA_MODULES, ids=lambda m: m.__name__)
@pytest.mark.parametrize("value", JIRA_REJECTED)
def test_jira_project_key_rejects(module, value):
    assert module._PROJECT_KEY.fullmatch(value) is None, (
        f"{module.__name__} accepted {value!r}"
    )


SLUG_ACCEPTED = ["repo", "my-repo", "my.repo", "my_repo", "R1", "-x"]
SLUG_REJECTED = ["", "a b", "a/b", "КИРИЛЛИЦА"]
SLUG_MODULES = (bitbucket, bitbucket_attachment, bitbucket_search, pr_review, repo_grep)


@pytest.mark.parametrize("module", SLUG_MODULES, ids=lambda m: m.__name__)
@pytest.mark.parametrize("value", SLUG_ACCEPTED)
def test_repository_slug_accepts(module, value):
    assert module._REPOSITORY_SLUG.fullmatch(value), (
        f"{module.__name__} rejected {value!r}"
    )


@pytest.mark.parametrize("module", SLUG_MODULES, ids=lambda m: m.__name__)
@pytest.mark.parametrize("value", SLUG_REJECTED)
def test_repository_slug_rejects(module, value):
    assert module._REPOSITORY_SLUG.fullmatch(value) is None, (
        f"{module.__name__} accepted {value!r}"
    )


def test_the_two_project_key_grammars_are_not_interchangeable():
    """A Bitbucket key is not a Jira key: this is the trap the refactor removes."""
    assert bitbucket._PROJECT_KEY.fullmatch("~user")
    assert jira_metadata._PROJECT_KEY.fullmatch("~user") is None
    assert jira_metadata._PROJECT_KEY.fullmatch("AB-1") is None
    assert bitbucket._PROJECT_KEY.fullmatch("demo")


def test_every_module_shares_one_compiled_pattern_per_concept():
    """After the refactor there is one object per concept, so drift is impossible."""
    from atlawire import identifiers

    assert len({id(m._PROJECT_KEY) for m in BITBUCKET_MODULES}) == 1
    assert bitbucket._PROJECT_KEY is identifiers.BITBUCKET_PROJECT_KEY
    assert jira_metadata._PROJECT_KEY is identifiers.JIRA_PROJECT_KEY
    assert len({id(m._REPOSITORY_SLUG) for m in SLUG_MODULES}) == 1
    assert bitbucket._REPOSITORY_SLUG is identifiers.REPOSITORY_SLUG


def test_shared_numeric_limits_have_one_value():
    from atlawire import identifiers

    assert bitbucket._COMMIT_SHA1 is identifiers.COMMIT_SHA1
    assert repo_grep._COMMIT_SHA1 is identifiers.COMMIT_SHA1
    assert bitbucket._PULL_REQUEST_ID_MAX == identifiers.PULL_REQUEST_ID_MAX
    assert pr_review._PULL_REQUEST_ID_MAX == identifiers.PULL_REQUEST_ID_MAX
    assert bitbucket._DIFF_CONTEXT_MAX == identifiers.DIFF_CONTEXT_MAX
    assert pr_review._DIFF_CONTEXT_MAX == identifiers.DIFF_CONTEXT_MAX
