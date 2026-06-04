"""Reporters package init."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jaguar.core.plugin import ReporterProtocol


def get_all_reporters() -> list[ReporterProtocol]:
    """Return an instance of all built-in reporters."""
    from jaguar.core.plugin import registry
    from jaguar.reporters.console_reporter import ConsoleReporter
    from jaguar.reporters.html_reporter import HtmlReporter
    from jaguar.reporters.json_reporter import JsonReporter
    from jaguar.reporters.markdown_reporter import MarkdownReporter
    reporters: list[ReporterProtocol] = [
        ConsoleReporter(),
        JsonReporter(),
        MarkdownReporter(),
        HtmlReporter(),
    ]
    for reporter in reporters:
        registry.register_reporter(reporter)
    return reporters
