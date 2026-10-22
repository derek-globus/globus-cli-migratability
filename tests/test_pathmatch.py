from globus_migratability.pathmatch import make_route, normalize_path


def test_normalize_path_angle_brackets():
    segments, params = normalize_path("/v2/groups/<group_id>")
    assert segments == ("v2", "groups", "*")
    assert params == ("group_id",)


def test_normalize_path_curly_braces():
    segments, params = normalize_path("/v2/groups/{group_id}")
    assert segments == ("v2", "groups", "*")
    assert params == ("group_id",)


def test_routes_with_different_param_syntax_match():
    sdk_route = make_route("GET", "/v2/groups/<group_id>")
    spec_route = make_route("get", "/v2/groups/{group_id}")
    assert sdk_route.key == spec_route.key


def test_routes_with_different_literal_segments_do_not_match():
    a = make_route("GET", "/v2/groups/<group_id>")
    b = make_route("GET", "/v2/groups/<group_id>/children")
    assert a.key != b.key
