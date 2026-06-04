import datetime
from pathlib import Path

changelog = Path('CHANGELOG.md')
cl_text = changelog.read_text(encoding='utf-8')
new_cl = f"""## [1.0.5] - {datetime.date.today()}
### Added
- Universal Resource Rewriter using BeautifulSoup to intelligently resolve and fix local file paths.
- Comprehensive Validation Engine detecting 404s for HTML, CSS, JS, Images, Fonts, SVG, Manifests, and Media.
- Clone Visual Accuracy strict enforcement (>98%) failing clones on layout divergence.
- Playwright console error detection to capture JS exceptions and failed network requests during verification.
- CLONE_DEBUG.md documentation.

"""
changelog.write_text(cl_text.replace('## [1.0.4]', new_cl + '## [1.0.4]'), encoding='utf-8')

rn = Path('RELEASE_NOTES.md')
rn_text = rn.read_text(encoding='utf-8')
new_rn = """# JAGUAR v1.0.5 Release Notes

## Universal Resource Rewriter
JAGUAR v1.0.5 completely revamps the way offline websites are linked together. It replaces regex-based URL adjustments with a robust BeautifulSoup AST analysis. It now calculates relative path resolutions perfectly regardless of original URL structure or root directories.

## Strict Clone Validation
The clone accuracy engine is drastically upgraded. JAGUAR now generates detailed `CLONE_REPORT.md` summaries confirming 0 missing assets across 8 different categories (HTML, CSS, JS, Fonts, Images, SVG, Media, Manifests).

## Browser Console Verification
When running with `--verify`, JAGUAR natively attaches to Playwright browser console streams and will automatically mark clones as FAILED if any 404 resource errors or JS Exceptions are found, ensuring the offline clone is identical to the production website. Visual Accuracy is now enforced at >98%.

"""
rn.write_text(new_rn + rn_text, encoding='utf-8')
