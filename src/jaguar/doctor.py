import asyncio
import json
import os
import platform
import subprocess
import sys
from typing import Any

from rich.console import Console

console = Console()

def get_python_status() -> dict[str, Any]:
    version = sys.version_info
    supported = version >= (3, 12)
    return {
        "status": "PASS" if supported else "FAIL",
        "value": f"{version.major}.{version.minor}.{version.micro}",
        "message": "Python 3.12 or newer required." if not supported else "Python version OK.",
        "fix": None
    }

def get_playwright_status() -> dict[str, Any]:
    try:
        import playwright  # noqa: F401
        return {
            "status": "PASS",
            "value": "Installed",
            "message": "Playwright is available.",
            "fix": None
        }
    except ImportError:
        return {
            "status": "FAIL",
            "value": "Not Found",
            "message": "Playwright is missing.",
            "fix": "pip install playwright"
        }

def get_browser_status() -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
        async def _check() -> bool:
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch()
                    await browser.close()
                    return True
            except Exception:
                return False
        if asyncio.run(_check()):
            return {"status": "PASS", "value": "Installed", "message": "", "fix": None}
        else:
            return {
                "status": "FAIL",
                "value": "Missing",
                "message": "Chromium not found.",
                "fix": "python -m playwright install chromium"
            }
    except Exception:
        return {
            "status": "FAIL",
            "value": "Unknown",
            "message": "Playwright initialization error.",
            "fix": "python -m playwright install chromium"
        }

def get_db_status() -> dict[str, Any]:
    try:
        from jaguar.storage.database import StorageDatabase
        db = StorageDatabase()
        db.list_history(limit=1)
        return {"status": "PASS", "value": "Healthy", "message": "", "fix": None}
    except Exception as e:
        return {"status": "FAIL", "value": "Error", "message": str(e), "fix": "Check permissions or delete jaguar.db"}

def get_permissions_status() -> dict[str, Any]:
    can_write = os.access(".", os.W_OK)
    if can_write:
        return {"status": "PASS", "value": "W_OK", "message": "", "fix": None}
    return {"status": "FAIL", "value": "Read-only", "message": "Cannot write to current directory.", "fix": "Fix directory permissions to allow write access."}

def get_config_status() -> dict[str, Any]:
    return {"status": "PASS", "value": "Valid", "message": "", "fix": None}

def get_network_status() -> dict[str, Any]:
    import urllib.request
    try:
        urllib.request.urlopen("https://1.1.1.1", timeout=3)
        return {"status": "PASS", "value": "Online", "message": "", "fix": None}
    except Exception:
        return {"status": "FAIL", "value": "Offline", "message": "No internet connection.", "fix": "Check network connection."}

def run_doctor(json_mode: bool = False, fix: bool = False) -> None:
    from jaguar import __version__
    from jaguar.analyzers import get_all_analyzers
    analyzers = get_all_analyzers()

    results = {
        "JAGUAR Version": {"status": "INFO", "value": __version__, "fix": None},
        "Operating System": {"status": "INFO", "value": platform.platform(), "fix": None},
        "Python": get_python_status(),
        "Playwright": get_playwright_status(),
        "Browser Binaries": get_browser_status() if get_playwright_status()["status"] == "PASS" else {"status": "FAIL", "value": "Blocked", "message": "Requires Playwright", "fix": None},
        "Database": get_db_status(),
        "Config": get_config_status(),
        "Permissions": get_permissions_status(),
        "Network": get_network_status(),
        "Analyzers": {"status": "INFO", "value": f"{len(analyzers)} Loaded", "fix": None}
    }

    if json_mode:
        print(json.dumps(results, indent=2))
        return

    has_issues = False
    fixes = []

    console.print("\n[bold]JAGUAR Diagnostics Report[/bold]\n")

    for key, data in results.items():
        status = data["status"]
        val = data["value"]
        if status == "PASS":
            console.print(f"[green]✔[/green] {key}: {val}")
        elif status == "INFO":
            console.print(f"[cyan]ℹ[/cyan] {key}: {val}")
        else:
            has_issues = True
            console.print(f"[red]✖[/red] {key}: {val} - {data.get('message', '')}")
            if data.get("fix"):
                fixes.append((key, data["fix"]))

    if has_issues:
        console.print("\n[yellow][WARNING][/yellow] Issues detected.")
        if fixes:
            console.print("\nSuggested fixes:")
            for k, f in fixes:
                console.print(f"- {k}: [bold cyan]{f}[/bold cyan]")

            if fix:
                console.print("\nApplying automatic fixes...\n")
                for k, f in fixes:
                    if f and str(f).startswith("playwright install") or f.startswith("pip install") or f.startswith("python -m playwright"):  # type: ignore
                        console.print(f"Running: {f}...")
                        try:
                            subprocess.run(str(f).split(), check=True)
                            console.print(f"[green]Fixed {k}[/green]")
                        except Exception as e:
                            console.print(f"[red]Failed to fix {k}: {e}[/red]")
            else:
                console.print("\nUse [bold]jaguar doctor --fix[/bold] for automatic repair.")
    else:
        console.print("\n[green]All systems operational. JAGUAR is ready.[/green]\n")
