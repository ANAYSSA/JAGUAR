"""
Pydantic v2 data models for the JAGUAR intelligence platform.

Every piece of data flowing through JAGUAR is represented by these models.
They enforce type safety, provide serialization, and form the contract
between analyzers, the engine, reporters, storage, and the comparison system.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Severity(StrEnum):
    """Finding severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Grade(StrEnum):
    """Letter grades for scores."""

    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    B_PLUS = "B+"
    B = "B"
    B_MINUS = "B-"
    C_PLUS = "C+"
    C = "C"
    C_MINUS = "C-"
    D_PLUS = "D+"
    D = "D"
    D_MINUS = "D-"
    F = "F"


class Priority(StrEnum):
    """Recommendation priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnalyzerCategory(StrEnum):
    """Categories of analyzers."""

    SECURITY = "security"
    SECRETS = "secrets"
    SEO = "seo"
    PERFORMANCE = "performance"
    ACCESSIBILITY = "accessibility"
    TECHSTACK = "techstack"
    UX = "ux"
    AI_DESIGN = "ai_design"
    AI_DETECT = "ai_detect"
    VULNERABILITY = "vulnerability"


class ReportFormat(StrEnum):
    """Supported report export formats."""

    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"


class ViewportType(StrEnum):
    """Viewport types for screenshots."""

    DESKTOP = "desktop"
    TABLET = "tablet"
    MOBILE = "mobile"


# ---------------------------------------------------------------------------
# Core Data Models
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    """
    A single check result from an analyzer.

    Represents one discrete test or observation, such as
    'HSTS header present with max-age >= 6 months'.
    """

    name: str = Field(description="Machine-readable identifier, e.g. 'hsts-implemented'")
    title: str = Field(description="Human-readable title")
    description: str = Field(default="", description="Detailed explanation")
    passed: bool = Field(description="Whether this check passed")
    severity: Severity = Field(default=Severity.INFO)
    score_modifier: int = Field(
        default=0, description="Points added/subtracted from the analyzer's base score of 100"
    )
    data: dict[str, Any] = Field(default_factory=dict, description="Raw data backing this finding")
    recommendation: str = Field(default="", description="Actionable fix suggestion")


class ScoreExplanation(BaseModel):
    """
    Explains why a score was given — required for every scored result.

    Requirement #7: Every score must explain why it was given,
    what reduced it, and what could increase it.
    """

    score: int = Field(ge=0, le=100)
    grade: Grade
    summary: str = Field(description="One-line reason for this score")
    penalties: list[str] = Field(default_factory=list, description="Factors that reduced the score")
    bonuses: list[str] = Field(default_factory=list, description="Factors that increased the score")
    improvements: list[str] = Field(
        default_factory=list, description="Actions that would raise the score"
    )


class Recommendation(BaseModel):
    """
    AI-generated recommendation from the Recommendations Engine.

    Requirement #2: After every scan, generate what is wrong, why,
    how to fix it, priority, and estimated impact.
    """

    what: str = Field(description="What is wrong")
    why: str = Field(description="Why it is wrong")
    how: str = Field(description="How to fix it")
    priority: Priority
    estimated_impact: str = Field(
        description="Estimated impact of fixing this issue, e.g. '+15 points'"
    )
    category: AnalyzerCategory
    related_findings: list[str] = Field(
        default_factory=list, description="Finding names this recommendation addresses"
    )


class AnalyzerResult(BaseModel):
    """Output from a single analyzer module."""

    analyzer_name: str
    category: AnalyzerCategory
    findings: list[Finding] = Field(default_factory=list)
    score_explanation: ScoreExplanation
    recommendations: list[Recommendation] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(
        default_factory=dict, description="Analyzer-specific raw data for reporters"
    )
    duration_ms: float = Field(
        default=0.0, description="Time taken by this analyzer in milliseconds"
    )

    @computed_field  # type: ignore
    @property
    def score(self) -> int:
        return self.score_explanation.score

    @computed_field  # type: ignore
    @property
    def grade(self) -> Grade:
        return self.score_explanation.grade


class Screenshot(BaseModel):
    """A captured screenshot."""

    viewport: ViewportType
    width: int
    height: int
    path: str = Field(description="Absolute path to the saved image file")
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TechDetection(BaseModel):
    """A single technology detection result."""

    name: str
    category: str = Field(description="e.g. 'framework', 'cms', 'cdn', 'css', 'analytics'")
    version: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence 0.0-1.0")
    evidence: list[str] = Field(
        default_factory=list, description="Evidence strings that triggered detection"
    )


class AIDetectionResult(BaseModel):
    """
    AI-generated content detection probabilities.

    Requirement #4: Detect specific AI tools and patterns.
    """

    design_ai_probability: float = Field(
        ge=0.0, le=100.0, description="Probability that design is AI-generated (%)"
    )
    code_ai_probability: float = Field(
        ge=0.0, le=100.0, description="Probability that frontend code is AI-generated (%)"
    )
    text_ai_probability: float = Field(
        ge=0.0, le=100.0, description="Probability that text content is AI-generated (%)"
    )
    detected_tools: list[str] = Field(
        default_factory=list,
        description="Specific AI tools detected: Lovable, Bolt, v0, Cursor, etc.",
    )
    tool_confidences: dict[str, float] = Field(
        default_factory=dict, description="Confidence per detected tool"
    )
    evidence: dict[str, list[str]] = Field(
        default_factory=dict, description="Evidence grouped by detection category"
    )


# ---------------------------------------------------------------------------
# Scan Result (top-level output)
# ---------------------------------------------------------------------------


class ScanResult(BaseModel):
    """
    Complete output of a JAGUAR scan.

    This is the primary data structure that flows to reporters,
    storage, and the comparison engine.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    url: str
    hostname: str
    scan_started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scan_completed_at: datetime | None = None
    duration_ms: float = 0.0
    analyzer_results: dict[str, AnalyzerResult] = Field(default_factory=dict)
    overall_score: ScoreExplanation | None = None
    screenshots: list[Screenshot] = Field(default_factory=list)
    tech_stack: list[TechDetection] = Field(default_factory=list)
    ai_detection: AIDetectionResult | None = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    executive_summary: str = ""
    errors: list[str] = Field(default_factory=list)
    jaguar_version: str = "1.0.0"

    def get_analyzer_score(self, category: AnalyzerCategory) -> int | None:
        """Get score for a specific analyzer category."""
        result = self.analyzer_results.get(category.value)
        return result.score if result else None


