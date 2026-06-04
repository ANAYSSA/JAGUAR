# JAGUAR Architecture

JAGUAR is a premium, pure-Python Website Intelligence Platform designed for high-performance security, SEO, and techstack analysis, along with advanced website cloning capabilities.

## 1. Core Engine (`jaguar.core.engine`)
The `ScanEngine` is the central orchestrator of JAGUAR.
- It accepts a target URL and creates an asynchronous execution context (`ScanContext`).
- It parallelizes the execution of all registered `AnalyzerProtocol` plugins using `asyncio.gather`.
- It aggregates the results and computes the final technical grade using the `Scorer` engine.

## 2. Analyzer Flow (`jaguar.analyzers`)
Analyzers operate via a strict plugin architecture:
1. Each analyzer implements `AnalyzerProtocol` (defining `name`, `category`, and `weight`).
2. The plugin system (`PluginRegistry`) automatically discovers analyzers via `entry_points` or explicit registration.
3. During a scan, each analyzer performs its domain-specific checks (e.g. Security headers, SEO tags, AI generation footprints).
4. They yield a standardized `AnalyzerResult` comprising `Findings` (pass/fail states) and `Recommendations`.

## 3. Cloner Flow (`jaguar.cloner`)
The Cloner subsystem is an asynchronous recursive web scraper.
- **Engine**: The `ClonerEngine` processes an entire domain within bounded constraints (`max_depth`, `max_pages`).
- **SPA Renderer**: If `--spa` is provided, it leverages Playwright to evaluate Javascript frameworks (React, Next.js, Vue) and capture the hydrated HTML.
- **Link Rewriter**: Converts absolute domains and CDNs into relative local paths to ensure the cloned directory operates completely offline without external requests.
- **Server**: Provides a local lightweight HTTP server to immediately view the offline copy.

## 4. Reporting Flow (`jaguar.reporters`)
Reporting converts the internal `ScanResult` schema into human and machine-readable artifacts.
- The `ReporterProtocol` dictates the contract.
- Current reporters include:
  - **Console**: Rich, interactive CLI output.
  - **JSON**: Machine-parseable output for CI/CD integrations.
  - **Markdown**: Readme-friendly format.
  - **HTML**: Standalone interactive dashboards with built-in charts using Jinja2 templates.

## 5. Database Flow (`jaguar.storage.database`)
JAGUAR maintains historical metrics.
- Uses a local SQLite database (`jaguar.db`).
- Upon completion of any scan (unless `--no-store` is used), the `ScanEngine` archives the summary.
- Users can view past scans (`jaguar history`) or natively compute metric drift using `jaguar diff`.

## Independence Guarantee
JAGUAR executes without reliance on external tools such as `nmap`, `trufflehog`, or `axe-core`. All analysis is mathematically and heuristically computed directly in native Python.
