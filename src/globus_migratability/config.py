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
