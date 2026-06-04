# JAGUAR GitHub Deployment Guide

Follow these steps to deploy JAGUAR to your GitHub account as a production-ready repository.

## 1. Initialize Git

If you haven't already, initialize the local repository:

```bash
cd jaguar
git init
```

## 2. Prepare `.gitignore`
Make sure you have a `.gitignore` file that excludes the virtual environment, SQLite database, and generated reports:

```text
# .gitignore
venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.mypy_cache/
jaguar.db
jaguar_report_*.html
jaguar_report_*.json
jaguar_report_*.md
```

## 3. Commit the Code
Add all source code and commit:

```bash
git add .
git commit -m "Initial JAGUAR Release: The most advanced open-source Website Intelligence Platform"
```

## 4. Push to GitHub
Create a new empty repository on GitHub named `jaguar`. Then push your code:

```bash
git branch -M main
git remote add origin https://github.com/anayssa/jaguar.git
git push -u origin main
```

## 5. GitHub Actions (Optional Release Workflow)
To automatically publish releases to PyPI or run tests, create `.github/workflows/test.yml`:

```yaml
name: JAGUAR CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .[all]
        playwright install chromium
    - name: Run Tests
      run: pytest -v
    - name: Run Linter
      run: ruff check .
    - name: Type Check
      run: mypy .
```
