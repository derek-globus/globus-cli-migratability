"""Render a Report into a self-contained HTML artifact."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from .compare import Report

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def render_report_html(report: Report, repo: str = "globus/globus-cli-migratability") -> str:
    env = Environment(
        loader=PackageLoader("globus_migratability", "templates"),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html.jinja")
    return template.render(report=report, repo=repo)


def write_report_html(report: Report, output_path: str | Path, repo: str = "globus/globus-cli-migratability") -> None:
    html = render_report_html(report, repo=repo)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
