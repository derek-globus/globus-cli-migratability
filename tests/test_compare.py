from globus_migratability.compare import compare_service
from globus_migratability.openapi_loader import parse_spec
from globus_migratability.pathmatch import make_route
from globus_migratability.sdk_introspect import SdkClientInfo, SdkMethodInfo

from .test_openapi_loader import SAMPLE_DOCUMENT


def _spec():
    return parse_spec("widgets", "https://example.test/openapi.json", SAMPLE_DOCUMENT)


def _sdk_info(methods):
    return SdkClientInfo(
        service="widgets",
        module="fake",
        class_name="WidgetsClient",
        sdk_version="9.9.9",
        methods=list(methods),
    )


def test_matched_method_with_full_param_coverage_scores_high():
    method = SdkMethodInfo(
        name="get_widget",
        qualname="WidgetsClient.get_widget",
        route=make_route("GET", "/v2/widgets/<widget_id>"),
        raw_route="GET /v2/widgets/<widget_id>",
        operation_id=None,
        explicit_params=("widget_id", "include"),
        required_params=("widget_id",),
        source='def get_widget(self, widget_id, include=None):\n    return self.get(f"/v2/widgets/{widget_id}", query_params={"include": include})\n',
        docstring="``GET /v2/widgets/<widget_id>``",
        return_annotation=None,
    )
    result = compare_service(_sdk_info([method]), _spec())
    matched = [m for m in result.methods if m.status == "matched"]
    assert len(matched) == 1
    assert matched[0].score > 0.8
    assert matched[0].missing_params == ()


def test_missing_required_field_is_flagged_as_error():
    method = SdkMethodInfo(
        name="create_widget",
        qualname="WidgetsClient.create_widget",
        route=make_route("POST", "/v2/widgets"),
        raw_route="POST /v2/widgets",
        operation_id=None,
        explicit_params=(),
        required_params=(),
        source="def create_widget(self, data):\n    return self.post('/v2/widgets', data=data)\n",
        docstring="``POST /v2/widgets``",
        return_annotation=None,
    )
    result = compare_service(_sdk_info([method]), _spec())
    matched = next(m for m in result.methods if m.status == "matched" and m.openapi_op.operation_id == "create_widget")
    kinds = {a.kind for a in matched.aberrations}
    assert "missing_required_field" in kinds


def test_spec_operation_without_sdk_method_is_flagged_missing_from_sdk():
    result = compare_service(_sdk_info([]), _spec())
    missing = [m for m in result.methods if m.status == "spec_only"]
    assert len(missing) == 3
    assert all(a.kind == "missing_from_sdk" for m in missing for a in m.aberrations)
    assert result.coverage_pct == 0.0


def test_sdk_method_with_no_matching_route_is_flagged_sdk_only():
    method = SdkMethodInfo(
        name="get_widget_stats",
        qualname="WidgetsClient.get_widget_stats",
        route=make_route("GET", "/v2/widgets/<widget_id>/stats"),
        raw_route="GET /v2/widgets/<widget_id>/stats",
        operation_id=None,
        explicit_params=("widget_id",),
        required_params=("widget_id",),
        source="def get_widget_stats(self, widget_id):\n    return self.get(f'/v2/widgets/{widget_id}/stats')\n",
        docstring="``GET /v2/widgets/<widget_id>/stats``",
        return_annotation=None,
    )
    result = compare_service(_sdk_info([method]), _spec())
    sdk_only = [m for m in result.methods if m.status == "sdk_only"]
    assert len(sdk_only) == 1
    assert sdk_only[0].aberrations[0].kind == "no_matching_operation"
