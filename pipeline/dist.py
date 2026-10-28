"""Package the built site for a static host (Netlify, Cloudflare Pages, any web server).

    python -m pipeline.dist            # writes dist/ from site/glassballot.html

Every page has a real address (/pinellas/r/bcc-d2) and its own small HTML file with the
title, description and a plain-text summary already filled in, so search engines and link
previews see the content without running any code. The app itself (one script, one
stylesheet, shared by every page) then takes over in the browser.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://glassballot.org"
DESC = ("Nonpartisan voter guide to Florida county commission and school board races. Every local race, "
        "every commission vote, who funds each candidate, and a source behind every fact.")

FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30"><rect x="3" y="10" width="24" height="17" rx="3" fill="#0A6B62" fill-opacity="0.14" stroke="#0A6B62" stroke-width="2"/><rect x="10.5" y="3" width="9" height="14" rx="1.5" fill="#fff" stroke="#0A6B62" stroke-width="2"/><path d="M12.8 9.6l1.6 1.6 3-3.2" fill="none" stroke="#0A6B62" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>"""

def head(title: str, desc: str, url: str, css: str) -> str:
    e = html.escape
    og_title = title.removesuffix(" | Glass Ballot")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(url)}">
<link rel="icon" href="/assets/favicon-64.png" type="image/png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<meta name="theme-color" content="#0B3D91">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Glass Ballot">
<meta property="og:title" content="{e(og_title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{SITE}/og.png?v=2">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(og_title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{SITE}/og.png?v=2">
<link rel="stylesheet" href="{css}">
<style>:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
</head>
<body>
"""


OG_HTML = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=Plus+Jakarta+Sans:wght@700;800&display=block"><style>
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


GLOBAL_META = {
    "about": ("About Glass Ballot", "Who runs Glass Ballot, how it's paid for, and how to reach us."),
    "standards": ("Our standards", "How Glass Ballot checks facts, labels sources and handles corrections."),
    "sources": ("Where our information comes from", "Every public record and published report Glass Ballot uses, county by county."),
    "corrections": ("Changes and corrections", "Every fact Glass Ballot has changed, with what it said before and the date."),
    "money": ("How campaign money works", "How Florida county campaigns are funded, what the limits are, and how to read the reports."),
    "terms": ("Terms of use", "Terms of use for glassballot.org."),
    "privacy": ("Privacy policy", "What Glass Ballot collects (almost nothing) and what it never does."),
    "accessibility": ("Accessibility", "How Glass Ballot works for people using screen readers, larger text and keyboards."),
}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _date(iso: str | None) -> str:
    if not iso:
        return ""
    y, m, d = (int(x) for x in iso[:10].split("-"))
    return f"{MONTHS[m - 1]} {d}, {y}"


def _vdate(v: dict) -> str:
    return _date(v.get("date")) if v.get("date") else (v.get("dateNote") or "Date not confirmed yet")


def _seat(p: dict) -> str:
    return f"{p.get('office') or ''}{', District ' + str(p['district']) if p.get('district') else ''}"


def _val(f: dict | None):
    return (f or {}).get("value")


def _money(n) -> str:
    return f"${n:,.0f}" if isinstance(n, (int, float)) else ""


def _cname(c: dict) -> str:
    return c["county"]["name"].replace(" County", "")


def _n_races(c: dict) -> int:
    return sum(1 for r in c["races"] if r.get("onNovBallot") is not False)


STATUS = {"incumbent": "In office now", "challenger": "Running", "open": "Running", "former": "Former official"}
DEFAULT = ("Glass Ballot | Florida local election guide", DESC)


def page_meta(path: str, c: dict | None = None, obj: dict | None = None, people: dict | None = None) -> tuple[str, str]:
    """Title and description for a page. Mirrors pageMeta() in site/template.html."""
    parts = [x for x in path.split("/") if x]
    site = "Glass Ballot"
    if not parts:
        return DEFAULT
    if parts[0] in GLOBAL_META:
        t, d = GLOBAL_META[parts[0]]
        return f"{t} | {site}", d
    if c is None:
        return DEFAULT
    n = _cname(c)
    a = parts[1] if len(parts) > 1 else None
    if not a:
        return (f"{n} County ballot guide: {_n_races(c)} local races | {site}",
                f"Who's running for {n} County commission and school board on the Nov 3 ballot, how incumbents voted, and who funds each campaign. A source for every fact.")
    if a == "officials":
        return f"Who's in office in {n} County | {site}", f"Every {n} County commissioner and school board member: how they vote, who funds them, and their attendance."
    if a == "votes":
        return f"{n} County commission votes | {site}", f"Recent {n} County commission decisions in plain English, with how each commissioner voted."
    if a == "vote":
        return f"When and where to vote in {n} County | {site}", f"Election Day hours, early voting and mail ballots in {n} County, from the Supervisor of Elections."
    if a == "r" and obj:
        who = [people[i]["name"] for i in obj.get("people", []) if i in people]
        return (f"{n} {obj['title']}: {' vs. '.join(who)} | {site}",
                f"Compare the candidates for {n} {obj['title']}{': ' + ', '.join(who) if who else ''}. Track records, campaign money and sources, side by side.")
    if a == "p" and obj:
        return (f"{obj['name']}, {_seat(obj)} ({n} County) | {site}",
                f"{obj['name']}'s public record{' in office' if obj.get('status') == 'incumbent' else ''}: votes, campaign money, filings and promises, each with its source.")
    if a == "v" and obj:
        return (f"{obj['headline'].rstrip('.')} ({n} County, {_vdate(obj)}) | {site}",
                f"How each {n} County commissioner voted{' on ' + _vdate(obj) if obj.get('date') else ''}: {obj['headline']}. With the official record.")
    if a == "t" and obj:
        return f"{n} County: {obj['name']} | {site}", obj.get("blurb") or f"{obj['name']} decisions in {n} County."
    return f"{n} County | {site}", DESC


def _person_line(k: str, p: dict) -> str:
    e = html.escape
    bits = [STATUS.get(p.get("status"), "")]
    party = _val(p.get("facts", {}).get("party"))
    if party:
        bits.append(str(party))
    raised = (p.get("money") or {}).get("total")
    extra = f" Raised {_money(raised)} for this campaign." if raised else ""
    return f'<li><a href="/{k}/p/{e(p["id"])}">{e(p["name"])}</a> <span class="muted">({e(" · ".join(b for b in bits if b))})</span>{e(extra)}</li>'


def _vote_line(k: str, v: dict) -> str:
    e = html.escape
    return f'<li><a href="/{k}/v/{e(v["id"])}">{e(v["headline"])}</a> <span class="muted">{e(_vdate(v))} · {e(str(_val(v.get("result")) or ""))}</span></li>'


def render(path: str, c: dict | None, obj: dict | None) -> str:
    """Plain HTML summary of a page, shown to search engines, link previews and anyone without JavaScript.
    The app replaces it with the full interactive page as soon as it starts."""
    e = html.escape
    title, desc = page_meta(path, c, obj, {p["id"]: p for p in c["people"]} if c else None)
    h1 = title.removesuffix(" | Glass Ballot")
    out = [f'<div class="stack view prerender"><h1 class="h1">{e(h1)}</h1><p class="lede">{e(desc)}</p>']
    if c:
        k = c["county"]["id"]
        P = {p["id"]: p for p in c["people"]}
        parts = [x for x in path.split("/") if x]
        a = parts[1] if len(parts) > 1 else None
        if not a:
            for r in c["races"]:
                if r.get("onNovBallot") is False:
                    continue
                out.append(f'<section><h2 class="h2"><a href="/{k}/r/{e(r["id"])}">{e(r["title"])}</a></h2><p class="small">Who votes: {e(r.get("who") or "")}</p>'
                           f'<ul>{"".join(_person_line(k, P[i]) for i in r.get("people", []) if i in P)}</ul></section>')
            if c["votes"]:
                out.append(f'<section><h2 class="h2">Recent county commission decisions</h2><ul>{"".join(_vote_line(k, v) for v in c["votes"][:12])}</ul></section>')
        elif a == "officials":
            out.append(f'<ul>{"".join(_person_line(k, p) + "" for p in c["people"] if p.get("status") == "incumbent")}</ul>')
        elif a == "votes":
            out.append(f'<ul>{"".join(_vote_line(k, v) for v in c["votes"])}</ul>')
        elif a == "r" and obj:
            out.append(f'<p>Who votes: {e(obj.get("who") or "")}</p><ul>{"".join(_person_line(k, P[i]) for i in obj.get("people", []) if i in P)}</ul>')
        elif a == "p" and obj:
            f = obj.get("facts", {})
            rows = [("Seat", _seat(obj)), ("Status", STATUS.get(obj.get("status"), "")), ("Party", _val(f.get("party"))), ("In office since", _val(f.get("inOfficeSince"))),
                    ("Work", _val(f.get("job"))), ("Money raised", _money((obj.get("money") or {}).get("total"))), ("Voting record", _val(f.get("record"))), ("Attendance", _val(f.get("attendance")))]
            out.append("<dl>" + "".join(f"<dt>{e(a_)}</dt><dd>{e(str(b_))}</dd>" for a_, b_ in rows if b_) + "</dl>")
            if obj.get("race"):
                out.append(f'<p><a href="/{k}/r/{e(obj["race"])}">Compare everyone in this race</a></p>')
        elif a == "v" and obj:
            roll = _val(obj.get("roll")) or {}
            nm = lambda ids: ", ".join(P[i]["name"] if i in P else i for i in ids) or "None"
            out.append(f'<p><b>Result:</b> {e(str(_val(obj.get("result")) or ""))}</p>')
            if obj.get("inShort"):
                out.append(f'<p>{e(obj["inShort"])}</p>')
            out.append(f'<p><b>Yes:</b> {e(nm(roll.get("yes", [])))}</p><p><b>No:</b> {e(nm(roll.get("no", [])))}</p>')
            if obj.get("officialTitle"):
                wording = re.sub(r"\s+", " ", obj["officialTitle"])
                out.append(f'<p class="small"><b>Official wording:</b> {e(wording)}</p>')
            if obj.get("sourceUrl"):
                out.append(f'<p class="small"><a href="{e(obj["sourceUrl"])}" rel="noopener">The county\'s official record</a></p>')
        elif a == "t" and obj:
            out.append(f'<ul>{"".join(_vote_line(k, v) for v in c["votes"] if v.get("topic") == obj["id"])}</ul>')
        out.append(f'<p><a href="/{k}">Back to the {e(_cname(c))} County ballot</a></p>')
    out.append("</div>")
    return "".join(out)


def pages(region: dict):
    """Every address worth its own file: (path, county, object)."""
    yield "/", None, None
    for g in GLOBAL_META:
        yield f"/{g}", None, None
    for k in region["order"]:
        c = region["counties"][k]
        yield f"/{k}", c, None
        for sub in ("officials", "votes", "vote"):
            yield f"/{k}/{sub}", c, None
        for r in c["races"]:
            yield f"/{k}/r/{r['id']}", c, r
        for p in c["people"]:
            yield f"/{k}/p/{p['id']}", c, p
        for v in c["votes"]:
            yield f"/{k}/v/{v['id']}", c, v
        for t in c["topics"]:
            yield f"/{k}/t/{t['id']}", c, t


def split_page(page: str) -> tuple[str, str, str, str]:
    """Pull the one stylesheet and the one script out of the built page so every page can share them.
    Font links that sit above the stylesheet move into each page's head; its placeholder title is dropped."""
    m = re.search(r"<style>(.*?)</style>", page, re.S)
    extra = re.sub(r"<title>.*?</title>\s*", "", page[:m.start()], flags=re.S).strip()
    css, page = m.group(1), page[m.end():]
    s = page.rfind("<script>")
    js = page[s + len("<script>"):page.rindex("</script>")]
    body = page[:s] + "__APP_SCRIPT__" + page[page.rindex("</script>") + len("</script>"):]
    return extra, css, js, body


def build_dist() -> Path:
    src = ROOT / "site" / "glassballot.html"
    region_p = ROOT / "site" / "region.json"
    out = ROOT / "dist"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    shutil.copytree(ROOT / "site" / "assets", out / "assets", ignore=shutil.ignore_patterns("tb4.json", "fl.json", "zips.json", "zips_fl.json"))
    extra, css, js, body = split_page(src.read_text())
    h = lambda s: hashlib.sha256(s.encode()).hexdigest()[:10]
    css_name, js_name = f"/assets/app-{h(css)}.css", f"/assets/app-{h(js)}.js"
    (out / css_name.lstrip("/")).write_text(css)
    (out / js_name.lstrip("/")).write_text(js)
    body = body.replace("__APP_SCRIPT__", f'<script src="{js_name}"></script>')
    css_name_tag = css_name
    head_ = lambda title, desc, url: head(title, desc, url, css_name_tag).replace("<link rel=\"stylesheet\"", extra + "\n<link rel=\"stylesheet\"", 1)
    assert body.count('<main class="wrap" id="app" tabindex="-1"></main>') == 1, "app container changed"
    region = json.loads(region_p.read_text())
    urls = []
    for path, c, obj in pages(region):
        title, desc = page_meta(path, c, obj, {p["id"]: p for p in c["people"]} if c else None)
        url = SITE + path
        doc = head_(title, desc, url) + body.replace('<main class="wrap" id="app" tabindex="-1"></main>',
                                                            f'<main class="wrap" id="app" tabindex="-1">{render(path, c, obj)}</main>') + "\n</body>\n</html>\n"
        f = out / ("index.html" if path == "/" else path.lstrip("/") + ".html")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(doc)
        urls.append(url)
    # Any other address (a source page, an old link) still gets the app, which then shows the right page.
    fallback = head_(*DEFAULT, SITE + "/") + body + "\n</body>\n</html>\n"
    (out / "app.html").write_text(fallback.replace(f'<link rel="canonical" href="{SITE}/">', '<meta name="robots" content="noindex">'))
    (out / "favicon.svg").write_text(FAVICON)
    (out / "data").mkdir()
    if region_p.exists():
        shutil.copy(region_p, out / "data" / "glassballot.json")
    shutil.copytree(ROOT / "site" / "c", out / "data" / "c")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{html.escape(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    (out / "_headers").write_text(
        "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n  X-Frame-Options: SAMEORIGIN\n  Cache-Control: public, max-age=300\n\n"
        "/assets/app-*\n  Cache-Control: public, max-age=31536000, immutable\n\n"
        "/data/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=300\n")
    # Old #/ links all point at the home page, so they keep working; the app moves them to the real path.
    (out / "_redirects").write_text("/*  /app.html  200\n")
    og = ROOT / "site" / "og.png"
    if og.exists():
        shutil.copy(og, out / "og.png")  # rendered once; the nightly job doesn't need a browser
    else:
        (out / "og.html").write_text(OG_HTML)
    return out


if __name__ == "__main__":
    d = build_dist()
    print("Built", d, sum(1 for _ in d.rglob("*.html")), "pages")
