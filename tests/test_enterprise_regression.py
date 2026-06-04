# mypy: ignore-errors
import pytest

from jaguar.analyzers import get_all_analyzers
from jaguar.core.engine import ScanEngine

DOMAINS = [
    "https://github.com",
    "https://google.com",
    "https://microsoft.com",
    "https://cloudflare.com"
]

@pytest.mark.asyncio
async def test_enterprise_regression_no_failures() -> None:
    """
    Ensure Google, Microsoft, GitHub and Cloudflare never receive a failing score
    because of redirect parsing, user-agent differences, or cookie parsing.
    """
    engine = ScanEngine(enterprise_mode=True)
    get_all_analyzers()

    for domain in DOMAINS:
        res = await engine.scan(domain)

        # Ensure we got a valid score
        assert res.overall_score is not None

        # GitHub and Cloudflare are known to have high scores
        if "github" in domain or "cloudflare" in domain:
            assert res.overall_score.score >= 90, f"{domain} scored poorly: {res.overall_score.score}."

        # Ensure critical components like HTTPS didn't incorrectly fail
        sec = res.analyzer_results.get("security")
        assert sec is not None

        findings = {f.name: f for f in sec.findings}

        # They should all have HTTPS working
        assert findings["https-enabled"].passed, f"HTTPS check failed on {domain}"

    await engine.close()
