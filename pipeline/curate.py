"""Editorial merges, logged in public (data/curation_log.json).

Each entry rewrites claims that say the same thing in different words, or drops an older
undated snapshot when a dated newer one exists. Nothing here changes a fact's meaning;
the log shows every before and after.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (county, person, field, action, value)  action: "same" sets every claim to value; "drop" removes claims from listed sources
EDITS = [
 ("hillsborough","hagan","term","same","Re-elected 2024; seat not on the 2026 ballot"),
 ("hillsborough","miller","inOfficeSince","same","Appointed Jun 26, 2024, sworn in Jul 1, 2024; elected Nov 2024"),
 ("hillsborough","cepeda","inOfficeSince","same","Elected Nov 2022"),
 ("hillsborough","wostal","inOfficeSince","same","Elected Nov 2022"),
 ("hillsborough","boles","inOfficeSince","same","Elected Nov 2024, sworn in Nov 19, 2024"),
 ("hillsborough","toledo","job","same","Engineer and small business owner; former state representative"),
 ("hillsborough","lyssy","job","same","Attorney"),
 ("hillsborough","simic","job","same","Longtime educator and former assistant superintendent for curriculum; now an account executive with Magic School AI"),
 ("hillsborough","lyssy","raised","drop",["bb-sb2"]),
 ("hillsborough","simic","raised","drop",["bb-sb2"]),
 ("hillsborough","perez","raised","drop",["bb-sb6"]),
 ("hillsborough","gay","raised","drop",["bb-sb6"]),
 ("pasco","weightman","lastElection","same","Won the Aug 23, 2022 Republican primary with 48.87%, then unopposed in Nov 2022"),
 ("pasco","yeager","term","same","2024 to 2026, finishing the late Gary Bradford's term"),
 ("pasco","yeager","lastElection","drop",["soe-2024"]),
 ("pasco","harding","inOfficeSince","drop",["wusf-sb"]),
 ("pasco","harding","lastElection","same","Won outright in the Aug 18, 2026 primary, 72.15% to 27.85% over Michelle R. Mandarin"),
 ("hernando","mitten","inOfficeSince","same","Appointed Jul 31, 2026; sworn in Aug 4, 2026"),
]


def run():
    log = []
    by = {}
    for c, pid, f, act, val in EDITS:
        p = ROOT / "data" / f"seed_{c}.json"
        d = by.setdefault(c, json.loads(p.read_text()))
        person = next((x for x in d["people"] if x["id"] == pid), None)
        if not person or f not in person.get("claims", {}):
            print("skip", c, pid, f); continue
        before = [dict(x) for x in person["claims"][f]]
        if act == "same":
            for x in person["claims"][f]:
                x["value"] = val
        else:
            person["claims"][f] = [x for x in person["claims"][f] if x["source"] not in val]
        log.append({"county": c, "person": pid, "field": f, "action": "reworded to one shared wording" if act == "same" else "dropped an older undated report",
                    "before": before, "after": person["claims"][f]})
    for c, d in by.items():
        (ROOT / "data" / f"seed_{c}.json").write_text(json.dumps(d, indent=1, ensure_ascii=False))
    (ROOT / "data" / "curation_log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
    print(len(log), "edits")


if __name__ == "__main__":
    run()
