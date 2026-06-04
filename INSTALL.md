# JAGUAR Installation Guide

JAGUAR (v1.0.9) supports local installation via pip.

## Prerequisites
- Python 3.12+
- Git

## Install from Source (Editable)
```bash
git clone https://github.com/anayssa/jaguar.git
cd jaguar
pip install -e .
```

## Verification
Run `jaguar version` to verify your installation:
```
Version: 1.0.8
Install Type: Editable
Project Path: D:\JAGUAR
Package Path: D:\JAGUAR\src
```

## Quick Start (All Platforms)

We recommend using a virtual environment.

```bash
# 1. Clone the repository
git clone https://github.com/anayssa/jaguar.git
cd jaguar

# 2. Create a virtual environment
python -m venv venv

# 3. Activate the environment
# Windows:
venv\Scripts\activate
# Linux / macOS / Kali:
source venv/bin/activate

# 4. Install JAGUAR with all features (including Playwright)
pip install -e .[all]

# 5. Install Playwright browsers (Required for Accessibility, UX, and AI Design checks)
playwright install chromium
```

## Platform-Specific Notes

### Kali Linux
Kali Linux comes with many of the tools JAGUAR replaces, but JAGUAR runs entirely self-contained. Make sure you don't install it globally using `sudo pip` to avoid conflicts with system packages. Always use `venv`.

### Windows
If you run into issues with long paths during installation, ensure long paths are enabled in your Windows Registry (`Computer\HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled`).

### macOS
If you are running on Apple Silicon (M1/M2/M3), Playwright will download the ARM64 Chromium binary automatically. No Rosetta required.

## Testing Your Installation

Once installed, verify the premium CLI banner loads and the version is displayed:
```bash
jaguar
```

## Configuration

JAGUAR stores cloned websites in `D:\JAGUAR\jaguar-clones` by default. You can customize this:

```bash
# Set globally via CLI
jaguar config set clone_dir "C:\custom\clones"

# Or via environment variable
export JAGUAR_CLONE_DIR="C:\custom\clones"
```

Run your first scan:
```bash
jaguar scan https://example.com
```
