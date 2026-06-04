# JAGUAR Clone Debugging Guide

The JAGUAR cloner performs a sophisticated offline website extraction. This guide documents the v1.0.5 algorithms for rewriting, validation, and visual comparison.

## Universal Resource Rewriter

The `Rebuilder` engine uses a `BeautifulSoup` AST to perform a universal rewrite of all resource paths.
1. **Extraction**: Finds all `link`, `script`, `img`, `source`, `video`, `audio`, `embed`, `object`, `form`, and `meta` tags. It also parses `srcset` strings to extract all image candidate paths.
2. **Resolution**: Attempts to resolve the given relative path from the perspective of the `clone_dir` root, or if not found, from the directory of the current HTML file.
3. **Rewrite**: Re-computes the shortest relative path from the current HTML document to the localized asset on disk (`../v3/main.css`) ensuring 0 broken links regardless of the original web server structure.

## Validation Engine

`CloneValidator` parses the final rewritten HTML files and ensures every asset points to a physically existing file.
* Tracks Health Metrics for HTML, CSS, JS, Fonts, Images, SVG, Media, and Manifests.
* Compiles `CLONE_REPORT.md` inside the target directory specifying exactly which files are OK and which are Missing.

## Visual Comparison Engine

When invoked with `--verify`, `VisualCompare`:
1. Screenshots the live production site using Playwright.
2. Spawns a localized `ThreadingTCPServer` to serve the clone.
3. Attaches listeners for `console`, `pageerror`, and `requestfailed` events to instantly trap 404s and JS errors.
4. Screenshots the local clone.
5. Pixel-diffs both images.
6. Automatically marks the clone as **FAILED** if Visual Accuracy falls below **98.0%** or if any console errors are trapped.
