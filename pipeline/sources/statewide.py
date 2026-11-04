"""Election night results for statewide races and amendments.

Source: Florida Election Watch (floridaelectionwatch.gov), the Florida Department of State's official
unofficial-results site. We copy exactly what it shows: each choice's votes and percent, and how
many counties have every precinct reported. We never call a race ourselves. A race is only shown as
decided when every county has reported every precinct AND, for amendments, the 60% line can no longer
be crossed by ballots still out; otherwise we show who leads. Calls by news organizations are kept
in data/statewide_calls.json by a person, each with its source, and shown with that attribution.

    python -m pipeline.sources.statewide          # pull and write data/results/statewide.json
    python -m pipeline.sources.statewide --dir data/fewatch_raw   # parse saved pages (testing)
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://floridaelectionwatch.gov"
PAGES = {
    "gov": "StateOffices/Governor",
    "ag": "StateOffices/AttorneyGeneral",
    "cfo": "StateOffices/ChiefFinancialOfficer",
    "agr": "StateOffices/CommissionerOfAgriculture",
    "uss": "FederalOffices/USSenator",
    "amendments": "Amendments",
    "scotus": "JudicialOffices/SupremeCourt",
    "status": "CountyReportingStatus",
}
PARTIES = {"REP", "DEM", "NPA", "LPF", "WRI", "GRE", "IND", "CPF", "ECO", "PSL", "REF", "NON"}


def _num(s: str) -> float:
    s = (s or "").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def lines(page: str) -> list[str]:
    b = page[page.find("<body"):] if "<body" in page else page
    b = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", b)
    out = [re.sub(r"\s+", " ", x).strip() for x in html.unescape(re.sub(r"<[^>]+>", "\n", b)).split("\n")]
    out = [x for x in out if x]
    # Skip the site's menu: content starts after the last menu item ("Downloads").
    if "Downloads" in out:
        out = out[len(out) - out[::-1].index("Downloads"):]
    if "Florida Department of State" in out:
        out = out[:out.index("Florida Department of State")]
    return out


def contests(page: str) -> list[dict]:
    """Every contest on an Election Watch results page, in page order."""
    L = lines(page)
    found, i = [], 0
    while i < len(L):
        if L[i] in ("Votes Received",):
            # Work back to the contest's name: the line before "Contest Results by County" / "Nonpartisan" / "General".
            j = i - 1
            while j > 0 and L[j] in ("Candidate", "Party", "Ballot Choice", "Compare State to County", "Contest Results by County", "General", "Nonpartisan"):
                j -= 1
            name = L[j]
            number = None
            k = j
            while k > max(0, j - 8):
                if re.match(r"Amendment No\. ?\d+", L[k]):
                    number = L[k]
                    break
                k -= 1
            choices, i = [], i + 1
            while i < len(L) and not L[i].startswith("Total") and L[i] != "Votes Received" and not L[i].startswith("Amendments require"):
                nm = L[i]
                party = None
                if i + 1 < len(L) and L[i + 1] in PARTIES:
                    party, i = L[i + 1], i + 1
                if i + 2 < len(L) and re.fullmatch(r"[\d,]+", L[i + 1]) and re.fullmatch(r"[\d.]+%", L[i + 2]):
                    choices.append({"name": nm, "party": party, "votes": int(_num(L[i + 1])), "pct": _num(L[i + 2])})
                    i += 3
                else:
                    i += 1
            threshold = 60 if (i < len(L) and L[i].startswith("Amendments require")) or number else None
            while i < len(L) and not L[i].startswith("Total") and L[i] != "Votes Received":
                i += 1
            total = int(_num(L[i].replace("Total", ""))) if i < len(L) and L[i].startswith("Total") else sum(c["votes"] for c in choices)
            found.append({"name": name, "number": number, "choices": choices, "total": total, "threshold": threshold})
        i += 1
    return found


def reporting(page: str) -> dict:
    """How many counties have every precinct reported (from the County Reporting Status page)."""
    L = lines(page)
    names = json.loads((ROOT / "data" / "counties.json").read_text())["counties"]
    county_names = {c["name"].replace(" County", "") if isinstance(c, dict) and c.get("name") else k for k, c in names.items()}
    pcts = []
    for i, x in enumerate(L):
        if x in county_names or x in ("Miami-Dade", "St. Johns", "St. Lucie", "Indian River", "Palm Beach", "Santa Rosa", "DeSoto", "Desoto"):
            row = L[i + 1:i + 6]
            p = [v for v in row if v.endswith("%")]
            if len(p) >= 2:
                pcts.append((x, _num(p[1])))
    seen = {}
    for n, p in pcts:
        seen.setdefault(n, p)
    return {"counties": len(seen), "complete": sum(1 for p in seen.values() if p >= 100), "byCounty": seen}


def build(pages: dict[str, str]) -> dict:
    out = {"source": BASE, "races": {}, "measures": [], "retention": []}
    for key in ("gov", "ag", "cfo", "agr", "uss"):
        if pages.get(key):
            cs = contests(pages[key])
            if cs:
                out["races"][key] = {**cs[0], "url": f"{BASE}/{PAGES[key]}"}
    if pages.get("amendments"):
        for c in contests(pages["amendments"]):
            out["measures"].append({**c, "url": f"{BASE}/{PAGES['amendments']}"})
    if pages.get("scotus"):
        for c in contests(pages["scotus"]):
            out["retention"].append({**c, "url": f"{BASE}/{PAGES['scotus']}"})
    if pages.get("status"):
        out["reporting"] = reporting(pages["status"])
    return out


def pull() -> str:
    from ..refresh import get
    pages = {}
    errs = []
    for k, p in PAGES.items():
        try:
            pages[k] = get(f"{BASE}/{p}", as_json=False)
        except Exception as e:
            errs.append(f"{k}: {e}")
    res = build(pages)
    if not res["races"] and not res["measures"]:
        return "statewide: nothing parsed, keeping last good file. " + "; ".join(errs)
    res["pulledAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = ROOT / "data" / "results"
    out.mkdir(exist_ok=True)
    (out / "statewide.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    rep = res.get("reporting", {})
    return f"statewide: {len(res['races'])} races, {len(res['measures'])} amendments, {rep.get('complete', '?')}/{rep.get('counties', '?')} counties fully reported" + ("; " + "; ".join(errs) if errs else "")


def _last(n: str) -> str:
    w = re.sub(r'"[^"]*"|\b(Jr|Sr|II|III|IV)\b\.?', " ", n).replace(",", " ").split()
    return w[-1].lower() if w else ""


def _match(choice: str, name: str) -> bool:
    """Does a results line ("Byron Donalds and Bryan Avila") belong to this candidate ("Byron Donalds")?"""
    head = choice.split(" and ")[0]
    return bool(name) and _last(head) == _last(name)


def _status(rep: dict) -> str:
    return "allin" if rep and rep.get("counties") == 67 and rep.get("complete") == 67 else "counting"


def merge() -> dict | None:
    """Everything the site shows for statewide races and amendments: who is running and what they say they
    stand for (data/statewide_2026.json), the live count (data/results/statewide.json), and any race call by a
    named outlet or certification (data/statewide_calls.json, kept by a person, each with a link)."""
    rp, lp, cp = ROOT / "data" / "statewide_2026.json", ROOT / "data" / "results" / "statewide.json", ROOT / "data" / "statewide_calls.json"
    research = json.loads(rp.read_text()) if rp.exists() else {}
    live = json.loads(lp.read_text()) if lp.exists() else {}
    calls = json.loads(cp.read_text()) if cp.exists() else {}
    if not research and not live:
        return None
    rep = live.get("reporting", {})
    status = _status(rep)
    sources = dict(research.get("sources", {}))
    if live:
        sources["fewatch-2026g"] = {"title": "Florida Election Watch: 2026 General Election, unofficial results", "url": live.get("source", BASE),
                                    "publisher": "Florida Department of State, Division of Elections", "tier": 1, "accessed": live.get("pulledAt", "")[:10]}
    races = []
    for r in research.get("races", []) or [{"id": k, "office": v["name"], "candidates": []} for k, v in live.get("races", {}).items()]:
        res = live.get("races", {}).get(r["id"])
        cands = [dict(c) for c in r.get("candidates", [])]
        if res:
            for ch in res["choices"]:
                c = next((c for c in cands if _match(ch["name"], c.get("name", ""))), None)
                if not c:
                    c = {"id": re.sub(r"[^a-z]", "", _last(ch["name"].split(" and ")[0])), "name": ch["name"].split(" and ")[0], "party": ch.get("party"),
                         "runningMate": ch["name"].split(" and ")[1] if " and " in ch["name"] else "", "positions": []}
                    cands.append(c)
                c["votes"], c["pct"] = ch["votes"], ch["pct"]
            cands.sort(key=lambda c: -c.get("votes", 0))
        call = calls.get(r["id"])
        winner = None
        if call:
            winner = next((c["id"] for c in cands if _match(call.get("winner", ""), c["name"]) or call.get("winner") == c.get("id")), None)
        races.append({**r, "candidates": cands, "total": res["total"] if res else 0, "url": res["url"] if res else None,
                      "status": (call.get("kind", "called") if call and winner else status) if res else "nocount",
                      "leader": cands[0]["id"] if res and cands and cands[0].get("votes") else None,
                      "winner": winner, "call": call if winner else None})
    measures = []
    lm = {re.sub(r"\D", "", m.get("number") or ""): m for m in live.get("measures", [])}
    for m in research.get("measures", []) or [{"id": "a" + k, "number": v.get("number"), "title": v["name"]} for k, v in lm.items()]:
        res = lm.get(re.sub(r"\D", "", m.get("number") or ""))
        out = {**m}
        if res:
            yes = next((c for c in res["choices"] if c["name"].lower().startswith("yes")), None)
            no = next((c for c in res["choices"] if c["name"].lower().startswith("no")), None)
            out.update({"yes": yes["votes"] if yes else 0, "no": no["votes"] if no else 0, "yesPct": yes["pct"] if yes else 0.0,
                        "noPct": no["pct"] if no else 0.0, "total": res["total"], "url": res["url"], "threshold": m.get("threshold") or res.get("threshold") or 60})
        call = calls.get(m["id"])
        out["status"] = (call.get("kind", "called") if call else status) if res else "nocount"
        out["outcome"] = call.get("outcome") if call else None
        out["call"] = call
        measures.append(out)
    retention = [{"question": c["name"], "yesPct": next((x["pct"] for x in c["choices"] if x["name"].lower().startswith("yes")), 0.0),
                  "noPct": next((x["pct"] for x in c["choices"] if x["name"].lower().startswith("no")), 0.0), "total": c["total"], "url": c["url"]}
                 for c in live.get("retention", [])]
    return {"election": "2026-11-03", "updated": live.get("pulledAt"), "status": status,
            "reporting": {"counties": rep.get("counties"), "complete": rep.get("complete")},
            "races": races, "measures": measures, "retention": retention, "sources": sources}


def main(argv):
    if argv[:1] == ["--merge"]:
        print(json.dumps(merge(), indent=1, ensure_ascii=False)[:8000])
        return
    if argv[:1] == ["--dir"]:
        d = Path(argv[1])
        names = {"gov": "StateOffices_Governor", "ag": "StateOffices_AttorneyGeneral", "cfo": "StateOffices_ChiefFinancialOfficer",
                 "agr": "StateOffices_CommissionerOfAgriculture", "uss": "FederalOffices_USSenator", "amendments": "Amendments",
                 "scotus": "JudicialOffices_SupremeCourt", "status": "CountyReportingStatus"}
        pages = {k: (d / f"{v}.html").read_text() for k, v in names.items() if (d / f"{v}.html").exists()}
        print(json.dumps(build(pages), indent=1, ensure_ascii=False)[:6000])
        return
    print(pull())


if __name__ == "__main__":
    main(sys.argv[1:])
