"""Configuration loading for the set of services to compare."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    openapi_url: str
    sdk_module: str
    sdk_class: str


UNCATEGORIZED = "Uncategorized"


@dataclass(frozen=True)
class MethodGroups:
    """Hand-curated method->group mapping for a single service."""

    mapping: dict[str, str]
    order: tuple[str, ...]  # group names, in the order they're declared


def load_method_groups(path: str | Path) -> dict[str, MethodGroups]:
    """Load the hand-curated method->group mapping.

    Returns ``{service_name: MethodGroups}``. Missing or unreadable files
    yield an empty mapping, so every method simply falls back to
    :data:`UNCATEGORIZED`.
    """
    p = Path(path)
    if not p.exists():
        return {}

    data = yaml.safe_load(p.read_text()) or {}
    result: dict[str, MethodGroups] = {}
    for service, groups in (data.get("services") or {}).items():
        method_to_group: dict[str, str] = {}
        group_order: list[str] = []
        for group_name, method_names in (groups or {}).items():
            group_order.append(group_name)
            for method_name in method_names or []:
                method_to_group[method_name] = group_name
        result[service] = MethodGroups(mapping=method_to_group, order=tuple(group_order))
    return result


def load_services(path: str | Path) -> list[ServiceConfig]:
    data = yaml.safe_load(Path(path).read_text())
    services = []
    for entry in data["services"]:
        services.append(
            ServiceConfig(
                name=entry["name"],
                openapi_url=entry["openapi_url"],
                sdk_module=entry["sdk_module"],
                sdk_class=entry["sdk_class"],
            )
        )
    return services
