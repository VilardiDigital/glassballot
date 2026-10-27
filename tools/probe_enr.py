"""Find each county's Nov 3, 2026 results page on enr.electionsfl.org (VR Systems election night reporting).

Election ids are shared across counties and increase over time, so we scan a range for each county code.
Writes data/enr_ids.json: {county: {"code": "HER", "general": 4106, "primary": 4046}}.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "GlassBallot/1.0 (+https://glassballot.org; nonpartisan voter guide)"}
CODES = {"alachua": "ALA", "baker": "BAK", "bay": "BAY", "bradford": "BRA", "brevard": "BRE", "broward": "BRO", "calhoun": "CAL", "charlotte": "CHA",
 "citrus": "CIT", "clay": "CLA", "collier": "CLL", "columbia": "CLM", "desoto": "DES", "dixie": "DIX", "duval": "DUV", "escambia": "ESC", "flagler": "FLA",
 "franklin": "FRA", "gadsden": "GAD", "gilchrist": "GIL", "glades": "GLA", "gulf": "GUL", "hamilton": "HAM", "hardee": "HAR", "hendry": "HEN", "hernando": "HER",
 "highlands": "HIG", "hillsborough": "HIL", "holmes": "HOL", "indianriver": "IND", "jackson": "JAC", "jefferson": "JEF", "lafayette": "LAF", "lake": "LAK",
 "lee": "LEE", "leon": "LEO", "levy": "LEV", "liberty": "LIB", "madison": "MAD", "manatee": "MAN", "marion": "MRN", "martin": "MRT", "miamidade": "DAD",
 "monroe": "MON", "nassau": "NAS", "okaloosa": "OKA", "okeechobee": "OKE", "orange": "ORA", "osceola": "OSC", "palmbeach": "PAL", "pasco": "PAS",
 "pinellas": "PIN", "polk": "POL", "putnam": "PUT", "stjohns": "STJ", "stlucie": "STL", "santarosa": "SAN", "sarasota": "SAR", "seminole": "SEM",
 "sumter": "SUM", "suwannee": "SUW", "taylor": "TAY", "union": "UNI", "volusia": "VOL", "wakulla": "WAK", "walton": "WAL", "washington": "WAS"}


def head(code: str, i: int):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://enr.electionsfl.org/{code}/{i}/Summary/", headers=UA), timeout=20) as r:
            t = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    n = re.search(r"<h\d[^>]*>\s*([^<]*Election[^<]*)<", t)
    d = re.search(r"Election Date:\s*([\d/]+)", t)
    return (i, n.group(1).strip() if n else "", d.group(1) if d else "")


def scan(item):
    county, code = item
    if code in KNOWN:
        return county, KNOWN[code]
    with cf.ThreadPoolExecutor(12) as ex:
        hits = [h for h in ex.map(lambda i: head(code, i), range(4000, 4420)) if h]
    out = {"code": code, "all": hits}
    for i, name, d in hits:
        if d == "11/3/2026" or "2026 general" in name.lower():
            out["general"] = i
        if d == "8/18/2026" and "primary" in name.lower():
            out["primary"] = i
    return county, out


KNOWN = {}


def main():
    # Keep counties already found; rescan only the rest (their results pages may not be posted yet).
    f = ROOT / "data" / "enr_ids.json"
    old = json.loads(f.read_text()) if f.exists() else {}
    for k, v in old.items():
        if v.get("general"):
            KNOWN[v["code"]] = v
    with cf.ThreadPoolExecutor(6) as ex:
        res = dict(ex.map(scan, CODES.items()))
    (ROOT / "data" / "enr_ids.json").write_text(json.dumps(res, indent=1))
    print(sum(1 for v in res.values() if v.get("general")), "counties with a Nov 3 results page;",
          [k for k, v in res.items() if not v.get("general")], "without")


if __name__ == "__main__":
    main()
