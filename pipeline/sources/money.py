"""Merge campaign finance, donor-to-vote connections and disclosure filings into the seed.

Inputs come from data/money_pinellas.json, built from:
  - Pinellas Supervisor of Elections itemized reports (VoterFocus export)
  - Pinellas Legistar roll calls (to find donors named in agenda items)
  - Florida Division of Corporations (Sunbiz) for company links
  - Florida Commission on Ethics filing search (Form 6 dates)
"""

from __future__ import annotations

import copy
from datetime import date

SOE, LG, SUNBIZ, ETHICS = "soe-cf", "legistar", "sunbiz", "ethics-efdms"


def _usd(n: float) -> str:
    return f"${n:,.0f}"


def _fmt(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return date(y, m, d).strftime("%b %-d, %Y")


def merge(seed: dict, money: dict) -> dict:
    seed = copy.deepcopy(seed)
    seed["sources"].update(money["sources"])
    people = {p["id"]: p for p in seed["people"]}
    names = {pid: p["name"] for pid, p in people.items()}

    # Campaign money: the county's own reports replace third-party snapshots.
    for pid, c in money["campaigns"].items():
        p = people.get(pid)
        if not p:
            continue
        cl = p.setdefault("claims", {})
        cl["raised"] = [{"value": f"{_usd(c['total'])} for the {c['cycle']} campaign (reports through {_fmt(c['last'])})", "source": SOE}]
        where = f"{c['pctPinellas']}% from inside Pinellas, {c['pctOutOfState']}% from out of state, {c['donors']} donors"
        cl["moneyWhere"] = [{"value": where, "source": SOE}]
        own = []
        if c.get("self"):
            own.append(f"{_usd(c['self'])} from the candidate" + (f" (including {_usd(c['loans'])} in loans)" if c.get("loans") else ""))
        if c.get("inKind"):
            own.append(f"{_usd(c['inKind'])} in goods and services (in-kind)")
        if own:
            cl["moneyOwn"] = [{"value": "; ".join(own), "source": SOE}]
        tops = [f"{n}: {_usd(a)}" for n, a in c.get("topOrgs", [])[:6]]
        if c.get("realtors"):
            tops.append(f"Florida Realtors' {c['realtors']['committees']} political committees combined: {_usd(c['realtors']['amount'])} (grouped by name)")
        cl["topOrgDonors"] = [{"value": tops, "source": SOE}]
        p["money"] = {k: c[k] for k in ("cycle", "total", "inKind", "loans", "self", "donors", "pctPinellas", "pctOutOfState")}

    # Gifts between officials.
    for g in money.get("giftsBetweenOfficials", []):
        line_to = f"Gave {_usd(g['amount'])} to {names.get(g['to'], g['to'])}'s campaign ({g['dates']}). {g['match']}."
        line_from = f"Got {_usd(g['amount'])} from {names.get(g['from'], g['from'])} ({g['dates']}). {g['match']}."
        for pid, line in ((g["from"], line_to), (g["to"], line_from)):
            if pid in people:
                people[pid].setdefault("giftLines", []).append(line)
    for p in people.values():
        if p.get("giftLines"):
            p["claims"]["officialGifts"] = [{"value": p.pop("giftLines"), "source": SOE}]

    # Donor-to-vote connections.
    flagged: dict[str, float] = {}
    vote_notes: dict[int, list] = {}
    for cnx in money.get("connections", []):
        pid = cnx["person"]
        p = people.get(pid)
        if not p:
            continue
        label = {"named": "verified", "named-unconfirmed": "unverified", "industry": "single",
                 "linked-by-records": "single", "own-business": "single"}[cnx["kind"]]
        srcs = {"named": [SOE, LG], "named-unconfirmed": [SOE, LG], "industry": [SOE, LG],
                "linked-by-records": [SOE, SUNBIZ, LG], "own-business": [SOE]}[cnx["kind"]]
        kind_text = {"named": "Donor named in a county vote", "named-unconfirmed": "Possible donor link to a county vote",
                     "industry": "Donor's industry regulated by a county vote", "linked-by-records": "Donor linked by state business records to a county contractor",
                     "own-business": "Their own business gave to their campaign"}[cnx["kind"]]
        votes = [f"{v['how'].upper() if v['how'] in ('yes','no') else v['how'].capitalize()} on {_fmt(v['date'])}: {v['title']} ({v['days']} days {'after' if v['date'] < cnx['date'] else 'before'} the gift)" for v in cnx["votes"]]
        p.setdefault("connections", []).append({
            "kind": kind_text, "label": label, "sources": srcs, "inWindow": cnx["inWindow"],
            "donor": cnx["donor"], "amount": cnx["amount"], "date": cnx["date"], "note": cnx.get("note"), "votes": votes,
        })
        if cnx["kind"] == "named" and cnx["inWindow"]:
            flagged[pid] = flagged.get(pid, 0) + cnx["amount"]
        for v in cnx["votes"]:
            vote_notes.setdefault(v["item"], []).append({
                "text": f"{names.get(pid)} received {_usd(cnx['amount'])} from {cnx['donor']} on {_fmt(cnx['date'])}, {v['days']} days {'after' if v['date'] < cnx['date'] else 'before'} this vote, and voted {v['how']}.",
                "note": cnx.get("note"), "label": label, "sources": srcs})

    for v in seed["votes"]:
        item = None
        if v["id"].startswith("lg-"):
            item = int(v["id"][3:])
        if item in vote_notes:
            v["moneyNotes"] = vote_notes[item]

    # Disclosure filings and the openness / money timing parts of the score.
    for pid, fl in money.get("filings", {}).items():
        p = people.get(pid)
        if not p:
            continue
        lines, recs = [], []
        for f in fl:
            due = date(f["year"] + 1, 7, 1)
            filed = date.fromisoformat(f["filed"])
            on_time = filed <= due
            late = ""
            if not on_time:
                late = (", after the July 1 due date but before the September 1 cutoff" if filed <= date(f["year"] + 1, 9, 1)
                        else ", after the September 1 cutoff, when automatic $25-a-day fines apply")
            lines.append(f"Form {f['form']} for {f['year']}: filed {_fmt(f['filed'])}" + late)
            if not f["form"].startswith("6X"):
                recs.append({"on_time": on_time, "complete": None})
        p["claims"]["filings"] = [{"value": lines, "source": ETHICS}]
        if any("cutoff" in l for l in lines):
            p["claims"]["filings"].append({"value": lines, "source": "flbar-disclosure"})
        p.setdefault("record", {})["filings"] = recs

    for pid, c in money["campaigns"].items():
        p = people.get(pid)
        if p and p.get("status") == "incumbent" and p.get("office") == "County Commissioner":
            total = c["total"] - c.get("self", 0)
            p.setdefault("record", {})["money_timing_value"] = round(100 - 100 * flagged.get(pid, 0) / total, 1) if total else None

    seed["manualProblems"] = seed.get("manualProblems", []) + money.get("problems", [])
    # The county finance search does cover 2022 to 2026 (the export is per cycle), so retire that gap.
    seed["manualProblems"] = [m for m in seed["manualProblems"] if m["id"] != "soe-finance-years"]
    return seed
