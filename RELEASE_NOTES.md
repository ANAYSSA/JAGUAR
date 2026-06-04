# JAGUAR v1.0.0 Release Notes

We are incredibly excited to announce the initial release of **JAGUAR** (v1.0.0), a premium Website Intelligence Platform written purely in Python.

## Highlights
- **10 Advanced Analyzers**: Spanning Security, SEO, Accessibility, UX, Performance, and modern AI Detection schemas.
- **Deep SPA Cloning Engine**: The powerful `jaguar clone` command uses headless Playwright to penetrate heavily obfuscated Single Page Applications (Next.js, React, Vue) and extract a fully hydrated, relative-pathed offline copy of the site—served immediately via a built-in local server.
- **Competitor Insights**: Compute grading differentials between your infrastructure and competitors using `jaguar compare`.
- **Zero External Tooling**: JAGUAR operates entirely independently. No `nmap`, no `trufflehog`, no third-party APIs. Everything executes cleanly via native asynchronous Python.

## Installation
```bash
pip install .[browser]
jaguar doctor --fix
```

## Getting Started
```bash
# Basic intelligence scan
jaguar scan https://example.com

# Deep AI & UX Scan
jaguar scan https://example.com -g full

# Clone a Next.js application offline
jaguar clone https://nextjs.org --spa
```

Welcome to the future of Website Intelligence.
