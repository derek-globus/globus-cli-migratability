from globus_migratability.openapi_loader import parse_spec

SAMPLE_DOCUMENT = {
    "openapi": "3.0.0",
    "info": {"title": "Sample API", "version": "1.2.3"},
    "paths": {
        "/v2/widgets/{widget_id}": {
            "get": {
                "operationId": "get_widget",
                "summary": "Get a widget",
                "tags": ["Widgets"],
                "parameters": [
                    {"name": "widget_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {"name": "include", "in": "query", "required": False, "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Widget"}
                            }
                        }
                    }
                },
            }
        },
        "/v2/widgets": {
            "get": {
                "operationId": "list_widgets",
                "summary": "List widgets",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"$ref": "#/components/schemas/Widget"}}
                            }
                        }
                    }
                },
            },
            "post": {
                "operationId": "create_widget",
                "summary": "Create a widget",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/WidgetCreate"}
                        }
                    }
                },
                "responses": {"201": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}}}},
            },
        },
    },
    "components": {
        "schemas": {
            "Widget": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
                "required": ["id"],
            },
            "WidgetCreate": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "tags": {"type": "array"}},
                "required": ["name"],
            },
        }
    },
}


def test_parse_spec_basic_counts():
    spec = parse_spec("widgets", "https://example.test/openapi.json", SAMPLE_DOCUMENT)
    assert spec.title == "Sample API"
    assert spec.version == "1.2.3"
    assert len(spec.operations) == 3


def test_parse_spec_path_and_query_params():
    spec = parse_spec("widgets", "https://example.test/openapi.json", SAMPLE_DOCUMENT)
    get_widget = next(op for op in spec.operations if op.operation_id == "get_widget")
    assert get_widget.path_params == ("widget_id",)
    assert get_widget.query_params == ("include",)
    assert get_widget.required_params == ("widget_id",)
    assert get_widget.response_type == "object"


def test_parse_spec_array_response_and_request_body():
    spec = parse_spec("widgets", "https://example.test/openapi.json", SAMPLE_DOCUMENT)
    list_widgets = next(op for op in spec.operations if op.operation_id == "list_widgets")
    assert list_widgets.response_type == "array"

    create_widget = next(op for op in spec.operations if op.operation_id == "create_widget")
    assert set(create_widget.request_body_props) == {"name", "tags"}
    assert create_widget.required_body_props == ("name",)
