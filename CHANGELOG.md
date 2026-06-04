# Changelog

All notable changes to JAGUAR will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
