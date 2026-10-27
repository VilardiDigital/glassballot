"""Find the Nov 3, 2026 general election on counties that use Clarity Elections results sites (Pinellas).

We read only the county's own election list (the same elections.json its results home page reads),
one request per county. We never scan ids: Clarity sites block that. Once the county posts the general,
its id goes into the county's entry in data/enr_ids.json as "general". An id can also be set there by hand.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "GlassBallot/1.0 (+https://glassballot.org; nonpartisan voter guide)"}


def fetch(url: str):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def find_general(elections) -> int | None:
    """Pick the Nov 3, 2026 election out of a Clarity elections.json list, whatever its field names are."""
    for e in elections if isinstance(elections, list) else []:
        if not isinstance(e, dict):
            continue
        text = " ".join(str(v) for v in e.values())
        dated = re.search(r"\b(11/0?3/2026|2026-11-03|November 3, 2026)\b", text, re.I)
        named = re.search(r"2026", text) and re.search(r"general", text, re.I) and not re.search(r"primary", text, re.I)
        if dated or named:
            for k in ("EID", "eid", "ElectionID", "electionId", "electionid", "id", "ID", "Id"):
                if str(e.get(k, "")).isdigit():
                    return int(e[k])
            m = re.search(r"/(\d{5,7})/", text)
            if m:
                return int(m.group(1))
    return None


def main():
    f = ROOT / "data" / "enr_ids.json"
    ids = json.loads(f.read_text())
    for county, e in ids.items():
        if e.get("vendor") != "clarity" or e.get("general"):
            continue
        t = fetch(f"{e['base']}/elections.json")
        try:
            g = find_general(json.loads(t)) if t else None
        except ValueError:
            g = None
        if g:
            e["general"] = g
            e.setdefault("all", []).append([g, "2026 General Election", "11/3/2026"])
        print(county, "general:", e.get("general") or "not posted yet")
    f.write_text(json.dumps(ids, indent=1))


if __name__ == "__main__":
    main()
