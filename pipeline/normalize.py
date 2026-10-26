"""Turn a raw Legistar pull into tier 1 claims the build step can merge.

Two outputs:
  1. Claims attached to votes the seed file already describes
     (matched by meeting date and title keywords), so a news-only vote
     upgrades to Verified once the official roll call agrees.
  2. New vote records for every other action item with a roll call,
     with the official title kept word for word and the plain-English
     summary marked as pending review.
"""

from __future__ import annotations

import re

YES = {"aye", "yes", "yea", "approve", "approved"}
NO = {"nay", "no", "opposed"}
SOURCE_ID = "legistar"


def _date(ev: dict) -> str:
    return (ev.get("EventDate") or "")[:10]


def _person_id(name: str, people: list[dict]) -> str | None:
    """Match a Legistar person name to a seed person by last name, then full name."""
    if not name:
        return None
    n = name.lower().replace("commissioner", "").strip()
    for p in people:
        if p["name"].lower() == n:
            return p["id"]
    last = n.split()[-1] if n.split() else n
    hits = [p for p in people if p["name"].lower().split()[-1].rstrip(".") == last]
    return hits[0]["id"] if len(hits) == 1 else None


def roll_from_votes(votes: list[dict], people: list[dict]) -> tuple[dict, list[str]]:
    roll = {"yes": [], "no": [], "absent": [], "abstain": []}
    unmatched = []
    for v in votes:
        pid = _person_id(v.get("VotePersonName", ""), people)
        val = (v.get("VoteValueName") or "").strip().lower()
        if pid is None:
            unmatched.append(v.get("VotePersonName", "?"))
            continue
        if val in YES:
            roll["yes"].append(pid)
        elif val in NO:
            roll["no"].append(pid)
        elif "abstain" in val or "recus" in val or "conflict" in val:
            roll["abstain"].append(pid)
        else:
            roll["absent"].append(pid)
    for k in roll:
        roll[k].sort()
    return {k: v for k, v in roll.items() if v or k in ("yes", "no")}, unmatched


def result_text(item: dict, roll: dict) -> str | None:
    passed = item.get("EventItemPassedFlag")
    if passed is None and not roll["yes"] and not roll["no"]:
        return None
    y, n = len(roll["yes"]), len(roll["no"])
    if n == 0 and y > 0:
        return "Passed unanimously" if passed != 0 else "Failed"
    verb = "Passed" if (passed == 1 or (passed is None and y > n)) else "Failed"
    return f"{verb} {y} to {n}"


def tally_check(item: dict, roll: dict) -> dict | None:
    """Legistar stores a typed tally ("5-2") separately from the individual votes.
    When they disagree, that is a record problem worth showing."""
    tally = item.get("EventItemTally")
    if not tally:
        return None
    m = re.match(r"\s*(\d+)\s*[-:]\s*(\d+)", tally)
    if not m:
        return None
    typed = (int(m.group(1)), int(m.group(2)))
    counted = (len(roll["yes"]), len(roll["no"]))
    if typed == counted:
        return None
    return {"typed": f"{typed[0]} to {typed[1]}", "counted": f"{counted[0]} to {counted[1]}"}


def to_claims(pull: dict, seed: dict) -> dict:
    """Returns {"matched": {vote_id: {"result": claim, "roll": claim, "url": str}},
                "extra": [vote records], "problems": [...]}."""
    people = seed["people"]
    matched, extra, problems = {}, [], []
    used_items = set()

    for ev in pull.get("events", []):
        d = _date(ev)
        for it in ev.get("_items", []):
            if not it.get("_votes") and it.get("EventItemPassedFlag") is None:
                continue
            title = (it.get("EventItemTitle") or it.get("EventItemMatterName") or "").strip()
            roll, unmatched = roll_from_votes(it.get("_votes", []), people)
            res = result_text(it, roll)
            url = ev.get("EventInSiteURL") or "https://pinellas.legistar.com/Calendar.aspx"
            low = title.lower()

            # 1. Attach to a seed vote when date and keywords match.
            for sv in seed["votes"]:
                lm = sv.get("legistarMatch") or {}
                if sv["id"] in matched:
                    continue
                if lm.get("date") and lm["date"] != d:
                    continue
                words = lm.get("contains") or []
                if words and sum(w in low for w in words) >= max(1, len(words) - 1):
                    matched[sv["id"]] = {
                        "result": {"value": res, "source": SOURCE_ID} if res else None,
                        "roll": {"value": {"yes": roll["yes"], "no": roll["no"]}, "source": SOURCE_ID},
                        "url": url,
                        "officialTitle": title,
                    }
                    used_items.add(it.get("EventItemId"))
                    break

            mismatch = tally_check(it, roll)
            if mismatch:
                problems.append({
                    "id": f"tally-{it.get('EventItemId')}",
                    "subject": f"{d}: {title[:80]}",
                    "field": "vote tally",
                    "kind": "Typed tally doesn't match the individual votes",
                    "versions": [
                        {"value": mismatch["typed"] + " (typed tally)", "sources": [SOURCE_ID], "official": True},
                        {"value": mismatch["counted"] + " (counted from each member's vote)", "sources": [SOURCE_ID], "official": True},
                    ],
                    "status": "Open: correction request to the Clerk",
                })
            if unmatched:
                problems.append({
                    "id": f"names-{it.get('EventItemId')}",
                    "subject": f"{d}: {title[:80]}",
                    "field": "voter names",
                    "kind": "Name not matched to a known official",
                    "versions": [{"value": ", ".join(unmatched), "sources": [SOURCE_ID]}],
                    "status": "Open: needs a human match",
                })

            # 2. Everything else with a recorded action becomes its own vote record.
            if it.get("EventItemId") in used_items or not res:
                continue
            extra.append({
                "id": f"lg-{it.get('EventItemId')}",
                "date": d,
                "topic": "other",
                "headline": title[:140] or "Untitled agenda item",
                "inShort": None,  # plain English pending human review
                "officialTitle": title,
                "claims": {
                    "result": [{"value": res, "source": SOURCE_ID}],
                    "roll": [{"value": {"yes": roll["yes"], "no": roll["no"]}, "source": SOURCE_ID}],
                },
                "facts": [],
                "routine": roll["no"] == [] and len(roll["yes"]) > 0,
                "sourceUrl": url,
            })
    return {"matched": matched, "extra": extra, "problems": problems}
