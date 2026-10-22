# globus-cli-migratability

Compares each [Globus](https://www.globus.org/) service's published OpenAPI
specification against the corresponding client in
[`globus-sdk`](https://github.com/globus/globus-sdk-python), and publishes a
"migratability" report as a GitHub Pages site.

The report answers two questions per service:

1. **API coverage** — what fraction of the OpenAPI-documented operations
   have a corresponding `globus-sdk` client method at all?
2. **Fidelity / aberrations** — for operations that *are* covered, do the
   SDK method's parameters and response shape line up with what the spec
   declares? Mismatches (missing required fields, parameters the SDK
   doesn't seem to pass through, response-shape mismatches, spec-only or
   SDK-only operations) are listed as concrete aberrations.

## How matching works

Every `globus-sdk` client method's docstring documents the HTTP route it
calls, either as an inline `` `METHOD /path` `` code span, or — for a few
services — as a Sphinx `.. extdoclink::` directive whose `:ref:` encodes the
OpenAPI `operationId` or path. [`sdk_introspect.py`](src/globus_migratability/sdk_introspect.py)
parses both forms. [`compare.py`](src/globus_migratability/compare.py) then
matches each SDK method to the OpenAPI operation with the same HTTP method
and path template (path parameter names may differ, e.g. `<group_id>` vs.
`{group_id}`), or by `operationId` when a path can't be recovered.

For matched pairs, parameter coverage is a **heuristic**: an OpenAPI query
or request-body field counts as "covered" if it's either an explicit
keyword argument on the SDK method, or its name appears as a literal string
in the method's source (covering the common pattern of building a
`query_params={...}` or `data={...}` dict). This is not a type-level diff —
it's meant to surface likely drift for a human to double check, not to be
authoritative.

## Running locally

```bash
pip install -e .
globus-migratability run --config config/services.yaml --output-dir site --repo <owner>/<repo>
```

This writes `site/index.html` (the report) and `site/report.json` (the same
data, machine-readable).

Run the tests with:

```bash
pip install -e ".[dev]"
pytest
```

## Configuring which services are compared

[`config/services.yaml`](config/services.yaml) lists one entry per service:
an OpenAPI spec URL and the `globus-sdk` class that wraps it. Not every
Globus service currently publishes a machine-readable OpenAPI document
(Transfer and Auth do not, as of writing) — add an entry here once a spec
becomes available.

## GitHub Actions workflow

[`.github/workflows/migratability.yml`](.github/workflows/migratability.yml)
regenerates and publishes the report to GitHub Pages:

- **Weekly**, on a fixed schedule, regardless of SDK version — this catches
  drift introduced purely on the OpenAPI/service side.
- **On every new `globus-sdk` release.** GitHub Actions has no native event
  for "a release was published on a different repository/package", so this
  is implemented by polling the PyPI JSON API daily and only
  doing a full run when the latest version differs from the last one seen
  (tracked in the committed `.globus-sdk-version` file). When a new version
  is detected, that exact `globus-sdk` release is installed before running
  the comparison, so the report reflects that release's SDK code.
- **Manually**, via `workflow_dispatch`.

### One-time setup

In the repository settings, under **Pages**, set the source to **GitHub
Actions**. The workflow needs `contents: write` (to commit the version
marker) and `pages: write` / `id-token: write` (to deploy the site), which
are already declared in the workflow file.
