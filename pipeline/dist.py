"""Package the built site for a static host (Netlify, Cloudflare Pages, any web server).

    python -m pipeline.dist            # writes dist/ from site/glassballot.html

Then upload the dist/ folder. Nothing else is needed: the page is one file with its data inside.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://glassballot.org"
DESC = ("Nonpartisan voter guide to Florida county commission and school board races. Every local race, "
        "every commission vote, who funds each candidate, and a source behind every fact.")

FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30"><rect x="3" y="10" width="24" height="17" rx="3" fill="#0A6B62" fill-opacity="0.14" stroke="#0A6B62" stroke-width="2"/><rect x="10.5" y="3" width="9" height="14" rx="1.5" fill="#fff" stroke="#0A6B62" stroke-width="2"/><path d="M12.8 9.6l1.6 1.6 3-3.2" fill="none" stroke="#0A6B62" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>"""

HEAD = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="{DESC}">
<link rel="canonical" href="{SITE}/">
<link rel="icon" href="/assets/favicon-64.png" type="image/png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<meta name="theme-color" content="#0B3D91">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Glass Ballot">
<meta property="og:title" content="Glass Ballot: every Florida local race, every vote, every dollar">
<meta property="og:description" content="{DESC}">
<meta property="og:url" content="{SITE}/">
<meta property="og:image" content="{SITE}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Glass Ballot: Florida local voter guide">
<meta name="twitter:description" content="{DESC}">
<meta name="twitter:image" content="{SITE}/og.png">
<style>:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
</head>
<body>
"""

OG_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;width:1200px;height:630px;font-family:"Plus Jakarta Sans",system-ui,sans-serif;color:#fff;
background:radial-gradient(90% 90% at 88% 8%,rgba(20,184,166,.38),transparent 55%),radial-gradient(80% 80% at 0% 100%,rgba(37,99,235,.6),transparent 60%),linear-gradient(160deg,#0B3D91,#1A56D0)}
.w{box-sizing:border-box;height:630px;padding:64px 72px;display:grid;grid-template-columns:1fr 330px;gap:30px;align-items:center}
.b{font-weight:800;font-size:44px;letter-spacing:-.03em}.b b{color:#8DB8FF}.b i{font-style:normal;color:#A9C0E8;font-weight:700}
h1{margin:26px 0 18px;font-size:72px;line-height:1;letter-spacing:-.035em;font-weight:800}
p{margin:0;font-size:30px;color:#DCE8FF;line-height:1.35;font-family:Inter,system-ui,sans-serif}
.t{margin-top:34px;font-size:18px;letter-spacing:.32em;font-weight:700;color:#A9C8FF}
.box{width:330px;height:330px;border-radius:64px;background:rgba(255,255,255,.95);display:flex;align-items:center;justify-content:center;box-shadow:0 30px 60px rgba(0,0,0,.25)}
.box img{width:250px}
</style></head><body><div class="w"><div>
<div class="b">Glass<b>Ballot</b><i>.org</i></div>
<h1>Every Florida local race. Every vote. Every dollar.</h1>
<p>How your county commissioners and school board members vote, who pays for their campaigns, and what they promised. In plain English, with a source for every fact.</p>
<div class="t">NONPARTISAN. SOURCED. FREE.</div></div>
<div class="box"><img src="assets/logo-box.png"></div></div></body></html>"""


def build_dist() -> Path:
    src = ROOT / "site" / "glassballot.html"
    region = ROOT / "site" / "region.json"
    out = ROOT / "dist"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    (out / "index.html").write_text(HEAD + src.read_text() + "\n</body>\n</html>\n")
    (out / "favicon.svg").write_text(FAVICON)
    shutil.copytree(ROOT / "site" / "assets", out / "assets", ignore=shutil.ignore_patterns("tb4.json", "fl.json", "zips.json", "zips_fl.json"))
    (out / "data").mkdir()
    if region.exists():
        shutil.copy(region, out / "data" / "glassballot.json")
    cd = out / "data" / "c"
    if cd.exists():
        shutil.rmtree(cd)
    shutil.copytree(ROOT / "site" / "c", cd)
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (out / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{SITE}/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>\n</urlset>\n")
    (out / "_headers").write_text(
        "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n  X-Frame-Options: SAMEORIGIN\n\n"
        "/index.html\n  Cache-Control: public, max-age=300\n\n/data/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=300\n")
    (out / "_redirects").write_text("/*  /index.html  200\n")
    og = ROOT / "site" / "og.png"
    if og.exists():
        shutil.copy(og, out / "og.png")  # rendered once; the nightly job doesn't need a browser
    else:
        (out / "og.html").write_text(OG_HTML)
    return out


if __name__ == "__main__":
    d = build_dist()
    print("Built", d, sorted(p.name for p in d.iterdir()))
