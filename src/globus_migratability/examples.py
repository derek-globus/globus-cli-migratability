"""Pick concrete, real worked examples out of a freshly-built Report.

The methodology page shows actual matched/mismatched method pairs pulled
from the current run, rather than hand-written samples that could drift
from how the matcher actually behaves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .compare import MethodComparison, Report
from .openapi_loader import OpenApiOperation
from .sdk_introspect import SdkMethodInfo


@dataclass
class Example:
    service: str
    method: MethodComparison


@dataclass
class MethodologyExamples:
    clean_match: Example | None = None
    missing_required_field: Example | None = None
    sdk_only_param: Example | None = None
    response_shape_mismatch: Example | None = None
    missing_from_sdk: Example | None = None
    no_matching_operation: Example | None = None


def _first(report: Report, predicate) -> Example | None:
    for svc in report.services:
        for m in svc.methods:
            if predicate(m):
                return Example(service=svc.service, method=m)
    return None


def _has_aberration(m: MethodComparison, kind: str) -> bool:
    return any(a.kind == kind for a in m.aberrations)


def sdk_blob(method: SdkMethodInfo | None, limit: int = 420) -> str:
    if method is None:
        return "(no SDK method)"
    text = (method.docstring or "(no docstring)").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "\n..."
    return f"# {method.qualname}\n{text}"


def openapi_blob(op: OpenApiOperation | None) -> str:
    if op is None:
        return "(no OpenAPI operation)"
    payload = {
        "method": op.method,
        "path": op.path,
        "operationId": op.operation_id,
        "pathParams": list(op.path_params),
        "queryParams": list(op.query_params),
        "requiredParams": list(op.required_params),
        "requestBodyProps": list(op.request_body_props),
        "requiredBodyProps": list(op.required_body_props),
        "responseType": op.response_type,
    }
    payload = {k: v for k, v in payload.items() if v not in (None, [], "")}
    return json.dumps(payload, indent=2)


def verdict_lines(method: MethodComparison) -> list[str]:
    lines = [f"status: {method.status}"]
    if method.status == "matched":
        lines.append(f"fidelity score: {method.score * 100:.0f}%")
    lines.extend(a.message for a in method.aberrations)
    return lines


def pick_examples(report: Report) -> MethodologyExamples:
    return MethodologyExamples(
        clean_match=_first(
            report, lambda m: m.status == "matched" and not m.aberrations and m.score >= 0.95
        ),
        missing_required_field=_first(
            report, lambda m: _has_aberration(m, "missing_required_field")
        ),
        sdk_only_param=_first(report, lambda m: _has_aberration(m, "sdk_only_parameter")),
        response_shape_mismatch=_first(
            report, lambda m: _has_aberration(m, "response_shape_mismatch")
        ),
        missing_from_sdk=_first(report, lambda m: m.status == "spec_only"),
        no_matching_operation=_first(
            report, lambda m: _has_aberration(m, "no_matching_operation")
        ),
    )
