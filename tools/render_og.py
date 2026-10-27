"""Render the link preview image (site/og.png) from dist/og.html. Runs in GitHub Actions, which can load web fonts."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
html = ROOT / "dist" / "og.html"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 630})
    pg.goto(html.as_uri())
    pg.wait_for_load_state("networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(ROOT / "site" / "og.png"))
    b.close()
print("rendered site/og.png")
