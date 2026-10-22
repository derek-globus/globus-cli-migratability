"""Utilities for normalizing and matching HTTP route templates.

The globus-sdk docstrings describe routes using angle-bracket path
parameters (e.g. ``/v2/groups/<group_id>``) while OpenAPI specs use curly
braces (e.g. ``/v2/groups/{group_id}``). This module normalizes both forms
into a template of literal segments and positional wildcards so that a
route can be matched regardless of parameter naming.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PARAM_RE = re.compile(r"^[<{](?P<name>[^<>{}]+)[>}]$")


@dataclass(frozen=True)
class RouteTemplate:
    method: str
    raw_path: str
    segments: tuple[str, ...]
    param_names: tuple[str, ...]

    @property
    def key(self) -> tuple[str, tuple[str, ...]]:
        """A hashable key usable for exact structural matching."""
        return (self.method, self.segments)


def normalize_path(path: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (segments, param_names) for a path template.

    Literal segments are kept as-is (lowercased); parameter segments are
    replaced with the wildcard marker ``"*"`` and their names collected
    separately.
    """
    param_names: list[str] = []
    segments: list[str] = []
    for part in path.strip("/").split("/"):
        if not part:
            continue
        match = _PARAM_RE.match(part)
        if match:
            param_names.append(match.group("name"))
            segments.append("*")
        else:
            segments.append(part.lower())
    return tuple(segments), tuple(param_names)


def make_route(method: str, path: str) -> RouteTemplate:
    segments, param_names = normalize_path(path)
    return RouteTemplate(
        method=method.upper(),
        raw_path=path,
        segments=segments,
        param_names=param_names,
    )
