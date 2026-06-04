# JAGUAR Release Notes

## v1.0.4 - Visual Clone Accuracy & Website Rebuilder
- **CSS Resolver**: Recursively downloads @import chains, @font-face fonts, and background-image assets up to 5 levels deep.
- **Website Rebuilder**: Post-clone phase that detects entry points, creates root redirects, rewrites absolute/root-relative URLs, fixes inline styles, and patches manifest files.
- **Clone Validator**: Generates CLONE_REPORT.md with health percentages for HTML, CSS, JS, Fonts, and Images.
- **Visual Compare**: jaguar clone --verify captures Playwright screenshots of original and clone, producing a pixel-level Visual Accuracy score.
- **Smart Serve**: jaguar serve auto-detects entry pages and creates redirects so no directory listing appears.
- **Link Rewriter**: Now handles source, video, audio, srcset, inline style url(), meta og:image, object, embed, and video poster attributes.
