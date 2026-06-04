# JAGUAR v1.0.5 Release Notes

## Universal Resource Rewriter
JAGUAR v1.0.5 completely revamps the way offline websites are linked together. It replaces regex-based URL adjustments with a robust BeautifulSoup AST analysis. It now calculates relative path resolutions perfectly regardless of original URL structure or root directories.

## Strict Clone Validation
The clone accuracy engine is drastically upgraded. JAGUAR now generates detailed `CLONE_REPORT.md` summaries confirming 0 missing assets across 8 different categories (HTML, CSS, JS, Fonts, Images, SVG, Media, Manifests).

## Browser Console Verification
When running with `--verify`, JAGUAR natively attaches to Playwright browser console streams and will automatically mark clones as FAILED if any 404 resource errors or JS Exceptions are found, ensuring the offline clone is identical to the production website. Visual Accuracy is now enforced at >98%.

# JAGUAR Release Notes

## v1.0.4 - Visual Clone Accuracy & Website Rebuilder
- **CSS Resolver**: Recursively downloads @import chains, @font-face fonts, and background-image assets up to 5 levels deep.
- **Website Rebuilder**: Post-clone phase that detects entry points, creates root redirects, rewrites absolute/root-relative URLs, fixes inline styles, and patches manifest files.
- **Clone Validator**: Generates CLONE_REPORT.md with health percentages for HTML, CSS, JS, Fonts, and Images.
- **Visual Compare**: jaguar clone --verify captures Playwright screenshots of original and clone, producing a pixel-level Visual Accuracy score.
- **Smart Serve**: jaguar serve auto-detects entry pages and creates redirects so no directory listing appears.
- **Link Rewriter**: Now handles source, video, audio, srcset, inline style url(), meta og:image, object, embed, and video poster attributes.
