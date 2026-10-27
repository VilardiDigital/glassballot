"""Find which meeting and finance systems each Florida county uses, by trying the public APIs.

Runs on GitHub Actions (which can reach county sites). Writes data/survey_probe.json.
"""
from __future__ import annotations

import concurrent.futures as cf
import html
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "GlassBallot/1.0 (+https://glassballot.org; nonpartisan voter guide; survey of public meeting systems)"}
COUNTIES = {"alachua": "Alachua", "baker": "Baker", "bay": "Bay", "bradford": "Bradford", "brevard": "Brevard", "broward": "Broward", "calhoun": "Calhoun",
 "charlotte": "Charlotte", "citrus": "Citrus", "clay": "Clay", "collier": "Collier", "columbia": "Columbia", "desoto": "DeSoto", "dixie": "Dixie", "duval": "Duval",
 "escambia": "Escambia", "flagler": "Flagler", "franklin": "Franklin", "gadsden": "Gadsden", "gilchrist": "Gilchrist", "glades": "Glades", "gulf": "Gulf",
 "hamilton": "Hamilton", "hardee": "Hardee", "hendry": "Hendry", "hernando": "Hernando", "highlands": "Highlands", "hillsborough": "Hillsborough", "holmes": "Holmes",
 "indianriver": "Indian River", "jackson": "Jackson", "jefferson": "Jefferson", "lafayette": "Lafayette", "lake": "Lake", "lee": "Lee", "leon": "Leon", "levy": "Levy",
 "liberty": "Liberty", "madison": "Madison", "manatee": "Manatee", "marion": "Marion", "martin": "Martin", "miamidade": "Miami-Dade", "monroe": "Monroe",
 "nassau": "Nassau", "okaloosa": "Okaloosa", "okeechobee": "Okeechobee", "orange": "Orange", "osceola": "Osceola", "palmbeach": "Palm Beach", "pasco": "Pasco",
 "pinellas": "Pinellas", "polk": "Polk", "putnam": "Putnam", "stjohns": "St. Johns", "stlucie": "St. Lucie", "santarosa": "Santa Rosa", "sarasota": "Sarasota",
 "seminole": "Seminole", "sumter": "Sumter", "suwannee": "Suwannee", "taylor": "Taylor", "union": "Union", "volusia": "Volusia", "wakulla": "Wakulla",
 "walton": "Walton", "washington": "Washington"}
EXTRA = {"miamidade": ["miamidade", "miami-dade", "mdc"], "duval": ["jacksonville", "coj", "jaxcityc"], "palmbeach": ["pbc", "pbcgov", "palmbeach"],
         "stjohns": ["sjcfl", "stjohns"], "stlucie": ["stlucieco", "stlucie"], "santarosa": ["santarosa"], "indianriver": ["ircgov"], "desoto": ["desotobocc"],
         "hillsborough": ["hillsboroughcounty"], "hernando": ["hernandocountyfl"], "charlotte": ["charlottecountyfl"]}


def get(url: str, timeout: int = 20):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.geturl()
    except Exception as e:
        return getattr(e, "code", 0) or 0, "", url


def variants(k: str) -> list[str]:
    base = EXTRA.get(k, []) + [k, f"{k}county", f"{k}countyfl", f"{k}co", f"{k}cofl", f"{k}fl", f"{k}bocc", f"{k}countygov", f"{k}gov", f"{k}-county", f"{k}countyflorida"]
    out = []
    for v in base:
        if v not in out:
            out.append(v)
    return out


def legistar(k: str):
    for c in variants(k):
        st, body, _ = get(f"https://webapi.legistar.com/v1/{c}/bodies")
        if st == 200 and body.strip().startswith("["):
            try:
                bodies = json.loads(body)
            except Exception:
                continue
            bcc = [b for b in bodies if re.search(r"board of county commission|county commission|city council|board of commissioners", b.get("BodyName", ""), re.I)]
            st2, ev, _ = get(f"https://webapi.legistar.com/v1/{c}/events?$top=1&$orderby=EventDate%20desc")
            last = None
            try:
                last = json.loads(ev)[0]["EventDate"][:10]
            except Exception:
                pass
            # Does a recent commission meeting have per-member votes?
            votes = None
            if bcc:
                bid = bcc[0]["BodyId"]
                st3, evs, _ = get(f"https://webapi.legistar.com/v1/{c}/events?$filter=EventBodyId%20eq%20{bid}&$top=3&$orderby=EventDate%20desc")
                try:
                    for e in json.loads(evs):
                        st4, its, _ = get(f"https://webapi.legistar.com/v1/{c}/events/{e['EventId']}/eventitems")
                        acted = [i for i in json.loads(its) if i.get("EventItemPassedFlag") is not None][:5]
                        for i in acted:
                            st5, vs, _ = get(f"https://webapi.legistar.com/v1/{c}/eventitems/{i['EventItemId']}/votes")
                            if vs.strip().startswith("[") and json.loads(vs):
                                votes = True
                                break
                        if votes:
                            break
                    votes = votes or False
                except Exception:
                    pass
            return {"client": c, "bodies": [(b["BodyId"], b["BodyName"]) for b in bcc][:5], "lastEvent": last, "perMemberVotes": votes}
    return None