# ---------------------------------------------------------------------------
# Comparison Models (Requirement #1, #3)
# ---------------------------------------------------------------------------


class ComparisonDelta(BaseModel):
    """Difference in a single metric between two scans."""

    metric: str
    label: str
    value_a: Any
    value_b: Any
    delta: float | None = Field(
        default=None, description="Numeric difference (b - a) if applicable"
    )
    winner: str | None = Field(default=None, description="'a', 'b', or 'tie'")
    explanation: str = ""


class ComparisonResult(BaseModel):
    """
    Result of comparing two websites.

    Used by both `jaguar compare` and `jaguar competitor`.
    """

    url_a: str
    url_b: str
    scan_a: ScanResult
    scan_b: ScanResult
    deltas: dict[str, list[ComparisonDelta]] = Field(
        default_factory=dict, description="Deltas grouped by category"
    )
    overall_winner: str | None = None
    competitive_insights: list[str] = Field(
        default_factory=list, description="AI-generated competitive analysis insights"
    )
    compared_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Historical / Diff Models (Requirement #6)
# ---------------------------------------------------------------------------


class ScanSummary(BaseModel):
    """Lightweight summary for history listing."""

    id: str
    url: str
    scanned_at: datetime
    overall_score: int
    overall_grade: Grade
    analyzer_scores: dict[str, int] = Field(default_factory=dict)


class ScanDiff(BaseModel):
    """
    Difference between two historical scans of the same site.

    Used by `jaguar diff scan1 scan2`.
    """

    scan_id_a: str
    scan_id_b: str
    url: str
    time_a: datetime
    time_b: datetime
    score_delta: int
    grade_change: str = Field(description="e.g. 'B+ → A-'")
    category_deltas: dict[str, ComparisonDelta] = Field(default_factory=dict)
    new_findings: list[Finding] = Field(default_factory=list)
    resolved_findings: list[Finding] = Field(default_factory=list)
    changed_findings: list[Finding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Plugin Models (Requirement #9)
# ---------------------------------------------------------------------------


class PluginInfo(BaseModel):
    """Metadata for an installed plugin."""

    name: str
    version: str
    description: str
    author: str = ""
    plugin_type: str = Field(description="'analyzer', 'reporter', or 'hook'")
    enabled: bool = True
    entry_point: str = Field(description="Python entry point string")


# ---------------------------------------------------------------------------
# Scan Context (shared state passed to analyzers)
# ---------------------------------------------------------------------------


class ScanContext(BaseModel):
    """
    Shared context passed to every analyzer during a scan.

    Contains the fetched response data, browser handle references,
    and configuration so analyzers don't duplicate work.
    """

    model_config = {"arbitrary_types_allowed": True}

    url: str
    hostname: str
    base_url: str
    response_status: int = 0
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: str = ""
    final_url: str = ""
    redirect_chain: list[str] = Field(default_factory=list)
    tls_info: dict[str, Any] = Field(default_factory=dict)
    cookies: list[dict[str, Any]] = Field(default_factory=list)
    page_resources: list[dict[str, Any]] = Field(
        default_factory=list, description="JS, CSS, image, font resources discovered"
    )
    screenshots: list[Screenshot] = Field(default_factory=list)
    browser_available: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
