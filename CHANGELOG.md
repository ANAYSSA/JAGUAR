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
