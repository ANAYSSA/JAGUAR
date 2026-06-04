"""
Plugin system for JAGUAR.

Supports three plugin types:
- Analyzers: add new analysis capabilities
- Reporters: add new output formats
- Hooks: intercept and extend the scan lifecycle

Plugins are discovered via Python entry_points (setuptools/hatch),
enabling third-party packages to extend JAGUAR without modifying core.

Requirement #9: Plugin Marketplace Architecture — future plugins
should be installable without modifying core.
"""

from __future__ import annotations

import importlib.metadata
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from jaguar.core.models import AnalyzerResult, ScanContext, ScanResult

logger = logging.getLogger("jaguar.plugin")


# ---------------------------------------------------------------------------
# Protocols — the contracts plugins must fulfill
# ---------------------------------------------------------------------------


@runtime_checkable
class AnalyzerProtocol(Protocol):
    """Contract for analyzer plugins."""

    name: str
    category: Any
    weight: float

    async def analyze(self, context: ScanContext) -> AnalyzerResult: ...


@runtime_checkable
class ReporterProtocol(Protocol):
    """Contract for reporter plugins."""

    name: str
    format_name: str

    async def generate(
        self,
        result: ScanResult,
        output_path: str,
        **options: Any,
    ) -> str: ...


@runtime_checkable
class HookProtocol(Protocol):
    """
    Contract for lifecycle hook plugins.

    Hooks can intercept the scan at various points:
    - pre_scan: before any analyzers run
    - post_analyzer: after each analyzer completes
    - post_scan: after all analyzers complete, before reporting
    """

    name: str

    async def pre_scan(self, context: ScanContext) -> ScanContext: ...
    async def post_analyzer(
        self, context: ScanContext, result: AnalyzerResult
    ) -> AnalyzerResult: ...
    async def post_scan(self, result: ScanResult) -> ScanResult: ...


# ---------------------------------------------------------------------------
# Base classes — convenience bases for plugin authors
# ---------------------------------------------------------------------------


class BaseHook(ABC):
    """
    Base class for hook plugins.

    Override only the methods you need; defaults are pass-through.
    """

    @abstractmethod
    def __init__(self) -> None:
        pass

    name: str = "unnamed-hook"

    async def pre_scan(self, context: ScanContext) -> ScanContext:
        return context

    async def post_analyzer(self, context: ScanContext, result: AnalyzerResult) -> AnalyzerResult:
        return result

    async def post_scan(self, result: ScanResult) -> ScanResult:
        return result


# ---------------------------------------------------------------------------
# Plugin Registry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """
    Central registry for all JAGUAR plugins.

    Discovers plugins from:
    1. Built-in analyzers/reporters registered via register()
    2. Third-party packages using entry_points
    """

    def __init__(self) -> None:
        self._analyzers: dict[str, AnalyzerProtocol] = {}
        self._reporters: dict[str, ReporterProtocol] = {}
        self._hooks: list[HookProtocol] = []

    # -- Registration --

    def register_analyzer(self, analyzer: AnalyzerProtocol) -> None:
        """Register an analyzer plugin."""
        if not isinstance(analyzer, AnalyzerProtocol):
            raise TypeError(f"{analyzer} does not implement AnalyzerProtocol")
        self._analyzers[analyzer.name] = analyzer
        logger.debug("Registered analyzer: %s", analyzer.name)

    def register_reporter(self, reporter: ReporterProtocol) -> None:
        """Register a reporter plugin."""
        self._reporters[reporter.name] = reporter
        logger.debug("Registered reporter: %s", reporter.name)

    def register_hook(self, hook: HookProtocol) -> None:
        """Register a lifecycle hook."""
        self._hooks.append(hook)
        logger.debug("Registered hook: %s", hook.name)

    # -- Discovery --

    def discover_entry_points(self) -> None:
        """
        Discover and load plugins from Python entry_points.

        Looks for entry_point groups:
        - jaguar.analyzers
        - jaguar.reporters
        - jaguar.plugins (hooks)
        """
        for group, register_fn in [
            ("jaguar.analyzers", self.register_analyzer),
            ("jaguar.reporters", self.register_reporter),
            ("jaguar.plugins", self.register_hook),
        ]:
            try:
                eps = importlib.metadata.entry_points().select(group=group)
            except AttributeError:
                # Python 3.12+ compatible fallback
                eps = importlib.metadata.entry_points(group=group)

            for ep in eps:
                try:
                    plugin_class = ep.load()
                    plugin_instance = plugin_class()
                    register_fn(plugin_instance)  # type: ignore
                    logger.info(
                        "Loaded plugin '%s' from entry_point '%s'",
                        getattr(plugin_instance, "name", ep.name),
                        ep.name,
                    )
                except Exception as e:
                    logger.warning("Failed to load plugin '%s': %s", ep.name, e)

    # -- Access --

    def get_analyzer(self, name: str) -> AnalyzerProtocol | None:
        """Get an analyzer by name."""
        return self._analyzers.get(name)

    def get_reporter(self, name: str) -> ReporterProtocol | None:
        """Get a reporter by name."""
        return self._reporters.get(name)

    @property
    def analyzers(self) -> dict[str, AnalyzerProtocol]:
        """All registered analyzers."""
        return dict(self._analyzers)

    @property
    def reporters(self) -> dict[str, ReporterProtocol]:
        """All registered reporters."""
        return dict(self._reporters)

    @property
    def hooks(self) -> list[HookProtocol]:
        """All registered hooks."""
        return list(self._hooks)

    def list_plugins(self) -> dict[str, list[str]]:
        """List all registered plugins by type."""
        return {
            "analyzers": list(self._analyzers.keys()),
            "reporters": list(self._reporters.keys()),
            "hooks": [h.name for h in self._hooks],
        }


# Singleton registry
registry = PluginRegistry()
