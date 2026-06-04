from jaguar.core.models import Finding, Severity


def test_finding_creation():  # type: ignore
    finding = Finding(
        name="test-finding",
        title="Test Finding",
        description="A test finding.",
        passed=True,
        severity=Severity.INFO,
        score_modifier=0,
    )
    assert finding.name == "test-finding"
    assert finding.passed is True
    assert finding.severity == Severity.INFO
