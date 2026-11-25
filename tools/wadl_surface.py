"""One reader for the WADL each deployment publishes, shared by the tools.

Three tools need the same facts from the same document: the routes a server
serves, the methods on each, the prose it documents them with, and the query
parameters each method accepts. Keeping one reader means a normalisation bug
cannot exist in one tool and be fixed in another, which is exactly what happened
once already: a trailing-placeholder strip silently merged distinct routes.

Routes have two forms on purpose:

* `readable_route` keeps the documented placeholder names (`/projects/{projectKey}`).
  Human-facing documents use it, because `{projectKey}` tells a reader more than
  `{}`.
* `normalize` collapses every placeholder to `{}`. Comparisons use it, because the
  registry and the WADL spell the same placeholder differently across products.

`route_variants` expands the one construct where a single declaration really
covers two routes: a WADL writes an optional suffix glued to a segment
(`diff{path:.*}`), which serves both `/diff` and `/diff/{path}`.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from defusedxml import ElementTree  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".development"

NS = "http://wadl.dev.java.net/2009/02"
W = f"{{{NS}}}"
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_SLASHES = re.compile(r"/+")
_GLUED = re.compile(r"(?<=[^/{}])\{\}+$")
DOC_TAG = re.compile(r"<[^>]+>")

# WADL types that are integers on the wire. Everything else is text: a date, a
# boolean or an enum travels as a string and the server validates it.
INTEGER_TYPES = frozenset(
    {
        "int",
        "integer",
        "long",
        "short",
        "byte",
        "nonNegativeInteger",
        "positiveInteger",
        "nonPositiveInteger",
        "negativeInteger",
        "unsignedInt",
        "unsignedLong",
        "unsignedShort",
        "unsignedByte",
    }
)

REST_PREFIX = {
    "jira": "/rest/api/2",
    "confluence": "/rest/api",
    "bitbucket": "/rest/api/1.0",
}
PRODUCTS = tuple(REST_PREFIX)


@dataclass(frozen=True)
class Param:
    """One documented query parameter."""

    name: str
    kind: str  # "integer" or "string"
    default: str | None = None
    raw_type: str = ""

    @property
    def sort_key(self) -> str:
        return self.name


@dataclass
class Method:
    """One documented method on one route."""

    verb: str
    route: str  # readable form, placeholders keep their names
    doc: str = ""
    query: list[Param] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.verb, self.route)


def param_name(raw: str) -> str:
    """Keep the documented placeholder name, without its regex suffix."""
    name = raw.split(":", 1)[0].strip()
    return name or "value"


def readable_route(path: str) -> str:
    """Turn a WADL path into `/a/{x}/b`, keeping placeholder names."""
    collapsed = _SLASHES.sub("/", path or "/").rstrip("/")
    named = _PLACEHOLDER.sub(
        lambda match: "{" + param_name(match.group(1)) + "}", collapsed
    )
    return named or "/"


def normalize(path: str) -> str:
    """Collapse placeholder contents and repeated or trailing slashes."""
    collapsed = _SLASHES.sub("/", _PLACEHOLDER.sub("{}", path)).rstrip("/")
    return collapsed or "/"


def route_variants(path: str) -> set[str]:
    """Return every route one declaration covers, in comparison form."""
    normalized = normalize(path)
    glued = _GLUED.search(normalized)
    if glued is None:
        return {normalized}
    bare = normalized[: glued.start()]
    return {bare, f"{bare}/{{}}"}


def prose(element: ElementTree.Element | None) -> str:
    """Return an element's text with tags stripped and whitespace collapsed."""
    if element is None:
        return ""
    raw = "".join(element.itertext())
    return " ".join(DOC_TAG.sub(" ", raw).split())


def wadl_path(product: str) -> Path:
    return BASE / product / "source" / "application.wadl"


def _query_params(element: ElementTree.Element) -> list[Param]:
    request = element.find(f"{W}request")
    if request is None:
        return []
    params: list[Param] = []
    seen: set[str] = set()
    for node in request.findall(f"{W}param"):
        if node.get("style") != "query":
            continue
        name = node.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        raw_type = (node.get("type") or "").removeprefix("xs:")
        params.append(
            Param(
                name=name,
                kind="integer" if raw_type in INTEGER_TYPES else "string",
                default=node.get("default"),
                raw_type=raw_type,
            )
        )
    return params


def load(product: str) -> tuple[str, list[Method]]:
    """Return the WADL base URL and every documented method of one product.

    Parsed with defusedxml: the document comes off the network, so entity
    expansion and external references must not be honoured.
    """
    root = ElementTree.parse(wadl_path(product)).getroot()
    resources = root.find(f"{W}resources")
    if resources is None:
        raise SystemExit(f"{product}: WADL has no resources element")
    base = resources.get("base", "")
    methods: list[Method] = []

    def walk(node: ElementTree.Element, prefix: str) -> None:
        for resource in node.findall(f"{W}resource"):
            full = readable_route(f"{prefix}/{resource.get('path', '')}")
            for method in resource.findall(f"{W}method"):
                methods.append(
                    Method(
                        verb=method.get("name", "").upper(),
                        route=full,
                        doc=prose(method.find(f"{W}doc")),
                        query=_query_params(method),
                    )
                )
            walk(resource, full)

    walk(resources, "")
    return base, methods


def served_queries(methods: list[Method]) -> dict[tuple[str, str], list[Param]]:
    """Index documented parameters by (verb, comparison route), variants merged."""
    served: dict[tuple[str, str], list[Param]] = {}
    for method in methods:
        for route in route_variants(method.route):
            bucket = served.setdefault((method.verb, route), [])
            known = {item.name for item in bucket}
            bucket.extend(item for item in method.query if item.name not in known)
    return served
