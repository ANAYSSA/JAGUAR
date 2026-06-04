"""Analyzers package init."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jaguar.core.plugin import AnalyzerProtocol


def get_all_analyzers() -> list[AnalyzerProtocol]:
    """Return an instance of all built-in analyzers."""
    # Local imports to avoid circular dependencies
    from jaguar.analyzers.accessibility import AccessibilityAnalyzer
    from jaguar.analyzers.ai_design import AIDesignAnalyzer
    from jaguar.analyzers.ai_detect import AIDetectAnalyzer
    from jaguar.analyzers.performance import PerformanceAnalyzer
    from jaguar.analyzers.secrets import SecretsAnalyzer
    from jaguar.analyzers.security import SecurityAnalyzer
    from jaguar.analyzers.seo import SEOAnalyzer
    from jaguar.analyzers.techstack import TechStackAnalyzer
    from jaguar.analyzers.ux import UXAnalyzer
    from jaguar.analyzers.vulnerability import VulnerabilityAnalyzer
    from jaguar.core.plugin import registry
    analyzers: list[AnalyzerProtocol] = [
        SecurityAnalyzer(),
        SecretsAnalyzer(),
        SEOAnalyzer(),
        PerformanceAnalyzer(),
        AccessibilityAnalyzer(),
        TechStackAnalyzer(),
        UXAnalyzer(),
        AIDesignAnalyzer(),
        AIDetectAnalyzer(),
        VulnerabilityAnalyzer(),
    ]
    for analyzer in analyzers:
        registry.register_analyzer(analyzer)
    return analyzers
