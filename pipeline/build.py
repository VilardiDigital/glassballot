"""Build the data file the Glass Ballot site reads.

    python -m pipeline.build                      # seed facts only
    python -m pipeline.build --legistar data/legistar_pinellas.json
    python -m pipeline.build --html               # also bake data into site/glassballot.html

Every fact in the output has a label (verified, single, unverified,
conflict, unknown) and the ids of the sources behind it.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .normalize import to_claims
from .sources.legistar_summary import merge as merge_summary
from .sources.money import merge as merge_money
from .score import pocket_or_public
from .verify import find_problems, label_fact

ROOT = Path(__file__).resolve().parents[1]

PROFILE_FIELDS = ["party", "inOfficeSince", "term", "leadership", "job", "roles", "pastOffice", "lastElection", "record", "attendance", "conflicts", "filings",
                  "raised", "moneyWhere", "moneyOwn", "topOrgDonors", "officialGifts", "promises", "photo"]
NOT_COUNTED = {"photo"}
ADDITIVE = {"roles"}  # several true things, not competing versions of one  # a headshot is not a fact about the record


def required_fields(p: dict) -> list[str]:
    """Fields every profile of this kind must show, even when we found nothing."""
    req = []
    if not p.get("nonpartisan"):
        req.append("party")
    if p.get("status") == "incumbent":
        req.append("inOfficeSince")
    if p.get("race"):
        req += ["raised", "promises"]
    return req


def build(seed: dict, legistar: dict | None = None, accessed: str | None = None) -> dict:
    reg = seed["sources"]
    lg = to_claims(legistar, seed) if legistar else {"matched": {}, "extra": [], "problems": []}
    all_facts: dict[str, dict] = {}

    people = []
    counted: set[str] = set()  # fact keys that count toward the label totals
    for p in seed["people"]:
        facts = {}
        required = required_fields(p)
        for f in PROFILE_FIELDS:
            cl = p.get("claims", {}).get(f, [])
            if f in ADDITIVE and len(cl) > 1:
                # Different roles from different sources add up; they don't contradict each other.
                vals = []
                for c in cl:
                    for v in (c["value"] if isinstance(c["value"], list) else [c["value"]]):
                        if v not in vals:
                            vals.append(v)
                fact = label_fact([{"value": vals, "source": c["source"]} for c in cl], reg, prefer_official=True)
            else:
                fact = label_fact(cl, reg, prefer_official=True)
            facts[f] = fact
            all_facts[f"{p['id']}.{f}"] = fact
            if f not in NOT_COUNTED and (fact["label"] != "unknown" or f in required):
                counted.add(f"{p['id']}.{f}")
        # Links (official page, campaign site, socials) are a set, not one fact with competing values.
        links, seen = [], set()
        for c in p.get("claims", {}).get("links", []):
            v = c.get("value") or {}
            u = v.get("url", "")
            if u.startswith("https://") and u not in seen:
                seen.add(u)
                links.append({"kind": v.get("kind", "campaign"), "url": u, "source": c.get("source"),
                              "tier": (reg.get(c.get("source")) or {}).get("tier")})
        people.append({k: v for k, v in p.items() if k not in ("claims", "record")} | {"facts": facts, "required": required, "links": links, "_record": p.get("record", {})})

    votes = []
    for v in seed["votes"] + lg["extra"]:
        claims = {k: list(c) for k, c in v.get("claims", {}).items()}
        m = lg["matched"].get(v["id"])
        if m:
            if m["result"]:
                claims.setdefault("result", []).append(m["result"])
            claims.setdefault("roll", []).append(m["roll"])
        result = label_fact(claims.get("result", []), reg)
        roll = label_fact(claims.get("roll", []), reg)
        all_facts[f"vote:{v['id']}.result"] = result
        all_facts[f"vote:{v['id']}.roll"] = roll
        counted.update({f"vote:{v['id']}.result", f"vote:{v['id']}.roll"})
        facts = [{"text": f["text"], **label_fact(f.get("claims", []), reg)} for f in v.get("facts", [])]
        for i, f in enumerate(facts):
            all_facts[f"vote:{v['id']}.fact{i}"] = f
            counted.add(f"vote:{v['id']}.fact{i}")
        votes.append({k: val for k, val in v.items() if k not in ("claims", "facts", "legistarMatch")} | {
            "result": result, "roll": roll, "facts": facts,
            "officialTitle": (m or {}).get("officialTitle") or v.get("officialTitle"),
            "sourceUrl": (m or {}).get("url") or v.get("sourceUrl"),
        })
    votes.sort(key=lambda x: x.get("date") or x.get("dateNote", "")[-4:] + "-12-31", reverse=True)

    # Each person's own votes, for their page.
    for p in people:
        mine = []
        for v in votes:
            r = v["roll"].get("value") or (v["roll"].get("versions") or [{}])[0].get("value") or {}
            extra = v.get("rollExtra") or {}
            for side in ("yes", "no", "absent", "abstain"):
                if p["id"] in (r.get(side) or []) or p["id"] in (extra.get(side) or []):
                    mine.append({"vote": v["id"], "how": side})
                    break
        p["votes"] = mine
        # Pocket or Public needs disclosures, money and recusal records the seed doesn't have yet.
        rec = p.pop("_record", {}) or {}
        # Conflict handling waits for Form 1 / Form 6 disclosures: a recusal list alone
        # shows only the conflicts someone declared, not the ones they didn't.
        p["score"] = pocket_or_public({
            "scored_votes": rec.get("scored_votes", len(mine)),
            "meetings_held": rec.get("meetings_held", 0),
            "meetings_attended": rec.get("meetings_attended", 0),
            "filings": rec.get("filings", []),
            "money_timing_value": rec.get("money_timing_value"),
        })
        if "aye" in rec:
            p["tally"] = {k: rec[k] for k in ("aye", "nay", "absent", "abstain")}

    names = {p["id"]: p["name"] for p in seed["people"]} | {f"vote:{v['id']}": v["headline"] for v in votes}
    problems = find_problems(all_facts, names) + lg["problems"] + seed.get("manualProblems", [])

    counts = {lab: 0 for lab in ("verified", "single", "unverified", "conflict", "unknown")}
    for k in counted:
        counts[all_facts[k]["label"]] += 1

    return {
        "county": seed["county"],
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "accessed": accessed or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "legistarLoaded": bool(legistar) or bool(seed.get("legistarTotals")),
        "legistarTotals": seed.get("legistarTotals"),
        "legistarScope": seed.get("legistarScope"),
        "legistarPulledAt": seed.get("legistarPulledAt"),
        "sources": reg,
        "people": people,
        "races": seed["races"],
        "votes": votes,
        "topics": seed["topics"],
        "problems": problems,
        "labelCounts": counts,
    }


def bake_html(data: dict) -> Path:
    tpl = (ROOT / "site" / "template.html").read_text()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out = ROOT / "site" / "glassballot.html"
    out.write_text(tpl.replace("/*__DATA__*/null", blob))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=str(ROOT / "data" / "seed_pinellas.json"))
    ap.add_argument("--legistar", default=None)
    ap.add_argument("--out", default=str(ROOT / "site" / "data.json"))
    ap.add_argument("--legistar-summary", default=None, help="Summary pulled in the browser (data/legistar_pinellas_summary.json)")
    ap.add_argument("--money", default=None, help="Campaign finance and connections (data/money_pinellas.json)")
    ap.add_argument("--accessed", default=None, help="Date the seed sources were read (YYYY-MM-DD)")
    ap.add_argument("--html", action="store_true")
    a = ap.parse_args()
    seed = json.loads(Path(a.seed).read_text())
    lg = json.loads(Path(a.legistar).read_text()) if a.legistar else None
    if a.legistar_summary:
        seed = merge_summary(seed, json.loads(Path(a.legistar_summary).read_text()))
    if a.money:
        seed = merge_money(seed, json.loads(Path(a.money).read_text()))
    data = build(seed, lg, a.accessed)
    Path(a.out).write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"{len(data['people'])} people, {len(data['votes'])} votes, {len(data['problems'])} record problems")
    print("Labels:", ", ".join(f"{k} {v}" for k, v in data["labelCounts"].items()))
    if a.html:
        print("Site:", bake_html(data))


if __name__ == "__main__":
    main()
