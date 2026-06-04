## [1.1.1] - 2026-06-04
### Added
- Universal Playwright-driven rendering validation: Clone Health is now benchmarked against an actual offline Chromium render instance verifying DOM layout and HTTP 404s dynamically.
- `jaguar clone-doctor <path>` CLI command to instantly diagnose broken local asset references.
- `jaguar serve <path>` now embeds a native SPA `SPARequestHandler` that cleanly intercepts 404s, returning `index.html` to allow Next.js/React/Vue client routing to execute seamlessly while still natively logging broken `.css`/`.js` fetches to the CLI.

### Fixed
- **CRITICAL**: Fixed a severe path-traversal bug where `jaguar serve` without arguments could maliciously serve the user's home or root directory instead of the clone. Serve now explicitly refuses to start unless the target directory contains valid `.html` files.
- Fixed critical CSS variable parsing where `url()` statements nested inside `var(--prop, url(...))` were ignored.
- Fixed `url()` and `src=` attributes resolution failing on URL-encoded strings (e.g. `%20` for spaces) and protocol-relative domains (`//`).
- Fixed an issue where deeply nested `@import` CSS files failed to recursively anchor their child URLs properly.
- `Clone Health: 100%` is now strictly hard-blocked if any offline console errors, visual screenshot mismatches, or missing Playwright network intercepts fire. Missing CSS and JS assets now severely penalize health score.

## [1.0.9] - 2026-06-04
### Added
- Native OS UI Language Detection mapping Windows kernel display settings directly to JAGUAR.
- `Accept-Language` headers are now automatically injected into all `aiohttp` requests to enforce regional assets/responses.
- Added `--lang` override parameter to `jaguar clone` CLI, allowing manual forcing of any locale.
- Redesigned the CLONE_REPORT.md structure to expose `Detected System Language`, `Selected Clone Language`, and `Final Site Language`.

### Fixed
- Fixed an issue where Github and other modern sites would default to unexpected regional languages (e.g. German instead of English/Russian).
- Playwright SPA contexts now reliably receive the enforced locale, driving internal navigator languages and dates matching the selected translation.

## [1.0.8] - 2026-06-04
### Added
- Packaging Sync: Fully synchronized pyproject.toml hatchling versioning with pip dist-info metadata.
- Interactive Progress UI: Live terminal dashboard displaying Processed URLs, Downloaded Assets, Failed Assets, Queue Size, Elapsed Time, and Current URL during `jaguar clone`.
- Added `jaguar version` command revealing installation type (Editable vs Standard) and package path.
- Completely redesigned `JAGUAR` CLI banner to use `rich.panel.Panel` and automatic center alignment, preventing ASCII distortion.

### Fixed
- Fixed Clone Health Accuracy calculating `100%` on non-existent websites by adding a root fetch abort and strict `index.html` fallback.
- Added strict fallback prioritization for Site Language (`config` -> `Header/HTML` -> `OS Locale`) preventing arbitrary translations of cloned SPAs.
- Handled graceful exit of the progress UI upon clone completion to avoid hanging threads.

## [1.0.7] - 2026-06-04
### Added
- Language Preservation: Accurately detects and passes the original site locale (`html lang`, `Content-Language` header, or OS default) to Playwright and clone reports to prevent unexpected translation issues.
- `jaguar serve` command now accepts `latest` as an argument to serve the most recently created clone, and automatically resolves `domain.com` from inside the clone directory.
- Clone Validation expanded to report `Missing Assets / Broken Links / 404s` with full path detection.
- Asset Rewrite Engine automatically finds and repairs broken paths by searching the clone directory for misplaced CSS/JS/images.
- CLI banner centered correctly and success output enhanced with exact Processing, Missing Assets, and Elapsed Time stats.

### Fixed
- Fixed an issue where the clone engine would freeze for ~15 seconds after completion by introducing queue drains and strict timeouts upon reaching `max_pages`.
- Fixed Clone Health scoring: A missing `index.html` (homepage) now correctly forces Clone Health to `0%`. Missing linked assets accurately penalize overall health.
- Fixed `url(...)` path handling for inline styles and CSS files to correctly generate relative, offline-compatible paths.

