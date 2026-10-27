"""Nightly refresh from official sources. Runs on a schedule (GitHub Actions), no browser needed.

    python -m pipeline.refresh            # pull, rebuild, log what changed
    python -m pipeline.refresh --offline  # rebuild and diff only (for testing)

What it pulls on its own, every run:
  - Legistar roll calls (Pinellas, Hernando): every vote, attendance, new split votes
  - VoterFocus campaign totals (Pinellas, Pasco, Hillsborough, Hernando): money raised, candidate status

What it never does on its own:
  - Write plain-English summaries. A new split vote goes up with the official title and
    "Plain-English summary pending review" until a person writes and checks the summary.
  - Add news reports, campaign claims or social links. Those need a human with a source.

Every run writes data/changes/<date>.json listing each fact that changed (before, after,
source), and the site shows it on the "What changed" page. If a pull fails, the last good
data stays up and the failure is logged; nothing is silently dropped.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "GlassBallot/1.0 (+https://glassballot.org; nonpartisan voter guide)", "Accept": "application/json"}

LEGISTAR = {  # county: (client, body ids, since)
    "pinellas": ("pinellas", [213, 212], "2024-11-19"),
    "hernando": ("hernandocountyfl", [138, 235], "2024-11-19"),
}
VOTERFOCUS = {"pasco": 38, "hillsborough": 27, "hernando": 32}  # 2026 cycle ids. Pinellas money comes from the itemized exports in data/money_pinellas.json


def get(url: str, as_json: bool = True, tries: int = 4):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                b = r.read().decode("utf-8", "replace")
                return json.loads(b) if as_json else b
        except Exception:
            if a == tries - 1:
                raise
            time.sleep(1.5 * (a + 1))


def _pid(name: str, people: list[dict]) -> str | None:
    last = name.replace(" Jr.", "").split()[-1].lower()
    hits = [p for p in people if p["name"].replace(" Jr.", "").split()[-1].lower() == last and "Commission" in p.get("office", "")]
    if len(hits) > 1:
        hits = [p for p in hits if p["name"].split()[0].lower() == name.split()[0].lower()] or hits
    return hits[0]["id"] if len(hits) == 1 else None


def refresh_legistar(county: str, today: str) -> str:
    client, bodies, since = LEGISTAR[county]
    seed = json.loads((ROOT / "data" / f"seed_{county}.json").read_text())
    sp = ROOT / "data" / f"legistar_{county}_summary.json"
    old = json.loads(sp.read_text()) if sp.exists() else {}
    curated = {s["item"]: s for s in old.get("splitVotes", [])}
    base = f"https://webapi.legistar.com/v1/{client}"
    flt = " or ".join(f"EventBodyId eq {b}" for b in bodies)
    q = urllib.parse.quote(f"({flt}) and EventDate ge datetime'{since}' and EventDate le datetime'{today}'")
    events = get(f"{base}/events?$filter={q}&$orderby=EventDate%20desc")
    with cf.ThreadPoolExecutor(6) as ex:
        items = list(ex.map(lambda e: (e, get(f"{base}/events/{e['EventId']}/eventitems?AgendaNote=1&MinutesNote=1")), events))
    acted = [(e, i) for e, its in items for i in its if i.get("EventItemPassedFlag") is not None or i.get("EventItemActionName")]
    with cf.ThreadPoolExecutor(8) as ex:
        votes = list(ex.map(lambda ei: get(f"{base}/eventitems/{ei[1]['EventItemId']}/votes"), acted))

    people = seed["people"]
    stats, att, split = {}, {}, []
    by_event: dict[int, set] = {}
    for (e, i), vs in zip(acted, votes):
        if not vs:
            continue
        rec = {"yes": [], "no": [], "absent": [], "abstain": []}
        for v in vs:
            pid = _pid(v["VotePersonName"], people)
            val = (v.get("VoteValueName") or "").lower()
            side = "yes" if val in ("aye", "yes", "yea") else "no" if val in ("nay", "no") else "abstain" if "recus" in val or "abstain" in val else "absent"
            if not pid:
                continue
            s = stats.setdefault(pid, {"aye": 0, "nay": 0, "absent": 0, "abstain": 0, "meetingsHeld": 0, "meetingsMissed": 0})
            s[{"yes": "aye", "no": "nay"}.get(side, side)] += 1
            rec[side].append(pid)
            a = att.setdefault(pid, {})
            a.setdefault(e["EventId"], False)
            if side != "absent":
                a[e["EventId"]] = True
        by_event.setdefault(e["EventId"], set())
        if rec["yes"] and rec["no"]:
            it = i["EventItemId"]
            c = curated.get(it, {})
            n_y, n_n = len(rec["yes"]), len(rec["no"])
            # A motion carries when more members vote yes than no. The county's "passed" flag is not
            # reliable on motions to deny, so a reviewed result is never overwritten.
            passed = n_y > n_n
            split.append({
                "item": it, "ev": e["EventId"], "date": e["EventDate"][:10], "file": i.get("EventItemMatterFile"),
                "topic": c.get("topic", "other"), "result": c.get("result") or f"Motion {'passed' if passed else 'failed'} {n_y} to {n_n}",
                "yes": sorted(rec["yes"]), "no": sorted(rec["no"]), **({"absent": rec["absent"]} if rec["absent"] else {}),
                "mover": c.get("mover") or _pid(i.get("EventItemMover") or "x", people), "seconder": c.get("seconder") or _pid(i.get("EventItemSeconder") or "x", people),
                "officialTitle": i.get("EventItemTitle") or c.get("officialTitle") or "",
                "motion": c.get("motion") or (i.get("EventItemActionText") or "").strip() or None,
                "headline": c.get("headline") or (i.get("EventItemTitle") or "Untitled item")[:120],
                "inShort": c.get("inShort"), "needsReview": not c.get("inShort"),
                # The clerk's minutes for this item. On public hearings they usually record who spoke and on which side.
                "minutesNote": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", i.get("EventItemMinutesNote") or ""))).strip() or c.get("minutesNote"),
            })
    for pid, a in att.items():
        stats[pid]["meetingsHeld"] = len(a)
        stats[pid]["meetingsMissed"] = sum(1 for v in a.values() if not v)
    # Keep only split votes a person has reviewed, plus new ones flagged for review.
    keep = [s for s in split if s["item"] in curated or s["date"] > max((c["date"] for c in curated.values()), default="")]
    out = {**old, "pulledAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "totals": {"meetings": len(events), "meetingsWithRollCalls": len({e["EventId"] for (e, i), vs in zip(acted, votes) if vs}),
                      "items": len(acted), "rollCalls": sum(1 for v in votes if v), "splitRollCalls": len(split)},
           "stats": stats, "splitVotes": keep,
           "meetingUrls": {**old.get("meetingUrls", {}), **{str(e["EventId"]): e.get("EventInSiteURL") for e in events if e.get("EventInSiteURL")}}}
    sp.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    new = [s for s in keep if s["item"] not in curated]
    return f"{county} Legistar: {out['totals']['rollCalls']} roll calls, {len(new)} new split votes awaiting review"


def refresh_voterfocus(county: str, el: int | None, today: str) -> list[str]:
    base = "https://www.voterfocus.com/CampaignFinance/candidate_pr.php"
    if el is None:
        page = get(f"{base}?c={county}", as_json=False)
        m = re.search(r"<option value=['\"](\d+)['\"][^>]*>\s*2026 Candidate", page, re.I)
        if not m:
            raise RuntimeError("2026 cycle not listed")
        el = int(m.group(1))
    page = get(f"{base}?c={county}&el={el}", as_json=False)
    rows = []
    for g in re.split(r'class="col-xs-12 officegroup"', page)[1:]:
        om = re.search(r'officename">\s*Office:\s*(.*?)</div>', g, re.S)
        office = html.unescape(om.group(1)).strip() if om else ""
        if not re.search(r"commission|school", office, re.I):
            continue
        for a in re.finditer(r'href="[^"]*ca=(\d+)[^"]*">(.*?)</a>', g, re.S):
            text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", a.group(2)))).strip()
            m = re.match(r"(.*?)(?: \((\w+)\))? status \((.*?)\) Contributions monetary \$([\d,.]+) In-Kind in-kind \$([\d,.]+)", text)
            if m and not re.search(r"Did not qualify|Withdrawn", m.group(3)):
                rows.append("|".join([county, str(el), office, m.group(1), m.group(2) or "NON", m.group(3).strip(), m.group(4), m.group(5), a.group(1)]))
    return rows


CONTRIB_CYCLES = {"pinellas": 35, "pasco": 38, "hillsborough": 27, "hernando": 32}


def refresh_contrib(county: str, el: int, today: str) -> str:
    """Itemized contributions for every county commission and school board campaign this cycle.

    Private donors keep their occupation, city, state and ZIP only; we don't store their names or
    street addresses. Businesses, committees and parties keep their names (and a business's street
    address, to spot several companies at one address)."""
    import csv, io
    base = "https://www.voterfocus.com/CampaignFinance"
    page = get(f"{base}/candidate_pr.php?c={county}&el={el}", as_json=False)
    camps = {}
    for g in re.split(r'class="col-xs-12 officegroup"', page)[1:]:
        om = re.search(r'officename">\s*Office:\s*(.*?)</div>', g, re.S)
        office = re.sub(r"\s+", " ", html.unescape(om.group(1))).strip() if om else ""
        if not re.search(r"commission|school", office, re.I):
            continue
        for a in re.finditer(r'href="[^"]*ca=(\d+)[^"]*">(.*?)</a>', g, re.S):
            text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", a.group(2)))).strip()
            m = re.match(r"(.*?)(?: \(\w+\))? status \((.*?)\)", text)
            if not m or re.search(r"Did not qualify|Withdrawn", m.group(2)):
                continue
            ca = a.group(1)
            raw = get(f"{base}/export.php?op=CFINANCE&cand_id={ca}&dhc=0&county={county}", as_json=False)
            rows = []
            for r in csv.DictReader(io.StringIO(raw)):
                if (r.get("Cont/Exp") or "").strip() != "C":
                    continue
                t = (r.get("cont. type") or "").strip()
                try:
                    amt = float(r.get("amount") or 0)
                except ValueError:
                    continue
                row = {"date": (r.get("item date") or "")[:10], "type": t, "amount": amt, "item": (r.get("item type") or "").strip(),
                       "occ": re.sub(r"<br>|\s+", " ", r.get("occupation") or "").strip(),
                       "city": (r.get("city") or "").strip(), "state": (r.get("state") or "").strip(), "zip": (r.get("zip") or "")[:5]}
                if t != "I":
                    row["name"] = re.sub(r"\s+", " ", r.get("name") or "").strip()
                if t == "B":
                    row["addr"] = re.sub(r"\b(ste|suite|unit|#)\b.*$", "", (r.get("address 1") or "").lower()).strip(" .,")
                rows.append(row)
            camps[ca] = {"candidate": m.group(1).strip(), "office": office, "status": m.group(2),
                         "url": f"{base}/candidate_pr.php?op=cv&e={el}&c={county}&ca={ca}&rellevel=4&committee=N", "rows": rows}
            time.sleep(0.4)
    out = ROOT / "data" / "contrib"
    out.mkdir(exist_ok=True)
    (out / f"{county}.json").write_text(json.dumps({"county": county, "cycle": "2026", "el": el, "pulledAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                    "url": f"{base}/candidate_pr.php?c={county}&el={el}", "campaigns": camps}, ensure_ascii=False))
    return f"{county} itemized contributions: {len(camps)} campaigns, {sum(len(c['rows']) for c in camps.values())} gifts"


def snapshot() -> dict:
    p = ROOT / "site" / "region.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    flat = {}
    for k, c in d["counties"].items():
        for pr in c["people"]:
            for f, x in pr["facts"].items():
                flat[f"{k}/{pr['id']}/{f}"] = {"subject": f"{pr['name']}: {f}", "value": x.get("value"), "label": x["label"], "sources": x.get("sources", [])}
        for v in c["votes"]:
            flat[f"{k}/vote/{v['id']}"] = {"subject": f"Vote: {v['headline']}", "value": v["result"].get("value"), "label": v["result"]["label"], "sources": v["result"].get("sources", [])}
    return flat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log, errors = [], []
    before = snapshot()
    if not a.offline:
        for county in LEGISTAR:
            try:
                log.append(refresh_legistar(county, today))
            except Exception as e:
                errors.append(f"{county} Legistar pull failed, kept last good data: {e}")
        rows = []
        for county, el in VOTERFOCUS.items():
            try:
                rows += refresh_voterfocus(county, el, today)
            except Exception as e:
                errors.append(f"{county} campaign finance pull failed, kept last good data: {e}")
        for county, el in CONTRIB_CYCLES.items():
            try:
                log.append(refresh_contrib(county, el, today))
            except Exception as e:
                errors.append(f"{county} itemized contributions pull failed, kept last good data: {e}")
        if rows:
            p = ROOT / "data" / f"voterfocus_totals_{today}.txt"
            p.write_text("\n".join(rows) + "\n")
            from .sources.voterfocus_totals import apply
            apply(p, today)
            log.append(f"Campaign totals: {len(rows)} candidates")
    from .curate import run as curate
    curate()
    from .region import build_region, bake
    data = build_region(today)
    data["region"]["refreshLog"] = log
    data["region"]["refreshErrors"] = errors
    bake(data)
    after = snapshot()
    changes = [{"key": k, "subject": after[k]["subject"], "before": before.get(k, {}).get("value"), "after": after[k]["value"],
                "label": after[k]["label"], "sources": after[k]["sources"]}
               for k in after if k in before and json.dumps(before[k]["value"]) != json.dumps(after[k]["value"])]
    added = [k for k in after if k not in before]
    if changes or added or errors:
        cd = ROOT / "data" / "changes"
        cd.mkdir(exist_ok=True)
        (cd / f"{today}.json").write_text(json.dumps({"date": today, "changed": changes, "added": added, "log": log, "errors": errors}, indent=1, ensure_ascii=False))
    from .dist import build_dist
    build_dist()
    print("\n".join(log + errors) or "No changes")
    print(f"{len(changes)} facts changed, {len(added)} added")


if __name__ == "__main__":
    main()
