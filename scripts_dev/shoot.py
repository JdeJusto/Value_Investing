"""Capture screenshots of the themed Streamlit UI (dev-only helper).

Starts the app on port 8510 with VI_DEMO=1, waits for it, then screenshots
each page. Not part of the app or the test suite.

Usage:
    python scripts_dev/shoot.py home screener
    python scripts_dev/shoot.py --all
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PORT = 8510
BASE = f"http://localhost:{PORT}"
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

# page name -> (url_path, screenshot filename)
PAGES = {
    "home": ("", "ui_v2_home.png"),
    "analysis": ("analysis", "ui_v2_analysis_methodologies.png"),
    "screener": ("screener", "ui_v2_screener.png"),
    "portfolio": ("portfolio", "ui_v2_portfolio.png"),
    "reports": ("reports", "ui_v2_reports.png"),
    "consensus": ("consensus", "ui_v2_consensus.png"),
}


def _start_server() -> subprocess.Popen:
    env = dict(os.environ, VI_DEMO="1")
    proc = subprocess.Popen(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            "-m",
            "streamlit",
            "run",
            str(ROOT / "ui" / "app.py"),
            "--server.headless",
            "true",
            "--server.port",
            str(PORT),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def _wait_for_server(timeout: float = 60.0) -> None:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:  # noqa: BLE001 — server not up yet
            time.sleep(1.0)
    raise RuntimeError(f"Streamlit did not come up on {BASE}")


def _shoot(names: list[str]) -> None:
    from playwright.sync_api import sync_playwright

    ASSETS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        for name in names:
            if name.startswith("analysis:"):
                _, tab = name.split(":", 1)
                _shoot_analysis_tab(page, tab)
                continue
            url_path, filename = PAGES[name]
            page.goto(f"{BASE}/{url_path}", wait_until="networkidle")
            page.wait_for_timeout(3500)
            out = ASSETS / filename
            page.screenshot(path=str(out), full_page=True)
            print(f"{name}: {out} ({out.stat().st_size} bytes)")
        browser.close()


def _analysis_tab_filename(tab: str) -> str:
    return {
        "Methodologies": "ui_v2_analysis_methodologies.png",
        "Scorecard": "ui_v2_analysis_scorecard.png",
        "DCF": "ui_v2_analysis_dcf.png",
    }.get(tab, f"ui_v2_analysis_{tab.lower()}.png")


def _shoot_analysis_tab(page, tab: str) -> None:
    """Open Analysis, run the default ticker, then screenshot one tab."""
    page.goto(f"{BASE}/analysis", wait_until="networkidle")
    page.wait_for_timeout(2500)
    page.get_by_role("button", name="Analyze").click()
    page.wait_for_timeout(6000)
    # Streamlit tabs are role="tab"; click the requested one.
    page.get_by_role("tab", name=tab, exact=True).click()
    page.wait_for_timeout(4000)
    out = ASSETS / _analysis_tab_filename(tab)
    page.screenshot(path=str(out), full_page=True)
    print(f"analysis:{tab}: {out} ({out.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pages", nargs="*")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    names = list(PAGES) if args.all else (args.pages or ["home"])

    proc = _start_server()
    try:
        _wait_for_server()
        _shoot(names)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
