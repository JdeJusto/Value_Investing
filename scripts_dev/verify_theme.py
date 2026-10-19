"""Verify the synthwave theme actually applied (computed styles).

Boots the app on 8510 with VI_DEMO=1, opens a page, and asserts that key
elements carry the theme: injected :root vars, the .vi-header band, the
Playfair heading font, and the deep-night background. Prints a PASS/FAIL
per check so a phase's visual check is reproducible without eyeballing.

Usage:
    python scripts_dev/verify_theme.py home
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shoot import BASE, PORT, PAGES, _start_server, _wait_for_server  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402


def _verify(page, name: str) -> bool:
    url_path, _ = PAGES[name]
    page.goto(f"{BASE}/{url_path}", wait_until="networkidle")
    page.wait_for_timeout(3500)

    checks: list[tuple[str, bool, str]] = []

    # 1. The CSS was injected (a <style> tag containing our :root palette).
    injected = page.evaluate(
        "() => [...document.querySelectorAll('style')].some(s => s.textContent.includes('--vi-neon-pink'))"
    )
    checks.append(("css injected", injected, ""))

    # 2. The .vi-header band exists and has the gradient background.
    header_bg = page.evaluate(
        "() => { const h = document.querySelector('.vi-header');"
        "return h ? getComputedStyle(h).backgroundImage : null; }"
    )
    checks.append(("vi-header band", bool(header_bg and "gradient" in header_bg), str(header_bg)[:60]))

    # 3. Headings use Playfair Display.
    heading_font = page.evaluate(
        "() => { const h = document.querySelector('.vi-header h1, h1');"
        "return h ? getComputedStyle(h).fontFamily : null; }"
    )
    checks.append(("heading Playfair", bool(heading_font and "Playfair" in heading_font), str(heading_font)[:60]))

    # 4. Body/background is the deep night #0a0a1a (rgb(10,10,26)).
    body_bg = page.evaluate(
        "() => getComputedStyle(document.body).backgroundColor"
        " || getComputedStyle(document.querySelector('[data-testid=\"stAppViewContainer\"]')).backgroundColor"
    )
    checks.append(("deep-night bg", "10, 10, 26" in str(body_bg), str(body_bg)))

    # 5. Metric widgets carry the card surface (#14142b = rgb(20,20,43)).
    metric_bg = page.evaluate(
        "() => { const m = document.querySelector('[data-testid=\"stMetric\"]');"
        "return m ? getComputedStyle(m).backgroundColor : null; }"
    )
    checks.append(("metric card surface", "20, 20, 43" in str(metric_bg), str(metric_bg)))

    ok = True
    for label, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            ok = False
        print(f"  [{status}] {label}" + (f"  ({detail})" if detail else ""))
    return ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pages", nargs="*", choices=[*PAGES, "--all"])
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    names = list(PAGES) if args.all else (args.pages or ["home"])

    proc = _start_server()
    all_ok = True
    try:
        _wait_for_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            for name in names:
                print(f"{name}:")
                if not _verify(page, name):
                    all_ok = False
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()
    print("THEME OK" if all_ok else "THEME GAPS PRESENT")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
