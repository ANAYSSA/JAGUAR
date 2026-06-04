# JAGUAR Release Checklist

Before tagging a production release, verify all items:

- [x] **Analyzers Working**: Security, SEO, Accessibility, TechStack, UX, Vulnerability, AI Detect/Design.
- [x] **Reporters Working**: Console, JSON, Markdown, HTML.
- [x] **Cloner Working**: Static assets downloaded, SPA rendering active, local server functional.
- [x] **Compare Verified**: Delta engines correctly compute differences between two targets.
- [x] **History Verified**: SQLite database properly stores and retrieves previous scans.
- [x] **Self-Contained**: No external downloaded repositories exist in the tree.
- [x] **Tests Passing**: `pytest -v` runs green.
- [x] **Linters Clean**: `ruff check .` runs green (or with acceptable ignores).
- [x] **Types Strict**: `mypy .` runs green.
- [x] **GitHub Ready**: `.gitignore`, `README.md`, `INSTALL.md`, `GITHUB.md`, `ROADMAP.md` exist.
