"""Loading and indexing OpenAPI specifications for Globus services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests

from .pathmatch import RouteTemplate, make_route

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@dataclass
class OpenApiOperation:
    method: str
    path: str
    operation_id: str | None
    summary: str
    tags: tuple[str, ...]
    path_params: tuple[str, ...]
    query_params: tuple[str, ...]
    required_params: tuple[str, ...]
    request_body_props: tuple[str, ...]
    required_body_props: tuple[str, ...]
    response_type: str | None  # "array", "object", or None if unknown
    route: RouteTemplate


@dataclass
class OpenApiSpec:
    service: str
    source_url: str
    title: str
    version: str
    operations: list[OpenApiOperation] = field(default_factory=list)

    def by_route_key(self) -> dict[tuple[str, tuple[str, ...]], list[OpenApiOperation]]:
        index: dict[tuple[str, tuple[str, ...]], list[OpenApiOperation]] = {}
        for op in self.operations:
            index.setdefault(op.route.key, []).append(op)
        return index


def fetch_spec_document(url: str, timeout: float = 30.0) -> dict[str, Any]:
    resp = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


def _resolve_ref(document: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        return {}
    node: Any = document
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}


def _schema_props(document: dict[str, Any], schema: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (property_names, required_names) for a (possibly $ref'd) schema."""
    seen_props: list[str] = []
    seen_required: list[str] = []

    def walk(node: dict[str, Any], depth: int = 0) -> None:
        if depth > 5 or not isinstance(node, dict):
            return
        if "$ref" in node:
            walk(_resolve_ref(document, node["$ref"]), depth + 1)
            return
        for combinator in ("allOf", "oneOf", "anyOf"):
            for sub in node.get(combinator, []) or []:
                walk(sub, depth + 1)
        props = node.get("properties") or {}
        for name in props:
            if name not in seen_props:
                seen_props.append(name)
        for name in node.get("required") or []:
            if name not in seen_required:
                seen_required.append(name)

    walk(schema)
    return tuple(seen_props), tuple(seen_required)


def _response_type(document: dict[str, Any], operation: dict[str, Any]) -> str | None:
    responses = operation.get("responses") or {}
    for status in ("200", "201", "202", "default"):
        resp = responses.get(status)
        if not resp:
            continue
        content = resp.get("content") or {}
        for media in content.values():
            schema = media.get("schema") or {}
            if "$ref" in schema:
                schema = _resolve_ref(document, schema["$ref"])
            schema_type = schema.get("type")
            if schema_type:
                return schema_type
            if "properties" in schema:
                return "object"
    return None


def parse_spec(
    service: str,
    source_url: str,
    document: dict[str, Any],
) -> OpenApiSpec:
    info = document.get("info", {}) or {}
    spec = OpenApiSpec(
        service=service,
        source_url=source_url,
        title=info.get("title", service),
        version=str(info.get("version", "unknown")),
    )

    for path, path_item in (document.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        shared_params = path_item.get("parameters") or []
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue

            params = list(shared_params) + list(operation.get("parameters") or [])
            path_params = []
            query_params = []
            required_params = []
            for p in params:
                if "$ref" in p:
                    p = _resolve_ref(document, p["$ref"])
                name = p.get("name")
                if not name:
                    continue
                location = p.get("in")
                if location == "path":
                    path_params.append(name)
                elif location == "query":
                    query_params.append(name)
                if p.get("required"):
                    required_params.append(name)

            body_props: tuple[str, ...] = ()
            required_body_props: tuple[str, ...] = ()
            request_body = operation.get("requestBody")
            if isinstance(request_body, dict):
                if "$ref" in request_body:
                    request_body = _resolve_ref(document, request_body["$ref"])
                content = (request_body or {}).get("content") or {}
                for media in content.values():
                    schema = media.get("schema") or {}
                    body_props, required_body_props = _schema_props(document, schema)
                    if body_props:
                        break

            route = make_route(method, path)

            spec.operations.append(
                OpenApiOperation(
                    method=method.upper(),
                    path=path,
                    operation_id=operation.get("operationId"),
                    summary=operation.get("summary") or operation.get("operationId") or "",
                    tags=tuple(operation.get("tags") or ()),
                    path_params=tuple(path_params),
                    query_params=tuple(query_params),
                    required_params=tuple(required_params),
                    request_body_props=body_props,
                    required_body_props=required_body_props,
                    response_type=_response_type(document, operation),
                    route=route,
                )
            )

    return spec


def load_spec(service: str, url: str) -> OpenApiSpec:
    document = fetch_spec_document(url)
    return parse_spec(service, url, document)
