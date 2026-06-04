"""
Configuration management for JAGUAR.

Loads configuration from TOML files and environment variables.
Supports user-level config (~/.jaguar/config.toml) and project-level
config (./jaguar.toml).
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("jaguar.config")

DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "timeout": 30,
        "max_retries": 3,
        "user_agent": "Mozilla/5.0 (compatible; JAGUAR/1.0; +https://github.com/anayssa/jaguar)",
        "verify_ssl": True,
        "use_browser": True,
        "output_dir": "./jaguar-reports",
        "log_level": "INFO",
    },
    "scoring": {
        "weights": {
            "security": 1.5,
            "secrets": 1.3,
            "seo": 1.0,
            "performance": 1.2,
            "accessibility": 1.1,
            "techstack": 0.3,
            "ux": 1.0,
            "ai_design": 0.7,
            "ai_detect": 0.4,
            "vulnerability": 1.4,
        }
    },
    "browser": {
        "headless": True,
        "viewport_desktop": {"width": 1920, "height": 1080},
        "viewport_tablet": {"width": 768, "height": 1024},
        "viewport_mobile": {"width": 375, "height": 812},
    },
    "cloner": {
        "max_depth": 5,
        "max_pages": 100,
        "concurrency": 5,
        "download_assets": True,
        "respect_robots": True,
    },
    "storage": {
        "database_path": "~/.jaguar/history.db",
        "max_history": 1000,
    },
}


def get_config_dir() -> Path:
    """Get the JAGUAR configuration directory."""
    config_dir = Path(os.environ.get("JAGUAR_CONFIG_DIR", "~/.jaguar")).expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load JAGUAR configuration.

    Priority (highest to lowest):
    1. Explicit config_path argument
    2. Project-level ./jaguar.toml
    3. User-level ~/.jaguar/config.toml
    4. Default configuration

    Environment variables override file config:
    - JAGUAR_TIMEOUT → general.timeout
    - JAGUAR_LOG_LEVEL → general.log_level
    - JAGUAR_USE_BROWSER → general.use_browser
    """
    import copy

    config = copy.deepcopy(DEFAULT_CONFIG)

    # Try loading from files
    paths_to_try: list[Path] = []

    if config_path:
        paths_to_try.append(Path(config_path))

    paths_to_try.extend(
        [
            Path("./jaguar.toml"),
            get_config_dir() / "config.toml",
        ]
    )

    for path in paths_to_try:
        if path.exists():
            try:
                file_config = _load_toml(path)
                config = _deep_merge(config, file_config)
                logger.info("Loaded config from %s", path)
                break
            except Exception as e:
                logger.warning("Failed to load config from %s: %s", path, e)

    # Apply environment variable overrides
    _apply_env_overrides(config)

    return config


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

    with open(path, "rb") as f:
        return tomllib.load(f)


def _deep_merge(base: dict, override: dict) -> dict:  # type: ignore
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(config: dict[str, Any]) -> None:
    """Apply environment variable overrides to config."""
    env_map = {
        "JAGUAR_TIMEOUT": ("general", "timeout", int),
        "JAGUAR_LOG_LEVEL": ("general", "log_level", str),
        "JAGUAR_USE_BROWSER": (
            "general",
            "use_browser",
            lambda x: x.lower() in ("true", "1", "yes"),
        ),
        "JAGUAR_OUTPUT_DIR": ("general", "output_dir", str),
        "JAGUAR_VERIFY_SSL": ("general", "verify_ssl", lambda x: x.lower() in ("true", "1", "yes")),
    }

    for env_var, (section, key, converter) in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            with contextlib.suppress(ValueError, KeyError):
                config[section][key] = converter(value)  # type: ignore
