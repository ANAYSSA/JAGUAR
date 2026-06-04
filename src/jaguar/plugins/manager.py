"""
Plugin manager for JAGUAR.

Requirement #9: Plugin Marketplace Architecture.

Handles plugin discovery, installation status checking, and provides
the interface for listing and managing plugins. Plugins are installed
as Python packages with entry_points — no core modification needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from jaguar.core.models import PluginInfo
from jaguar.core.plugin import registry

logger = logging.getLogger("jaguar.plugins")


@dataclass
class PluginManager:
    """
    Manages the plugin lifecycle for JAGUAR.

    Responsible for:
    - Discovering installed plugins
    - Loading/unloading plugins
    - Listing available and installed plugins
    - Validating plugin compatibility
    """

    _loaded: dict[str, PluginInfo] = field(default_factory=dict)

    def initialize(self) -> None:
        """
        Initialize the plugin system.

        Called once at startup to discover and load all plugins.
        """
        logger.info("Initializing plugin system")

        # Load built-in analyzers
        self._register_builtin_analyzers()

        # Load built-in reporters
        self._register_builtin_reporters()

        # Discover third-party plugins via entry_points
        registry.discover_entry_points()

        logger.info("Plugin system initialized: %s", registry.list_plugins())

    def _register_builtin_analyzers(self) -> None:
        """Register all built-in analyzers."""
        from jaguar.analyzers import get_all_analyzers

        for analyzer in get_all_analyzers():
            registry.register_analyzer(analyzer)
            self._loaded[analyzer.name] = PluginInfo(
                name=analyzer.name,
                version="1.0.0",
                description=f"Built-in {analyzer.name} analyzer",
                author="anayssa",
                plugin_type="analyzer",
                entry_point=f"jaguar.analyzers.{analyzer.name}",
            )

    def _register_builtin_reporters(self) -> None:
        """Register all built-in reporters."""
        from jaguar.reporters import get_all_reporters

        for reporter in get_all_reporters():
            registry.register_reporter(reporter)
            self._loaded[reporter.name] = PluginInfo(
                name=reporter.name,
                version="1.0.0",
                description=f"Built-in {reporter.name} reporter",
                author="anayssa",
                plugin_type="reporter",
                entry_point=f"jaguar.reporters.{reporter.name}",
            )

    def list_installed(self) -> list[PluginInfo]:
        """List all installed plugins."""
        return list(self._loaded.values())

    def get_plugin(self, name: str) -> PluginInfo | None:
        """Get plugin info by name."""
        return self._loaded.get(name)

    def is_installed(self, name: str) -> bool:
        """Check if a plugin is installed."""
        return name in self._loaded
