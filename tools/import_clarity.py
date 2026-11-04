"""Save a Clarity results summary that was read in a browser, when the county's site blocks automated requests.

Pinellas's results site (enr.votepinellas.gov) answers scripts on data-center networks, like GitHub's, with an empty
"202" challenge. We don't try to get around that. Instead, someone opens the county's own summary file in a browser
({base}/{eid}/{version}/json/sum.json), saves it, and runs:

    python -m tools.import_clarity pinellas path/to/sum.json [--certified]

The file is written in the same shape pipeline.sources.results.pull() writes, with the county's own URL as the source.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]):
    from pipeline.sources.results import parse_clarity, _key
    county, path = argv[0], Path(argv[1])
    e = json.loads((ROOT / "data" / "enr_ids.json").read_text())[county]
    res = parse_clarity(json.loads(path.read_text()))
    if "--certified" in argv or e.get("certified"):
        res["status"] = "official"
    keep = [r for r in res["races"] if _key(r["office"])]
    out = ROOT / "data" / "results" / f"{county}.json"
    url = f"{e['base']}/{e['general']}/"
    out.write_text(json.dumps({"county": county, "url": url, "pulledAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                               "status": res["status"], "updated": None, "races": keep, "via": "browser",
                               "all": [r for r in res["races"] if r["candidates"]]}, indent=1, ensure_ascii=False))
    print(f"{county}: {len(keep)} local races, {len(res['races'])} contests ({res['status']}) -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
