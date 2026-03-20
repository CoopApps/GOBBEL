#!/usr/bin/env python3
"""
Download Zeta web build into renderer/zeta-web/
================================================
Zeta is an accurate ZZT emulator by asiekierka that compiles to WebAssembly.
Running this script lets the live renderer show actual ZZT graphics and gameplay
instead of the ASCII fallback view.

Usage:
    python3 renderer/get_zeta.py [--version 0.3.2]

After running, start the renderer:
    python3 renderer/server.py path/to/world.zzt

Then open http://localhost:8080 and click the "ASCII" button to switch to Zeta.
"""

import argparse
import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

ZETA_REPO = "asiekierka/zeta"
# Known web release asset names (adjust if the release naming changes)
ASSET_CANDIDATES = ["zeta-web.zip", "web.zip", "zeta-web-latest.zip"]

ZETA_WEB_DIR = Path(__file__).parent / "zeta-web"


def fetch_latest_version() -> str:
    url = f"https://api.github.com/repos/{ZETA_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "zzt-mcp-renderer"})
    with urllib.request.urlopen(req, timeout=15) as r:
        import json
        data = json.loads(r.read())
    tag = data.get("tag_name", "")
    assets = [a["browser_download_url"] for a in data.get("assets", [])]
    return tag, assets


def download_extract(asset_url: str, dest: Path) -> None:
    print(f"Downloading {asset_url} …")
    req = urllib.request.Request(asset_url, headers={"User-Agent": "zzt-mcp-renderer"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    print(f"Extracting to {dest} …")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)
    print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Download Zeta web build")
    parser.add_argument("--version", default=None, help="Specific release tag (e.g. v0.3.2)")
    args = parser.parse_args()

    print(f"Fetching Zeta release info from github.com/{ZETA_REPO} …")
    try:
        tag, assets = fetch_latest_version()
    except Exception as e:
        print(f"Error fetching release info: {e}", file=sys.stderr)
        print(
            "\nFallback: download the Zeta web build manually from:\n"
            f"  https://github.com/{ZETA_REPO}/releases\n"
            f"and extract it to:  {ZETA_WEB_DIR}\n"
            "Make sure zeta-web/zeta.js and zeta-web/zeta.wasm exist.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Latest release: {tag}")

    # Find the web build asset
    web_asset = None
    for url in assets:
        name = url.rsplit("/", 1)[-1].lower()
        if any(c in name for c in ASSET_CANDIDATES) or "web" in name:
            web_asset = url
            break

    if web_asset is None:
        print("\nCould not find a web build asset. Available assets:")
        for url in assets:
            print(f"  {url}")
        print(
            f"\nDownload one manually and extract to: {ZETA_WEB_DIR}\n"
            "Make sure zeta-web/zeta.js and zeta-web/zeta.wasm exist."
        )
        sys.exit(1)

    download_extract(web_asset, ZETA_WEB_DIR)

    # Verify
    missing = [f for f in ("zeta.js", "zeta.wasm") if not (ZETA_WEB_DIR / f).exists()]
    if missing:
        print(
            f"\nWarning: expected files not found: {missing}\n"
            "The ZIP may use a subdirectory. Check the contents of:\n"
            f"  {ZETA_WEB_DIR}\n"
            "and make sure zeta.js / zeta.wasm are at the top level."
        )
    else:
        print(f"\nZeta web build ready at {ZETA_WEB_DIR}")
        print("Start the renderer:  python3 renderer/server.py path/to/world.zzt")
        print("Then open http://localhost:8080 and click the mode button.")


if __name__ == "__main__":
    main()