## [1.0.6] - 2026-06-04
### Added
- Configurable clone storage directory via `jaguar config set clone_dir` or `JAGUAR_CLONE_DIR`.
- Automatic migration of old clones during `jaguar doctor --fix`.

### Fixed
- Fixed `asyncio.Queue` `task_done()` bug inside `_page_worker` loop causing crashes during large clones.
- Clone stability improvements and GitHub clone stress testing fixes.

## [1.0.5] - 2026-06-04
### Added
- Universal Resource Rewriter using BeautifulSoup to intelligently resolve and fix local file paths.
- Comprehensive Validation Engine detecting 404s for HTML, CSS, JS, Images, Fonts, SVG, Manifests, and Media.
- Clone Visual Accuracy strict enforcement (>98%) failing clones on layout divergence.
- Playwright console error detection to capture JS exceptions and failed network requests during verification.
- CLONE_DEBUG.md documentation.

## [1.0.4] - Visual Clone Accuracy & Website Rebuilder
- Added CSS dependency resolver with recursive @import and @font-face support.
- Added post-clone rebuilder with entry-point detection and path rewriting.
- Added clone validation engine with per-category health scoring.
- Added visual comparison engine via Playwright screenshot diff.
- Added --verify flag to clone command.
- Improved link rewriter with source/video/audio/srcset/inline-style support.
- Smart serve with auto entry-point redirect and proper MIME types.

## [1.0.3] - Enterprise Calibration & Clone UX
- Added jaguar serve command for local cloning.
- Added --serve flag to clone command.
- Improved CSP parsing (Report-Only detection).
- Added GWS server fingerprinting.
- Adjusted SEO heuristic confidence models for enterprise scans.

# Changelog

All notable changes to JAGUAR will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-06-04
### Fixed
- **Enterprise Calibration**: Fixed false positive security header detection behind WAFs by incorporating a browser-based HTTP fallback capture mechanism in `ScanEngine`.
- **Async Resource Cleanup**: Safely suppress buggy `ProactorEventLoop` pipe closure exceptions (`ValueError: I/O operation on closed pipe`) on Windows platforms to prevent trailing output noise after scans.
- **Reporting Engine**: Improved accuracy and output format of `jaguar explain` (Security Evidence Mode), surfacing precise findings, raw headers, expected values, and detection sources.

## [1.0.1] - 2026-06-04
### Fixed
- **HTTP Client**: Fixed `TypeError` crash in `HttpClient` when parsing boolean cookie attributes (`secure`, `httponly`).

## [1.0.0] - 2026-06-04
### Added
- **Core Engine**: Fully asynchronous, plugin-based architecture for high-performance website analysis.
- **Security Analyzer**: Scans for CSP, HSTS, secure cookies, and cross-site protections.
- **Secrets Analyzer**: Deep inspection for exposed API keys, GitHub tokens, and hardcoded passwords.
- **SEO Analyzer**: Validates OpenGraph tags, semantic HTML, and metadata structures.
- **Performance Analyzer**: Computes loading heuristics and measures asset sizes.
- **Accessibility Analyzer**: Ensures WCAG-compliant attributes (ARIA tags, alt texts).
- **Tech Stack Analyzer**: Identifies CMS frameworks, CDNs, and libraries via fingerprinting.
- **UX Analyzer**: Evaluates reading complexity (Flesch scoring) and DOM interaction targets.
- **AI Design Analyzer**: Detects auto-generated Shadcn/UI patterns and Vercel v0 templates.
- **AI Detect Analyzer**: Heuristically scores AI-generated text or images on the page.
- **Vulnerability Analyzer**: Flags outdated known-vulnerable libraries (e.g., old jQuery/React).
- **SPA Cloner (`jaguar clone`)**: Capable of locally downloading fully-hydrated React/Next.js single page applications via headless Playwright, bypassing JS-required constraints. Includes a built-in offline HTTP server.
- **Comparison Engine (`jaguar compare`)**: Compares grading metrics and technical drift between two domains.
- **History Tracker (`jaguar history / diff`)**: Maintains local SQLite storage of past scans to monitor improvements over time.
- **Reporting Ecosystem (`jaguar scan -f`)**: Supports JSON, Markdown, rich Console, and interactive HTML dashboard reports.
- **Diagnostics (`jaguar doctor`)**: Integrated environment health-check and auto-repair.
