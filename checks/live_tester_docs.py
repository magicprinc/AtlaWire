"""Compare what the registry advertises with what the downloaded WADL documents.

This is the documentation check the owner asked for: the registry, the file the
CLI reads, must agree with the deployment's own API description. Every
disagreement is a defect, in either direction.
"""

from __future__ import annotations

import json
import pathlib
import sys

from defusedxml import ElementTree

sys.path.insert(0, str(pathlib.Path(r"D:\REPO\github\AtlaWire\src")))
from atlawire.operations import list_operations

WADL = {
    "bitbucket": pathlib.Path(
        r"D:\REPO\github\AtlaWire\.development\bitbucket\source\application.wadl"
    ),
    "confluence": pathlib.Path(
        r"D:\REPO\github\AtlaWire\.development\confluence\source\application.wadl"
    ),
    "jira": pathlib.Path(
        r"D:\REPO\github\AtlaWire\.development\jira\source\application.wadl"
    ),
}


def wadl_routes(path: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    """Return {route: {param: [style]}} from one WADL.

    A WADL nests resources: ``<resources base>`` holds top-level ``<resource>``
    elements, and a child ``<resource path>`` is relative to its parent. The full
    route is therefore the base plus every ancestor path, which is why a naive
    "last resource path" reader matches nothing.
    """
    tree = ElementTree.parse(path)
    root = tree.getroot()
    routes: dict[str, dict[str, list[str]]] = {}

    def walk(element: ElementTree.Element, prefix: str) -> None:
        for child in element:
            if not child.tag.endswith("resource"):
                if child.tag.endswith("param"):
                    continue
                walk(child, prefix)
                continue
            segment = child.get("path") or ""
            # A WADL path may or may not start with '/'. Joining naively would
            # produce '.../rest/api/content{id}' for a child named '{id}'.
            if prefix.endswith("/") and segment.startswith("/"):
                route = f"{prefix}{segment[1:]}"
            elif prefix.endswith("/") or segment.startswith("/"):
                route = f"{prefix}{segment}"
            else:
                route = f"{prefix}/{segment}"
            route = route.replace("//", "/")
            params: dict[str, list[str]] = {}
            for method in child:
                if not method.tag.endswith("method"):
                    continue
                # Only a GET is a read. A PUT, POST, or DELETE on the same
                # resource documents the parameters of a write (name, password,
                # permission), and mixing them in would report write-only
                # parameters as missing from a read registry.
                if (method.get("name") or "").upper() != "GET":
                    continue
                for request in method:
                    if not request.tag.endswith("request"):
                        continue
                    for parameter in request:
                        if not parameter.tag.endswith("param"):
                            continue
                        name = parameter.get("name")
                        if not name:
                            continue
                        params.setdefault(name, []).append(
                            parameter.get("style") or "query"
                        )
                # Some deployments declare a parameter directly on <method>
                # rather than inside <request>; both are documented.
                for parameter in method:
                    if not parameter.tag.endswith("param"):
                        continue
                    name = parameter.get("name")
                    if not name:
                        continue
                    params.setdefault(name, []).append(
                        parameter.get("style") or "query"
                    )
            if params:
                routes.setdefault(route, {}).update(params)
            else:
                # A route with no parameters is still documented. Keeping only
                # parameterised routes made every parameter-free operation look
                # undocumented.
                routes.setdefault(route, {})
            walk(child, f"{route}/")

    for resources in root:
        if not resources.tag.endswith("resources"):
            continue
        base = resources.get("base") or ""
        marker = "/rest/"
        index = base.find(marker)
        prefix = base[index:] if index >= 0 else "/"
        if not prefix.endswith("/"):
            prefix += "/"
        walk(resources, prefix)

    return routes


def normalise(path: str) -> str:
    """Turn a registry path into a WADL-comparable route."""
    cleaned = path
    for token in ("{path:.*}", "{.*}", "{path}"):
        cleaned = cleaned.replace(token, "")
    return cleaned.rstrip("/")


def main() -> int:
    operations = list_operations()
    by_product: dict[str, list[dict]] = {}
    for operation in operations:
        by_product.setdefault(operation["product"], []).append(operation)

    problems: list[dict[str, str]] = []

    for product, entries in by_product.items():
        wadl_path = WADL.get(product)
        if not wadl_path or not wadl_path.is_file():
            problems.append(
                {"product": product, "kind": "no-wadl", "detail": str(wadl_path)}
            )
            continue
        routes = wadl_routes(wadl_path)
        flat = {normalise(route): params for route, params in routes.items()}

        for operation in entries:
            route = normalise(operation["path"])
            documented = flat.get(route)
            if documented is None:
                # A route may still be documented with a template the registry
                # spells differently; compare by suffix before reporting.
                matches = [key for key in flat if key.endswith(route)]
                documented = flat[matches[0]] if len(matches) == 1 else None
            if documented is None:
                problems.append(
                    {
                        "product": product,
                        "kind": "route-not-in-wadl",
                        "id": operation["id"],
                        "detail": route,
                    }
                )
                continue

            # A POST operation carries its input in the body while the WADL
            # describes the GET form of the same route. Comparing either
            # direction reports every field as a mismatch, so a POST is compared
            # on its path only.
            if (operation.get("method") or "GET").upper() != "GET":
                continue

            declared = {field["name"] for field in operation.get("query") or []}
            path_names = {
                argument["name"] for argument in operation.get("arguments") or []
            }
            wadl_query = {
                name
                for name, where in documented.items()
                if "query" in where and name not in path_names
            }
            for name in sorted(wadl_query - declared):
                problems.append(
                    {
                        "product": product,
                        "kind": "parameter-missing-from-registry",
                        "id": operation["id"],
                        "detail": name,
                    }
                )
            # A declared parameter the deployment does not document is also a
            # defect: the registry would accept an argument the server ignores.
            for name in sorted(declared - wadl_query):
                problems.append(
                    {
                        "product": product,
                        "kind": "parameter-not-in-wadl",
                        "id": operation["id"],
                        "detail": name,
                    }
                )

    summary: dict[str, int] = {}
    for problem in problems:
        summary[problem["kind"]] = summary.get(problem["kind"], 0) + 1

    document = {
        "operations": len(operations),
        "summary": summary,
        "problems": problems,
    }
    out = pathlib.Path("checks/live_tester_docs.json")
    out.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print("operations:", len(operations))
    print("problems:", summary)
    for problem in problems[:40]:
        print(
            f"  {problem['kind']:32} {problem['product']:11} "
            f"{problem.get('id', ''):60} {problem['detail']}"
        )
    print("written:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
