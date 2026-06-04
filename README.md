# JAGUAR

**JAGUAR by anayssa — Website Intelligence Platform**

The most advanced open-source Website Intelligence Platform written purely in Python. JAGUAR analyzes websites for Security, SEO, Performance, Accessibility, and modern AI footprints, alongside a powerful embedded offline Website Cloner.

## 🚀 Features
- **10 Core Analyzers**: Run comprehensive scans evaluating Content Security Policies, exposed secrets, DOM interactions, SEO metadata, reading complexities, and more.
- **AI Detection Engine**: Identify AI-generated assets, heavily templated designs (e.g., Shadcn/v0), and generative text footprints.
- **Deep SPA Cloner**: Navigate heavily obfuscated Single Page Applications using headless Playwright. JAGUAR penetrates the JS-layer and downloads hydrated offline copies.
- **Competitor Insights**: Compare metrics between two distinct domains to establish engineering drift.
- **Rich Reporting**: Generate native interactive HTML dashboards, Markdown summaries, or JSON output.

## 📦 Installation

See the full [Installation Guide](INSTALL.md).

```bash
git clone https://github.com/ANAYSSA/JAGUAR.git
cd JAGUAR
pip install .[browser]
jaguar doctor --fix
```

## 🛠️ Usage

```bash
# Basic intelligence scan
jaguar scan https://example.com

# Comprehensive scan including AI, UX, and Accessibility
jaguar scan https://example.com -g full

# Compare against a competitor
jaguar compare https://example.com https://competitor.com

# Clone a Next.js / React application offline and serve it
jaguar clone https://nextjs.org --spa --serve

# Clone with visual accuracy verification
jaguar clone https://example.com --verify

# Serve a previously cloned application locally
jaguar serve ./jaguar-clones/nextjs.org
```

## 📖 Documentation
- [Architecture](ARCHITECTURE.md) - Deep dive into JAGUAR internals.
- [Changelog](CHANGELOG.md) - Version history.

## 🛡️ Security Audit
JAGUAR has been audited and contains zero external binary executions (except Playwright browser context), relying exclusively on native Python evaluation heuristics. See [Security Audit](SECURITY_AUDIT.md).

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
