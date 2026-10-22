"""Reflection over globus-sdk client classes.

For each public method defined directly on a service client class, this
module extracts:

* the declared ``METHOD /path`` route from the docstring (all globus-sdk
  client docstrings include this inside an ``API Info`` tab, as a single
  double-backtick code span), and
* the python call signature, used later to approximate parameter coverage
  against the OpenAPI definition for the same route.
"""

from __future__ import annotations

import importlib
import inspect
import re
from dataclasses import dataclass, field

from .pathmatch import RouteTemplate, make_route

_ROUTE_RE = re.compile(r"``(?P<method>GET|POST|PUT|PATCH|DELETE)\s+(?P<path>\S+)``")

# Fallback for client docstrings (flows, compute) that only include a Sphinx
# ``.. extdoclink::`` directive rather than an inline ``METHOD /path`` code
# span. The directive's ``:ref:`` value encodes either:
#   - a bare OpenAPI operationId (e.g. groups: "get_my_groups_..._get"), or
#   - "<Tag>/operation/<operationId>" (compute), or
#   - "<Tag>/paths/<json-pointer-escaped-path>/<method>" (flows).
_EXTDOCLINK_RE = re.compile(r"\.\.\s*extdoclink::.*?:ref:\s*(?P<ref>\S+)", re.DOTALL)
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# Parameter names that are generic passthrough containers rather than
# API fields in their own right; they shouldn't be flagged as SDK-only
# extras, and their *contents* are checked instead via source-text search.
_PASSTHROUGH_PARAM_NAMES = {
    "query_params",
    "data",
    "body",
    "headers",
    "kwargs",
    "self",
    "add_scope_requirement",
}


@dataclass
class SdkMethodInfo:
    name: str
    qualname: str
    route: RouteTemplate | None
    raw_route: str | None
    operation_id: str | None
    explicit_params: tuple[str, ...]
    required_params: tuple[str, ...]
    source: str
    docstring: str
    return_annotation: str | None


@dataclass
class SdkClientInfo:
    service: str
    module: str
    class_name: str
    sdk_version: str
    methods: list[SdkMethodInfo] = field(default_factory=list)


def _decode_json_pointer(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def _extract_route(
    docstring: str,
) -> tuple[RouteTemplate | None, str | None, str | None]:
    """Return (route, raw_route_display, operation_id)."""
    if not docstring:
        return None, None, None

    match = _ROUTE_RE.search(docstring)
    if match:
        method, path = match.group("method"), match.group("path")
        return make_route(method, path), f"{method} {path}", None

    ext_match = _EXTDOCLINK_RE.search(docstring)
    if not ext_match:
        return None, None, None
    ref = ext_match.group("ref")

    if "/paths/" in ref:
        _, _, remainder = ref.partition("/paths/")
        if "/" in remainder:
            escaped_path, _, method = remainder.rpartition("/")
            if method.lower() in _HTTP_METHODS:
                path = "/" + _decode_json_pointer(escaped_path)
                return make_route(method, path), f"{method.upper()} {path}", None
        return None, None, None

    if "/operation/" in ref:
        operation_id = ref.rpartition("/operation/")[2]
        return None, None, operation_id or None

    # Bare operationId (no slashes), as used by the groups service.
    if "/" not in ref:
        return None, None, ref

    return None, None, None


def _signature_params(func) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return (), ()
    explicit: list[str] = []
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if pname in _PASSTHROUGH_PARAM_NAMES:
            continue
        explicit.append(pname)
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    return tuple(explicit), tuple(required)


def _return_annotation(func) -> str | None:
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return None
    if sig.return_annotation is inspect.Signature.empty:
        return None
    ann = sig.return_annotation
    return ann if isinstance(ann, str) else getattr(ann, "__name__", str(ann))


def introspect_client(module_path: str, class_name: str, service: str) -> SdkClientInfo:
    import globus_sdk

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    sdk_version = getattr(globus_sdk, "__version__", "unknown")

    info = SdkClientInfo(
        service=service,
        module=module_path,
        class_name=class_name,
        sdk_version=sdk_version,
    )

    for name, member in sorted(vars(cls).items()):
        if name.startswith("_"):
            continue
        if not inspect.isfunction(member):
            continue
        # Only methods defined directly on this class (not inherited) are
        # considered part of the service's own surface area.
        docstring = inspect.getdoc(member) or ""
        route, raw_route, operation_id = _extract_route(docstring)
        explicit_params, required_params = _signature_params(member)
        try:
            source = inspect.getsource(member)
        except (OSError, TypeError):
            source = ""

        info.methods.append(
            SdkMethodInfo(
                name=name,
                qualname=f"{class_name}.{name}",
                route=route,
                raw_route=raw_route,
                operation_id=operation_id,
                explicit_params=explicit_params,
                required_params=required_params,
                source=source,
                docstring=docstring,
                return_annotation=_return_annotation(member),
            )
        )

    return info
