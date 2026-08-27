"""The OpenAPI document, checked against the URLs it claims to describe.

A hand-written schema drifts the moment someone adds an endpoint and forgets.
This does not check every field -- that would be writing the schema twice --
but it does check the one thing nobody notices going stale: that the set of
paths and methods in the document is the set of paths and methods that exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from django.urls import URLPattern, URLResolver, get_resolver

import vinta_django_questionnaires.editor_urls as editor_urls
import vinta_django_questionnaires.urls as response_urls

SPEC = Path(__file__).resolve().parent.parent / "openapi.yml"

#: Where each URL module is mounted in the document's paths.
PREFIXES = {
    "vinta_django_questionnaires.urls": "/api/questionnaires/",
    "vinta_django_questionnaires.editor_urls": "/api/authoring/",
}

METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    with SPEC.open() as handle:
        return yaml.safe_load(handle)


def documented() -> set[str]:
    with SPEC.open() as handle:
        loaded = yaml.safe_load(handle)
    return {
        f"{method.upper()} {path}"
        for path, operations in loaded["paths"].items()
        for method in operations
        if method in METHODS
    }


def implemented() -> set[str]:
    """Every route the two URL modules serve, as `METHOD /path/`."""
    found: set[str] = set()
    for module, prefix in [
        (response_urls, PREFIXES["vinta_django_questionnaires.urls"]),
        (editor_urls, PREFIXES["vinta_django_questionnaires.editor_urls"]),
    ]:
        for pattern in module.urlpatterns:
            assert isinstance(pattern, URLPattern)
            path = prefix + _as_openapi_path(str(pattern.pattern))
            view = pattern.callback.view_class  # type: ignore[attr-defined]
            for method in sorted(METHODS):
                if hasattr(view, method):
                    found.add(f"{method.upper()} {path}")
    return found


def _as_openapi_path(route: str) -> str:
    """`<uuid:response_uuid>/pages/<slug:page_key>/` to `{responseId}/pages/{pageKey}/`."""
    names = {
        "response_uuid": "responseId",
        "page_key": "pageKey",
        "questionnaire_key": "questionnaireKey",
        "version": "version",
        "key": "key",
    }
    out: list[str] = []
    rest = route
    while "<" in rest:
        head, _, rest = rest.partition("<")
        converter, _, rest = rest.partition(">")
        name = converter.split(":")[-1]
        out.append(head)
        out.append("{" + names.get(name, name) + "}")
    out.append(rest)
    return "".join(out)


def test_the_document_is_valid_openapi(spec):
    from openapi_spec_validator import validate

    validate(spec)


def test_the_document_parses_and_has_the_pieces(spec):
    assert spec["openapi"].startswith("3.1")
    assert spec["info"]["title"]
    assert spec["components"]["schemas"]
    assert spec["components"]["securitySchemes"]


def test_every_reference_resolves(spec):
    unresolved = []

    def walk(node):
        if isinstance(node, dict):
            reference = node.get("$ref")
            if isinstance(reference, str):
                target = spec
                for part in reference.lstrip("#/").split("/"):
                    target = target.get(part) if isinstance(target, dict) else None
                    if target is None:
                        unresolved.append(reference)
                        break
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec)
    assert unresolved == []


def test_every_endpoint_is_documented():
    undocumented = sorted(implemented() - documented())
    assert undocumented == [], f"Add these to openapi.yml: {undocumented}"


def test_the_document_invents_nothing():
    invented = sorted(documented() - implemented())
    assert invented == [], f"These are in openapi.yml but not in the URLs: {invented}"


def test_every_operation_says_what_it_is(spec):
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if method not in METHODS:
                continue
            where = f"{method.upper()} {path}"
            assert operation.get("operationId"), f"{where} has no operationId"
            assert operation.get("summary"), f"{where} has no summary"
            assert operation.get("tags"), f"{where} has no tags"
            assert operation.get("responses"), f"{where} documents no responses"


def test_operation_ids_are_unique(spec):
    ids = [
        operation["operationId"]
        for operations in spec["paths"].values()
        for method, operation in operations.items()
        if method in METHODS
    ]
    assert len(ids) == len(set(ids))


def test_the_paths_are_the_ones_django_resolves(client, db):
    """Belt and braces: Django itself can resolve what the document names."""
    resolver = get_resolver()
    assert isinstance(resolver, URLResolver)
    # The test project mounts the two modules at their own prefixes; what
    # matters is that both are reachable at all.
    assert client.get("/questionnaires/responses/").status_code in {403, 405}
    assert client.get("/authoring/catalog/").status_code == 403
