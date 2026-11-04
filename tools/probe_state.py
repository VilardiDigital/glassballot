"""Save raw pages from Florida Election Watch (the state's official election night results site)
so the statewide parser can be written and checked against the real format.

    python tools/probe_state.py
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "fewatch"
BASE = "https://floridaelectionwatch.gov"
UA = {"User-Agent": "GlassBallot/1.0 (+https://glassballot.org; nonpartisan voter guide)"}
PAGES = ["Home", "Downloads", "Amendments", "StateOffices", "StateOffices/Governor", "StateOffices/AttorneyGeneral",
         "StateOffices/ChiefFinancialOfficer", "StateOffices/CommissionerOfAgriculture", "FederalOffices/USSenator",
         "CountyReportingStatus"]


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read().decode("utf-8", "replace"), r.headers.get("Content-Type", "")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = {}
    seen = set()
    for p in PAGES:
        try:
            body, ct = get(f"{BASE}/{p}")
            (OUT / (p.replace("/", "_") + ".html")).write_text(body)
            log[p] = {"bytes": len(body), "type": ct}
            # Note any script or data endpoints the page loads, and fetch them once.
            for u in set(re.findall(r'["\'](/[^"\']*(?:api|json|Json|Get|Data|Download)[^"\']*)["\']', body)):
                if u in seen or len(seen) > 40:
                    continue
                seen.add(u)
                try:
                    b2, ct2 = get(BASE + u)
                    (OUT / ("ep_" + re.sub(r"[^A-Za-z0-9]+", "_", u)[:80])).write_text(b2)
                    log[u] = {"bytes": len(b2), "type": ct2}
                except Exception as e:
                    log[u] = {"error": str(e)}
        except Exception as e:
            log[p] = {"error": str(e)}
    (OUT / "_log.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    sys.exit(main())
