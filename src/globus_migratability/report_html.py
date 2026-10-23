"""Render a Report into a self-contained HTML artifact."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from .compare import Report
from .examples import MethodologyExamples, openapi_blob, sdk_blob, verdict_lines

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _env() -> Environment:
    env = Environment(
        loader=PackageLoader("globus_migratability", "templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["sdk_blob"] = sdk_blob
    env.globals["openapi_blob"] = openapi_blob
    env.globals["verdict_lines"] = verdict_lines
    return env


def render_report_html(report: Report, repo: str = "globus/globus-cli-migratability") -> str:
    template = _env().get_template("report.html.jinja")
    return template.render(report=report, repo=repo, active="report")


def write_report_html(report: Report, output_path: str | Path, repo: str = "globus/globus-cli-migratability") -> None:
    html = render_report_html(report, repo=repo)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)


def render_methodology_html(
    report: Report,
    examples: MethodologyExamples,
    repo: str = "globus/globus-cli-migratability",
) -> str:
    template = _env().get_template("methodology.html.jinja")
    return template.render(report=report, examples=examples, repo=repo, active="methodology")


def write_methodology_html(
    report: Report,
    examples: MethodologyExamples,
    output_path: str | Path,
    repo: str = "globus/globus-cli-migratability",
) -> None:
    html = render_methodology_html(report, examples, repo=repo)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