def civicclerk(k: str):
    for t in [f"{k}cofl", f"{k}countyfl", f"{k}fl", f"{k}county", f"{k}co", k]:
        st, body, _ = get(f"https://{t}.api.civicclerk.com/v1/Events?$top=1&$orderby=startDateTime%20desc")
        if st == 200 and '"value"' in body:
            try:
                v = json.loads(body)["value"]
                return {"tenant": t, "lastEvent": v[0]["startDateTime"][:10] if v else None, "name": v[0].get("eventName") if v else None}
            except Exception:
                return {"tenant": t}
    return None


def granicus(k: str):
    for g in [f"{k}county", f"{k}co", f"{k}countyfl", k, f"{k}fl"]:
        st, body, url = get(f"https://{g}.granicus.com/ViewPublisher.php?view_id=1")
        if st == 200 and "granicus" in url and len(body) > 2000 and re.search(r"agenda|minutes|meeting", body, re.I):
            return {"site": g}
    return None


def boarddocs(k: str):
    for b in [k, f"{k}co", f"{k}county", f"{k}cps", f"{k}schools", f"{k}sb", f"{k}k12"]:
        st, body, url = get(f"https://go.boarddocs.com/fl/{b}/Board.nsf/Public")
        if st == 200 and "BoardDocs" in body and "not found" not in body.lower()[:3000]:
            t = re.search(r"<title>(.*?)</title>", body, re.S)
            return {"slug": b, "title": html.unescape(t.group(1)).strip()[:120] if t else None}
    return None


def voterfocus(k: str):
    st, page, _ = get(f"https://www.voterfocus.com/CampaignFinance/candidate_pr.php?c={k}")
    opts = re.findall(r"<option value=['\"](\d+)['\"][^>]*>([^<]*)", page)
    cyc = [(int(v), re.sub(r"\s+", " ", t).strip()) for v, t in opts if "2026" in t and not re.search(r"committee|party|municipal|city of|town of|special|recall|club|estates|district|welaka|freeport|quincy|longboat|belleview|dunnellon|altamonte|casselberry|lake mary|longwood|oviedo|sanford|winter springs|naples|fort pierce|live oak|gainesville", t, re.I)]
    if not cyc:
        return {"found": bool(opts)}
    el = cyc[0][0]
    st, p2, _ = get(f"https://www.voterfocus.com/CampaignFinance/candidate_pr.php?c={k}&el={el}")
    offices = re.findall(r'officename">\s*Office:\s*(.*?)</div>', p2, re.S)
    local = [html.unescape(o).strip() for o in offices if re.search(r"commission|school", o, re.I)]
    return {"slug": k, "cycle": el, "cycleName": cyc[0][1], "allCycles": cyc, "localOffices": local, "candidatesListed": p2.count("ca=")}


def probe(k: str) -> tuple[str, dict]:
    return k, {"name": COUNTIES[k] + " County", "legistar": legistar(k), "civicclerk": civicclerk(k), "granicus": granicus(k),
               "boarddocs": boarddocs(k), "voterfocus": voterfocus(k)}


def main():
    with cf.ThreadPoolExecutor(8) as ex:
        res = dict(ex.map(probe, COUNTIES))
    (ROOT / "data" / "survey_probe.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(sum(1 for v in res.values() if v["legistar"]), "Legistar;", sum(1 for v in res.values() if v["civicclerk"]), "CivicClerk;",
          sum(1 for v in res.values() if v["granicus"]), "Granicus;", sum(1 for v in res.values() if v["boarddocs"]), "BoardDocs;",
          sum(1 for v in res.values() if (v["voterfocus"] or {}).get("cycle")), "VoterFocus")


if __name__ == "__main__":
    main()
