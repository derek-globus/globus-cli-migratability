"""Core migratability comparison logic.

This module matches globus-sdk client methods against operations in a
service's published OpenAPI specification, scores how faithfully each
matched method's parameters and response shape appear to track the spec,
and flags concrete aberrations: operations missing from the SDK, SDK
methods with no corresponding spec entry, and field-level mismatches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import MethodGroups
from .openapi_loader import OpenApiOperation, OpenApiSpec
from .sdk_introspect import SdkClientInfo, SdkMethodInfo

_ARRAY_WRAPPERS = ("ArrayResponse", "IterableResponse", "IterableJSONAPIResponse")
UNCATEGORIZED_GROUP = "Uncategorized"
MISSING_FROM_SDK_GROUP = "Missing from SDK"


@dataclass
class Aberration:
    severity: str  # "error" | "warning" | "info"
    kind: str
    message: str


@dataclass
class MethodComparison:
    sdk_method: SdkMethodInfo | None
    openapi_op: OpenApiOperation | None
    status: str  # "matched" | "sdk_only" | "spec_only" | "no_spec"
    score: float  # 0.0 - 1.0, only meaningful when matched
    param_coverage: float | None
    missing_params: tuple[str, ...]
    extra_sdk_params: tuple[str, ...]
    response_shape_ok: bool | None
    aberrations: list[Aberration] = field(default_factory=list)
    group: str = UNCATEGORIZED_GROUP

    @property
    def label(self) -> str:
        if self.openapi_op is not None:
            return f"{self.openapi_op.method} {self.openapi_op.path}"
        assert self.sdk_method is not None
        return self.sdk_method.raw_route or self.sdk_method.qualname


@dataclass
class ServiceComparison:
    service: str
    sdk_class: str
    spec_title: str
    spec_version: str
    sdk_version: str
    methods: list[MethodComparison] = field(default_factory=list)
    group_order: tuple[str, ...] = ()
    has_spec: bool = True

    @property
    def grouped_methods(self) -> list[tuple[str, list[MethodComparison]]]:
        """Methods bucketed by their documentation group, in display order.

        Curated groups (from config/method_groups.yaml) come first, in the
        order they're declared there; any methods not covered by a curated
        group fall into "Uncategorized"; OpenAPI operations with no SDK
        method at all are bucketed separately, last.
        """
        by_group: dict[str, list[MethodComparison]] = {}
        for m in self.methods:
            by_group.setdefault(m.group, []).append(m)

        ordered_names = [g for g in self.group_order if g in by_group]
        if UNCATEGORIZED_GROUP in by_group and UNCATEGORIZED_GROUP not in ordered_names:
            ordered_names.append(UNCATEGORIZED_GROUP)
        if MISSING_FROM_SDK_GROUP in by_group and MISSING_FROM_SDK_GROUP not in ordered_names:
            ordered_names.append(MISSING_FROM_SDK_GROUP)
        # Anything unexpected (shouldn't normally happen) still shows up.
        for name in by_group:
            if name not in ordered_names:
                ordered_names.append(name)

        return [(name, by_group[name]) for name in ordered_names]

    @property
    def total_operations(self) -> int:
        return sum(1 for m in self.methods if m.openapi_op is not None)

    @property
    def covered_operations(self) -> int:
        return sum(1 for m in self.methods if m.status == "matched")

    @property
    def coverage_pct(self) -> float:
        if self.total_operations == 0:
            return 0.0
        return 100.0 * self.covered_operations / self.total_operations

    @property
    def avg_fidelity_pct(self) -> float:
        matched = [m for m in self.methods if m.status == "matched"]
        if not matched:
            return 0.0
        return 100.0 * sum(m.score for m in matched) / len(matched)

    @property
    def aberration_count(self) -> int:
        return sum(len(m.aberrations) for m in self.methods)


@dataclass
class Report:
    generated_at: str
    sdk_version: str
    services: list[ServiceComparison] = field(default_factory=list)


def _referenced_in_source(source: str, field_name: str) -> bool:
    if not source:
        return False
    pattern = r"[\"']" + re.escape(field_name) + r"[\"']"
    return re.search(pattern, source) is not None


def _response_wrapper_name(source: str) -> str | None:
    match = re.search(r"\breturn\s+(?:self\.)?([A-Za-z_][A-Za-z0-9_]*Response)\(", source)
    if match:
        return match.group(1)
    match = re.search(r"\breturn\s+response\.([A-Za-z_][A-Za-z0-9_]*)\(", source)
    if match:
        return match.group(1)
    return None


def _check_response_shape(sdk_method: SdkMethodInfo, openapi_op: OpenApiOperation) -> bool | None:
    if openapi_op.response_type is None:
        return None
    wrapper = _response_wrapper_name(sdk_method.source)
    is_array_wrapper = wrapper in _ARRAY_WRAPPERS if wrapper else None
    if is_array_wrapper is None:
        return None
    expected_array = openapi_op.response_type == "array"
    return is_array_wrapper == expected_array


def _compare_params(sdk_method: SdkMethodInfo, openapi_op: OpenApiOperation) -> MethodComparison:
    aberrations: list[Aberration] = []

    spec_query_and_body = tuple(openapi_op.query_params) + tuple(openapi_op.request_body_props)
    covered = []
    missing = []
    for name in spec_query_and_body:
        if name in sdk_method.explicit_params or _referenced_in_source(sdk_method.source, name):
            covered.append(name)
        else:
            missing.append(name)

    param_coverage = 1.0 if not spec_query_and_body else len(covered) / len(spec_query_and_body)

    required_missing = [
        name
        for name in (tuple(openapi_op.required_params) + tuple(openapi_op.required_body_props))
        if name in missing
    ]
    if required_missing:
        aberrations.append(
            Aberration(
                severity="error",
                kind="missing_required_field",
                message=(
                    f"OpenAPI marks {', '.join(sorted(required_missing))} as required "
                    "but the SDK method does not appear to reference them."
                ),
            )
        )
    elif missing:
        aberrations.append(
            Aberration(
                severity="warning",
                kind="missing_optional_field",
                message=(
                    f"OpenAPI defines optional field(s) {', '.join(sorted(missing))} "
                    "not referenced in the SDK method."
                ),
            )
        )

    spec_field_names = set(spec_query_and_body) | set(openapi_op.path_params)
    extra_sdk_params = tuple(
        p for p in sdk_method.explicit_params if p not in spec_field_names
    )
    if extra_sdk_params:
        aberrations.append(
            Aberration(
                severity="info",
                kind="sdk_only_parameter",
                message=(
                    f"SDK exposes parameter(s) {', '.join(extra_sdk_params)} with no "
                    "obviously corresponding OpenAPI field (may be client-side sugar)."
                ),
            )
        )

    response_shape_ok = _check_response_shape(sdk_method, openapi_op)
    if response_shape_ok is False:
        aberrations.append(
            Aberration(
                severity="warning",
                kind="response_shape_mismatch",
                message=(
                    f"OpenAPI response type is '{openapi_op.response_type}' but the SDK "
                    "method's response wrapper does not match that shape."
                ),
            )
        )

    score = 0.5 + 0.35 * param_coverage
    score += 0.15 if response_shape_ok else (0.0 if response_shape_ok is False else 0.075)
    score = min(score, 1.0)

    return MethodComparison(
        sdk_method=sdk_method,
        openapi_op=openapi_op,
        status="matched",
        score=score,
        param_coverage=param_coverage,
        missing_params=tuple(missing),
        extra_sdk_params=extra_sdk_params,
        response_shape_ok=response_shape_ok,
        aberrations=aberrations,
    )


def compare_service(
    sdk_class_info: SdkClientInfo,
    spec: OpenApiSpec,
    method_groups: MethodGroups | None = None,
) -> ServiceComparison:
    spec_index: dict[tuple, list[OpenApiOperation]] = spec.by_route_key()
    by_operation_id: dict[str, OpenApiOperation] = {
        op.operation_id: op for op in spec.operations if op.operation_id
    }
    consumed_ops: set[int] = set()

    result = ServiceComparison(
        service=spec.service,
        sdk_class=sdk_class_info.class_name,
        spec_title=spec.title,
        spec_version=spec.version,
        sdk_version=sdk_class_info.sdk_version,
        group_order=method_groups.order if method_groups else (),
    )

    for method in sdk_class_info.methods:
        if method.route is None:
            op_by_id = by_operation_id.get(method.operation_id) if method.operation_id else None
            if op_by_id is not None and id(op_by_id) not in consumed_ops:
                consumed_ops.add(id(op_by_id))
                result.methods.append(_compare_params(method, op_by_id))
                continue

            result.methods.append(
                MethodComparison(
                    sdk_method=method,
                    openapi_op=None,
                    status="sdk_only",
                    score=0.0,
                    param_coverage=None,
                    missing_params=(),
                    extra_sdk_params=(),
                    response_shape_ok=None,
                    aberrations=[
                        Aberration(
                            severity="info",
                            kind="undocumented_route",
                            message=(
                                "SDK method has no parseable 'METHOD /path' route in its "
                                "docstring, and its operationId reference (if any) did not "
                                "match an operation in the current spec."
                            ),
                        )
                    ],
                )
            )
            continue

        candidates = spec_index.get(method.route.key, [])
        candidates = [c for c in candidates if id(c) not in consumed_ops]
        if not candidates:
            result.methods.append(
                MethodComparison(
                    sdk_method=method,
                    openapi_op=None,
                    status="sdk_only",
                    score=0.0,
                    param_coverage=None,
                    missing_params=(),
                    extra_sdk_params=(),
                    response_shape_ok=None,
                    aberrations=[
                        Aberration(
                            severity="warning",
                            kind="no_matching_operation",
                            message=(
                                f"SDK declares route '{method.raw_route}' but no matching "
                                "operation was found in the current OpenAPI spec."
                            ),
                        )
                    ],
                )
            )
            continue

        openapi_op = candidates[0]
        consumed_ops.add(id(openapi_op))
        result.methods.append(_compare_params(method, openapi_op))

    for op in spec.operations:
        if id(op) in consumed_ops:
            continue
        result.methods.append(
            MethodComparison(
                sdk_method=None,
                openapi_op=op,
                status="spec_only",
                score=0.0,
                param_coverage=None,
                missing_params=(),
                extra_sdk_params=(),
                response_shape_ok=None,
                aberrations=[
                    Aberration(
                        severity="error",
                        kind="missing_from_sdk",
                        message=(
                            f"OpenAPI defines '{op.method} {op.path}' "
                            f"({op.summary or op.operation_id}) with no corresponding "
                            "SDK method."
                        ),
                    )
                ],
            )
        )

    mapping = method_groups.mapping if method_groups else {}
    for m in result.methods:
        if m.sdk_method is not None:
            m.group = mapping.get(m.sdk_method.name, UNCATEGORIZED_GROUP)
        else:
            m.group = MISSING_FROM_SDK_GROUP

    result.methods.sort(key=lambda m: (m.status != "matched", m.label))
    return result


def service_without_spec(
    sdk_class_info: SdkClientInfo,
    method_groups: MethodGroups | None = None,
) -> ServiceComparison:
    """Build a ServiceComparison for a service with no fetchable OpenAPI spec.

    Nothing can be compared, so every SDK method is listed, unscored, under
    status "no_spec" -- this keeps the service visible in the report (at 0%
    coverage) for completeness, rather than omitting it silently.
    """
    mapping = method_groups.mapping if method_groups else {}
    result = ServiceComparison(
        service=sdk_class_info.service,
        sdk_class=sdk_class_info.class_name,
        spec_title="(no OpenAPI spec published)",
        spec_version="n/a",
        sdk_version=sdk_class_info.sdk_version,
        group_order=method_groups.order if method_groups else (),
        has_spec=False,
    )
    for method in sdk_class_info.methods:
        result.methods.append(
            MethodComparison(
                sdk_method=method,
                openapi_op=None,
                status="no_spec",
                score=0.0,
                param_coverage=None,
                missing_params=(),
                extra_sdk_params=(),
                response_shape_ok=None,
                aberrations=[],
                group=mapping.get(method.name, UNCATEGORIZED_GROUP),
            )
        )
    result.methods.sort(key=lambda m: m.label)
    return result
