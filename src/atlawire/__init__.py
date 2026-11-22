"""Command-line interface and library for self-hosted Atlassian products."""

from atlawire.sdk import SdkRequestError, client_for, get_json, request_json

__version__ = "0.1.0.dev0"

__all__ = [
    "SdkRequestError",
    "__version__",
    "client_for",
    "get_json",
    "request_json",
]
