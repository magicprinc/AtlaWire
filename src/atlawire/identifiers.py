"""One grammar per identifier concept, shared by every module that validates it.

Each Atlassian product spells its identifiers differently, and the differences are
not cosmetic: a Bitbucket project key allows a personal-project prefix, lowercase,
dots and dashes, while a Jira project key is uppercase letters, digits and
underscores only. Keeping one compiled pattern per concept here means a change to
a grammar happens once, and a module cannot silently validate against the other
product's rules.

The numeric limits are here for the same reason: a page size or a pull-request id
ceiling that two modules disagree about is a defect waiting for the right input.
"""

import re

__all__ = [
    "BITBUCKET_PROJECT_KEY",
    "COMMIT_SHA1",
    "DIFF_CONTEXT_MAX",
    "JIRA_PROJECT_KEY",
    "PAGE_SIZE",
    "PULL_REQUEST_ID_MAX",
    "REPOSITORY_SLUG",
]

# A Bitbucket project key, optionally prefixed with `~` for a personal project.
BITBUCKET_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
# A Bitbucket repository slug.
REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
# A Jira project key: uppercase letters, digits and underscore, starting with a
# letter. Bitbucket's grammar is deliberately not reused here.
JIRA_PROJECT_KEY = re.compile(r"[A-Z][A-Z0-9_]+")
# A full Git commit id; a short id is validated separately where it is accepted.
COMMIT_SHA1 = re.compile(r"[0-9A-Fa-f]{40}")
# The largest pull-request id a signed 64-bit server accepts.
PULL_REQUEST_ID_MAX = 2**63 - 1
# Rows requested per page by default.
PAGE_SIZE = 100
# Largest diff context a Bitbucket diff route accepts.
DIFF_CONTEXT_MAX = 100
