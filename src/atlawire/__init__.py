"""Command-line interface and library for self-hosted Atlassian products."""

from atlawire.http import AtlaWireError
from atlawire.operations import describe_operation, list_operations, read_operation
from atlawire.sdk import SdkRequestError, client_for, get_json, request_json

__version__ = "0.1.0.dev0"

__all__ = [
    "AtlaWireError",
    "SdkRequestError",
    "__version__",
    "client_for",
    "describe_operation",
    "get_json",
    "list_operations",
    "read_operation",
    "request_json",
]
