"""Configuration loading for the project pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ProjectConfig:
    """Resolved project configuration loaded from a YAML file."""

    root: Path
    database_path: Path
    sources: dict[str, dict[str, Any]]
    geocoding: dict[str, Any]

    @classmethod
    def from_yaml(cls, config_path: Path) -> "ProjectConfig":
        """Load and resolve paths in a project configuration file.

        Args:
            config_path: Path to the YAML configuration file.

        Returns:
            A configuration object with paths resolved relative to the project
            root, not the caller's current working directory.
        """
        config_path = config_path.resolve()
        with config_path.open(encoding="utf-8") as file:
            values = yaml.safe_load(file) or {}

        root = config_path.parent / values.get("project_root", "..")
        root = root.resolve()
        database_path = root / values["database"]["path"]
        sources = {
            name: _resolve_source(root, source)
            for name, source in values.get("sources", {}).items()
        }
        return cls(
            root=root,
            database_path=database_path,
            sources=sources,
            geocoding=values.get("geocoding", {}),
        )


def _resolve_source(root: Path, source: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(source)
    if "path" in resolved:
        resolved["path"] = root / resolved["path"]
    return resolved
