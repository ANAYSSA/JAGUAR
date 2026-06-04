"""
Post-clone website rebuilder for JAGUAR.

Runs after initial cloning to fix broken paths, detect entry points,
rewrite inline styles, handle manifests, and ensure the clone
opens correctly when served locally.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("jaguar.cloner.rebuilder")

# SPA framework markers
SPA_MARKERS = [
    "data-reactroot",
    'id="__next"',
    "data-v-",
    "ng-version",
    "data-nuxt",
    'id="app"',
    'id="root"',
]


def classify_file(path: Path) -> str:
    """Classify file as 'html', 'css', 'js', 'json', or 'unknown' based on metadata, extension, and content."""
    if not path.is_file():
        return "unknown"

    # 1. Check sidecar metadata
    meta_path = path.with_name(path.name + ".meta.json")
    if meta_path.exists():
        try:
            import json as _json
            meta = _json.loads(meta_path.read_text(encoding="utf-8"))
            ct = meta.get("Content-Type", "").lower()
            if "text/html" in ct:
                return "html"
            if "text/css" in ct:
                return "css"
            if "javascript" in ct or "ecmascript" in ct:
                return "js"
            if "json" in ct:
                return "json"
        except Exception:
            pass

    # 2. Check extension/filename suffixes
    ext = path.suffix.lower()
    if ext in (".html", ".htm"):
        return "html"
    if ext == ".css" or path.name == "styles.php" or path.name == "theme.php":
        return "css"
    if ext == ".js" or path.name == "javascript.php" or path.name == "yui_combo.php":
        return "js"
    if ext in (".json", ".webmanifest"):
        return "json"
    if ext == ".php":
        return "html"

    # 3. Sniff content
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
        text = chunk.decode("utf-8", errors="ignore").strip().lower()
        if text.startswith("<!doctype html") or "<html" in text or "<body" in text:
            return "html"
        if "import " in text or "const " in text or "let " in text or "function" in text or text.startswith("(function"):
            return "js"
        if "{" in text and ("body {" in text or "html {" in text or "@import" in text or "margin:" in text):
            return "css"
    except Exception:
        pass

    return "unknown"


class Rebuilder:
    """Post-clone rebuild engine that fixes paths and detects entry points."""

    def __init__(self, clone_dir: Path, base_url: str):
        self.clone_dir = clone_dir
        self.base_url = base_url
        self.base_parsed = urlparse(base_url)
        self.entry_point: str | None = None
        self.is_spa = False

    def rebuild(self) -> dict[str, object]:
        """Run all rebuild phases. Returns a summary dict."""
        summary: dict[str, object] = {}

        # Phase 1: Detect entry point
        self.entry_point = self._detect_entry_point()
        summary["entry_point"] = self.entry_point

        # Phase 2: Create root index.html redirect if needed
        root_index = self.clone_dir / "index.html"
        if not root_index.exists() and self.entry_point:
            self._create_redirect(root_index, self.entry_point)
            summary["redirect_created"] = True
        else:
            summary["redirect_created"] = False

        # Classify files dynamically
        html_files = []
        css_files = []
        js_files = []
        json_files = []

        for p in self.clone_dir.rglob("*"):
            if p.is_file() and not p.name.endswith(".meta.json") and ".jaguar-screenshots" not in p.parts and ".git" not in p.parts:
                t = classify_file(p)
                if t == "html":
                    html_files.append(p)
                elif t == "css":
                    css_files.append(p)
                elif t == "js":
                    js_files.append(p)
                elif t == "json":
                    json_files.append(p)

        summary["files_html_detected"] = len(html_files)
        summary["files_css_detected"] = len(css_files)
        summary["files_js_detected"] = len(js_files)
        summary["files_json_detected"] = len(json_files)

        # Phase 3: Rewrite HTML/PHP files
        html_fixed = 0
        for html_file in html_files:
            if self._rewrite_html(html_file):
                html_fixed += 1
        summary["html_files_processed"] = len(html_files)
        summary["html_files_fixed"] = html_fixed

        # Phase 4: Detect SPA
        if root_index.exists():
            self.is_spa = self._detect_spa(root_index)
        summary["is_spa"] = self.is_spa

        # Phase 5: Fix manifest files (which are JSON)
        manifest_fixed = self._fix_manifests()
        summary["manifests_fixed"] = manifest_fixed

        # Phase 6: Fix inline styles in HTML/PHP
        inline_fixed = 0
        for html_file in html_files:
            if self._fix_inline_styles(html_file):
                inline_fixed += 1
        summary["inline_styles_fixed"] = inline_fixed

        # Phase 7: Fix CSS files
        css_fixed = 0
        for css_file in css_files:
            if self._fix_css_file(css_file):
                css_fixed += 1
        summary["css_files_fixed"] = css_fixed

        # Phase 8: Fix JS files
        js_fixed = 0
        for js_file in js_files:
            if self._fix_js_file(js_file):
                js_fixed += 1
        summary["js_files_fixed"] = js_fixed

        # Phase 9: Fix JSON files
        json_fixed = 0
        for json_file in json_files:
            if self._fix_json_file(json_file):
                json_fixed += 1
        summary["json_files_fixed"] = json_fixed

        logger.info("Rebuild complete: %s", summary)
        return summary

    def _detect_entry_point(self) -> str | None:
        """Find the main entry page of the cloned site."""
        # Check root index.html first
        root_index = self.clone_dir / "index.html"
        if root_index.exists():
            return "index.html"

        # Check for URL-path-based index
        url_path = self.base_parsed.path.strip("/")
        if url_path:
            candidate = self.clone_dir / url_path / "index.html"
            if candidate.exists():
                return str(candidate.relative_to(self.clone_dir)).replace("\\", "/")
            # Try with .html extension
            candidate = self.clone_dir / (url_path + ".html")
            if candidate.exists():
                return str(candidate.relative_to(self.clone_dir)).replace("\\", "/")

        # Find any index.html in subdirectories (prefer shallowest)
        all_indexes = sorted(
            self.clone_dir.rglob("index.html"),
            key=lambda p: len(p.parts),
        )
        if all_indexes:
            return str(all_indexes[0].relative_to(self.clone_dir)).replace("\\", "/")

        # Find any HTML file
        all_html = sorted(
            self.clone_dir.rglob("*.html"),
            key=lambda p: len(p.parts),
        )
        if all_html:
            return str(all_html[0].relative_to(self.clone_dir)).replace("\\", "/")

        return None

    def _create_redirect(self, index_path: Path, target: str) -> None:
        """Create a root index.html that redirects to the entry point."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="0; url={target}">
    <title>Redirecting...</title>
