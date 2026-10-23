from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path

from .compare import Report, compare_service
from .config import load_method_groups, load_services
from .examples import pick_examples
from .openapi_loader import load_spec
from .pypi import latest_version
from .report_html import write_methodology_html, write_report_html
from .sdk_introspect import introspect_client


def _build_report(config_path: str, method_groups_path: str) -> Report:
    import globus_sdk

    services = load_services(config_path)
    method_groups = load_method_groups(method_groups_path)
    report = Report(
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        sdk_version=getattr(globus_sdk, "__version__", "unknown"),
    )
    for svc in services:
        print(f"Comparing service: {svc.name} ...", file=sys.stderr)
        spec = load_spec(svc.name, svc.openapi_url)
        sdk_info = introspect_client(svc.sdk_module, svc.sdk_class, svc.name)
        report.services.append(
            compare_service(sdk_info, spec, method_groups.get(svc.name))
        )
    return report


def _report_to_json(report: Report) -> dict:
    def convert(obj):
        if dataclasses.is_dataclass(obj):
            return {k: convert(v) for k, v in dataclasses.asdict(obj).items()}
        if isinstance(obj, (list, tuple)):
            return [convert(v) for v in obj]
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        return obj

    return convert(report)


def cmd_run(args: argparse.Namespace) -> int:
    report = _build_report(args.config, args.method_groups)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    write_report_html(report, out_dir / "index.html", repo=args.repo)
    examples = pick_examples(report)
    write_methodology_html(report, examples, out_dir / "methodology.html", repo=args.repo)
    (out_dir / "report.json").write_text(json.dumps(_report_to_json(report), indent=2))

    print(
        f"Wrote {out_dir / 'index.html'}, {out_dir / 'methodology.html'}, "
        f"and {out_dir / 'report.json'}",
        file=sys.stderr,
    )

    for svc in report.services:
        print(
            f"  {svc.service}: coverage={svc.coverage_pct:.0f}% "
            f"fidelity={svc.avg_fidelity_pct:.0f}% aberrations={svc.aberration_count}",
            file=sys.stderr,
        )
    return 0


def cmd_check_version(args: argparse.Namespace) -> int:
    version_file = Path(args.version_file)
    current = latest_version()
    previous = version_file.read_text().strip() if version_file.exists() else None

    changed = previous != current
    if args.write_on_change and changed:
        version_file.parent.mkdir(parents=True, exist_ok=True)
        version_file.write_text(current + "\n")

    result = {"previous": previous, "current": current, "changed": changed}
    print(json.dumps(result))

    if args.github_output:
        with open(args.github_output, "a") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")
            fh.write(f"version={current}\n")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="globus-migratability")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Compare SDK clients against OpenAPI specs and render a report")
    run_p.add_argument("--config", default="config/services.yaml")
    run_p.add_argument("--method-groups", default="config/method_groups.yaml")
    run_p.add_argument("--output-dir", default="site")
    run_p.add_argument("--repo", default="globus/globus-cli-migratability")
    run_p.set_defaults(func=cmd_run)

    ver_p = sub.add_parser("check-version", help="Check PyPI for a new globus-sdk release")
    ver_p.add_argument("--version-file", default=".globus-sdk-version")
    ver_p.add_argument("--write-on-change", action="store_true")
    ver_p.add_argument("--github-output", default=None)
    ver_p.set_defaults(func=cmd_check_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