</head>
<body>
    <p>Redirecting to <a href="{target}">{target}</a></p>
</body>
</html>
"""
        index_path.write_text(html, encoding="utf-8")
        logger.info("Created redirect: index.html → %s", target)

    def _rewrite_html(self, html_path: Path) -> bool:
        """Rewrite all relative URLs in an HTML file to local paths using BeautifulSoup."""
        try:
            content = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False

        from bs4 import BeautifulSoup, Tag
        soup = BeautifulSoup(content, "lxml")
        changed = False

        origin = f"{self.base_parsed.scheme}://{self.base_parsed.netloc}"
        host = self.base_parsed.netloc

        def fix_attr(tag: Tag, attr: str) -> None:
            nonlocal changed
            val_raw = tag.get(attr)
            if not val_raw:
                return
            val = val_raw[0] if isinstance(val_raw, list) else str(val_raw)
            if val.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
                return

            from urllib.parse import unquote, urlparse

            # Recursively decode encoded / double-encoded URLs
            val_decoded = val
            for _ in range(3):
                decoded = unquote(val_decoded)
                if decoded == val_decoded:
                    break
                val_decoded = decoded

            is_same_site = False
            path_part = ""
            if val_decoded.startswith((origin, f"http://{host}", f"https://{host}")):
                is_same_site = True
                path_part = urlparse(val_decoded).path
            elif val_decoded.startswith("//" + host):
                is_same_site = True
                path_part = urlparse("https:" + val_decoded).path
            elif not val_decoded.startswith(("http://", "https://", "//")):
                is_same_site = True
                path_part = val_decoded.split("?")[0].split("#")[0]

            if not is_same_site:
                return

            # Clean and split query/fragments
            clean_path = path_part.split("?")[0].split("#")[0].lstrip("/")
            if not clean_path:
                clean_path = "index.html"

            # Check if file exists relative to clone root
            target_path = self.clone_dir / clean_path
            if not target_path.exists():
                # Try relative to the HTML file
                try:
                    target_path = (html_path.parent / clean_path).resolve()
                except Exception:
                    pass

            if not target_path.exists():
                # Search directory for file with the same name
                filename = clean_path.split("/")[-1]
                if filename:
                    found = self._find_asset_in_clone(filename)
                    if found:
                        target_path = found

            if target_path.exists() and target_path.is_file():
                rel = self._relative_from(html_path, target_path)
                if rel != val:
                    tag[attr] = rel
                    changed = True

        for tag in soup.find_all("a", href=True):
            fix_attr(tag, "href")
        for tag in soup.find_all("link", href=True):
            fix_attr(tag, "href")
        for tag in soup.find_all("script", src=True):
            fix_attr(tag, "src")
        for tag in soup.find_all("img", src=True):
            fix_attr(tag, "src")
        for tag in soup.find_all(["source", "video", "audio", "embed", "object", "form"]):
            if tag.has_attr("src"):
                fix_attr(tag, "src")
            if tag.has_attr("data"):
                fix_attr(tag, "data")
            if tag.has_attr("action"):
                fix_attr(tag, "action")
            if tag.has_attr("poster"):
                fix_attr(tag, "poster")

        # Fix srcset
        for tag in soup.find_all(["img", "source"], srcset=True):
            srcset = tag["srcset"]
            parts = []
            for entry in srcset.split(","):
                entry = entry.strip()
                if not entry:
                    continue
                tokens = entry.split()
                if tokens:
                    val = tokens[0]
                    # Recursively decode
                    from urllib.parse import unquote, urlparse
                    val_decoded = val
                    for _ in range(3):
                        decoded = unquote(val_decoded)
                        if decoded == val_decoded:
                            break
                        val_decoded = decoded

                    is_same_site = False
                    path_part = ""
                    if val_decoded.startswith((origin, f"http://{host}", f"https://{host}")):
                        is_same_site = True
                        path_part = urlparse(val_decoded).path
                    elif val_decoded.startswith("//" + host):
                        is_same_site = True
                        path_part = urlparse("https:" + val_decoded).path
                    elif not val_decoded.startswith(("http://", "https://", "//", "javascript:", "mailto:", "tel:", "data:", "#")):
                        is_same_site = True
                        path_part = val_decoded.split("?")[0].split("#")[0]

                    if is_same_site:
                        clean_path = path_part.lstrip("/")
                        target_path = self.clone_dir / clean_path
                        if not target_path.exists():
                            try:
                                target_path = (html_path.parent / clean_path).resolve()
                            except Exception:
                                pass
                        if target_path.exists() and target_path.is_file():
                            tokens[0] = self._relative_from(html_path, target_path)
                            changed = True
                parts.append(" ".join(tokens))
            if changed:
                tag["srcset"] = ", ".join(parts)

        # Fix meta
        for tag in soup.find_all("meta", content=True):
            prop = tag.get("property", "") or tag.get("name", "")
            if "image" in prop.lower() or "url" in prop.lower():
                fix_attr(tag, "content")

        # Fix import maps
        for tag in soup.find_all("script", type="importmap"):
            try:
                import json as _json
                map_data = _json.loads(tag.string or "{}")
                map_changed = False

                for section in ["imports", "scopes"]:
                    if section in map_data and isinstance(map_data[section], dict):
                        for k, v in map_data[section].items():
                            if isinstance(v, str):
                                from urllib.parse import unquote, urlparse
                                val_decoded = v
                                for _ in range(3):
                                    decoded = unquote(val_decoded)
                                    if decoded == val_decoded:
                                        break
                                    val_decoded = decoded

                                is_same = False
                                path_part = ""
                                if val_decoded.startswith((origin, f"http://{host}", f"https://{host}")):
                                    is_same = True
                                    path_part = urlparse(val_decoded).path
                                elif val_decoded.startswith("//" + host):
                                    is_same = True
                                    path_part = urlparse("https:" + val_decoded).path
                                elif not val_decoded.startswith(("http://", "https://", "//")):
                                    is_same = True
                                    path_part = val_decoded.split("?")[0].split("#")[0]

                                if is_same:
                                    clean_path = path_part.lstrip("/")
                                    local_path = self.clone_dir / clean_path
                                    if not local_path.exists():
                                        try:
                                            local_path = (html_path.parent / clean_path).resolve()
                                        except Exception:
                                            pass
                                    if local_path.exists() and local_path.is_file():
                                        rel = self._relative_from(html_path, local_path)
                                        map_data[section][k] = rel
                                        map_changed = True
                if map_changed:
                    tag.string = _json.dumps(map_data, indent=2)
                    changed = True
            except Exception as e:
                logger.error("Failed to parse importmap: %s", e)

        if changed:
            html_path.write_text(str(soup), encoding="utf-8")
            return True
        return False

    def _fix_inline_styles(self, html_path: Path) -> bool:
        """Fix url() references inside style attributes."""
        try:
            content = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False

        original = content
        origin = f"{self.base_parsed.scheme}://{self.base_parsed.netloc}"

        def fix_style_url(match: re.Match[str]) -> str:
            url = match.group(1).strip("'\"").strip()
            if url.startswith("data:"):
                return match.group(0)

            path_to_check = None
            if url.startswith(origin):
                path_to_check = self.clone_dir / url[len(origin):].lstrip("/")
            elif url.startswith("/") and not url.startswith("//"):
                path_to_check = self.clone_dir / url.lstrip("/")
            else:
                path_to_check = (html_path.parent / url.split("?")[0].split("#")[0]).resolve()

            if not path_to_check or not path_to_check.exists():
                filename = url.split("/")[-1].split("?")[0].split("#")[0]
                if filename:
                    found = self._find_asset_in_clone(filename)
                    if found:
                        path_to_check = found

            if path_to_check and path_to_check.exists():
                rel = self._relative_from(html_path, path_to_check)
                return f"url('{rel}')"
            return match.group(0)

        content = re.sub(r"url\(\s*([^)]+)\s*\)", fix_style_url, content)

        if content != original:
            html_path.write_text(content, encoding="utf-8")
            return True
        return False

    def _fix_css_file(self, css_path: Path) -> bool:
        """Fix url() references inside CSS files."""
        try:
            content = css_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False

        original = content
        origin = f"{self.base_parsed.scheme}://{self.base_parsed.netloc}"

        def fix_css_url(match: re.Match[str]) -> str:
            url = match.group(1).strip("'\"").strip()
            if url.startswith("data:"):
                return match.group(0)

            path_to_check = None
            if url.startswith(origin):
                path_to_check = self.clone_dir / url[len(origin):].lstrip("/")
            elif url.startswith("/") and not url.startswith("//"):
                path_to_check = self.clone_dir / url.lstrip("/")
            else:
                path_to_check = (css_path.parent / url.split("?")[0].split("#")[0]).resolve()

            if not path_to_check or not path_to_check.exists():
                filename = url.split("/")[-1].split("?")[0].split("#")[0]
                if filename:
                    found = self._find_asset_in_clone(filename)
                    if found:
                        path_to_check = found

            if path_to_check and path_to_check.exists():
                rel = self._relative_from(css_path, path_to_check)
                return f"url('{rel}')"
            return match.group(0)

        content = re.sub(r"url\(\s*([^)]+)\s*\)", fix_css_url, content)

        if content != original:
            css_path.write_text(content, encoding="utf-8")
            return True
        return False

    def _find_asset_in_clone(self, filename: str) -> Path | None:
        if not filename:
            return None
        matches = list(self.clone_dir.rglob(filename))
        return matches[0] if matches else None

    def _fix_manifests(self) -> int:
        """Fix paths in manifest.json / site.webmanifest files."""
        fixed = 0
        for manifest_path in list(self.clone_dir.rglob("manifest.json")) + list(
            self.clone_dir.rglob("site.webmanifest")
        ):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                changed = False

                # Fix icon paths
                for icon in data.get("icons", []):
                    src = icon.get("src", "")
                    if src.startswith("/"):
                        icon["src"] = src.lstrip("/")
                        changed = True

                if data.get("start_url", "").startswith("/"):
                    data["start_url"] = data["start_url"].lstrip("/")
                    changed = True

                if changed:
                    manifest_path.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    fixed += 1
            except Exception as e:
                logger.debug("Failed to fix manifest %s: %s", manifest_path, e)

        return fixed

    def _detect_spa(self, html_path: Path) -> bool:
        """Check if an HTML file is a Single Page Application."""
        try:
            content = html_path.read_text(encoding="utf-8", errors="replace")
            return any(marker in content for marker in SPA_MARKERS)
        except Exception:
            return False

    def _relative_from(self, from_file: Path, to_file: Path) -> str:
        """Calculate a relative path from one file to another."""
        try:
            rel = to_file.relative_to(from_file.parent)
            return str(rel).replace("\\", "/")
        except ValueError:
            from_parts = from_file.parent.parts
            to_parts = to_file.parts
            common = 0
            for a, b in zip(from_parts, to_parts, strict=False):
                if a == b:
                    common += 1
                else:
                    break
            ups = [".."] * (len(from_parts) - common)
            downs = list(to_parts[common:])
            return "/".join(ups + downs)

    def _fix_js_file(self, js_path: Path) -> bool:
        try:
            content = js_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False

        original = content
        origin = f"{self.base_parsed.scheme}://{self.base_parsed.netloc}"
        host = self.base_parsed.netloc

        def replace_js_url(match: re.Match[str]) -> str:
            quote = match.group(1)
            url = match.group(2).strip()

            if url.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
                return match.group(0)

            is_match = False
            path_part = ""
            if url.startswith((origin, f"http://{host}", f"https://{host}")):
                is_match = True
                path_part = urlparse(url).path
            elif url.startswith("//" + host):
                is_match = True
                path_part = urlparse("https:" + url).path
            elif url.startswith("/") and not url.startswith("//"):
                is_match = True
                path_part = url

            if is_match:
                from urllib.parse import unquote
                decoded_path = unquote(unquote(path_part.split("?")[0].split("#")[0])).lstrip("/")
                local_path = self.clone_dir / decoded_path

                if local_path.exists() and local_path.is_file():
                    rel = self._relative_from(js_path, local_path)
                    return f"{quote}{rel}{quote}"

            return match.group(0)

        pattern = r"(['\"`])(.*?)\1"
        content = re.sub(pattern, replace_js_url, content)

        if content != original:
            js_path.write_text(content, encoding="utf-8")
            return True
        return False

    def _fix_json_file(self, json_path: Path) -> bool:
        try:
            content = json_path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(content)
        except Exception:
            return False

        changed = False
        origin = f"{self.base_parsed.scheme}://{self.base_parsed.netloc}"
        host = self.base_parsed.netloc

        def walk(node: Any) -> Any:
            nonlocal changed
            if isinstance(node, dict):
                for k, v in node.items():
                    node[k] = walk(v)
                return node
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    node[i] = walk(v)
                return node
            elif isinstance(node, str):
                url = node.strip()
                if url.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
                    return node

                is_match = False
                path_part = ""
                if url.startswith((origin, f"http://{host}", f"https://{host}")):
                    is_match = True
                    path_part = urlparse(url).path
                elif url.startswith("//" + host):
                    is_match = True
                    path_part = urlparse("https:" + url).path
                elif url.startswith("/") and not url.startswith("//"):
                    is_match = True
                    path_part = url

                if is_match:
                    from urllib.parse import unquote
                    decoded_path = unquote(unquote(path_part.split("?")[0].split("#")[0])).lstrip("/")
                    local_path = self.clone_dir / decoded_path
                    if not local_path.exists():
                        try:
                            local_path = (json_path.parent / decoded_path).resolve()
                        except Exception:
                            pass
                    if local_path.exists() and local_path.is_file():
                        rel = self._relative_from(json_path, local_path)
                        changed = True
                        return rel
            return node

        data = walk(data)
        if changed:
            json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        return False
