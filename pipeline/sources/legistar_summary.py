"""Merge a Legistar summary (pulled in the browser from webapi.legistar.com) into the seed.

The summary holds:
  - matches:     official roll calls for votes the seed already describes
  - splitVotes:  every non-unanimous roll call, with plain-English drafts
  - stats:       each member's yes / no / absent / abstain counts and meeting attendance
  - recusals:    votes where a member disclosed a conflict and abstained

All of it is tier 1 (the county's own record), cited to source id "legistar"
with the meeting page as the link.
"""

from __future__ import annotations

from .public_comment import parse as parse_public

import re

import copy

SRC = "legistar"


def _clip(text: str, n: int = 110) -> str:
    """Shorten at a word break, never mid-word, and say so with an ellipsis."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n + 1].rsplit(" ", 1)[0].rstrip(" ,;:-(")
    return cut + "…"


def auto_headline(s: dict, shared_item: bool) -> str:
    """Headline for a split vote no person has summarized yet.

    Uses the county's own words, cleaned up: the clerk's motion text when one agenda item had
    several motions (so each one reads differently), otherwise the agenda title. Leading
    "Consider" is dropped because every agenda item is something the board considers.
    """
    title = s.get("officialTitle") or s.get("headline") or "Untitled item"
    motion = (s.get("motion") or "").strip()
    usable_motion = motion and not re.match(r"(?i)^(a )?motion (was )?(made|by)\b", motion) and len(motion) >= 12
    text = motion if (shared_item and usable_motion) else title
    text = re.sub(r"(?i)^(consider(ation of)?|request(ing)? (to|for))\s+(the\s+)?", "", re.sub(r"\s+", " ", text).strip())
    text = text[:1].upper() + text[1:]
    return _clip(text)


def _roll(v: dict) -> dict:
    return {"yes": sorted(v.get("yes", [])), "no": sorted(v.get("no", []))}


def merge(seed: dict, summary: dict) -> dict:
    seed = copy.deepcopy(seed)
    urls = summary.get("meetingUrls", {})
    seed["sources"][SRC]["url"] = summary.get("calendarUrl", "https://pinellas.legistar.com/Calendar.aspx")
    votes = {v["id"]: v for v in seed["votes"]}

    # 1. Official roll calls for votes we already had from the news.
    for vid, m in summary.get("matches", {}).items():
        v = votes.get(vid)
        if not v:
            continue
        v.setdefault("claims", {}).setdefault("result", []).append({"value": m["result"], "source": SRC})
        v["claims"].setdefault("roll", []).append({"value": _roll(m), "source": SRC})
        if m.get("date") and not v.get("date"):
            v["date"] = m["date"]
            v.pop("dateNote", None)
        v["officialTitle"] = m.get("officialTitle")
        v["sourceUrl"] = urls.get(str(m.get("ev")), seed["sources"][SRC]["url"])
        for f in m.get("addFacts", []):
            v.setdefault("facts", []).append({"text": f["text"], "claims": [{"value": f["text"], "source": SRC}]})

    # 2. Every split vote becomes its own vote record.
    per_item: dict = {}
    for s in summary.get("splitVotes", []):
        per_item[(s.get("file"), s.get("date"))] = per_item.get((s.get("file"), s.get("date")), 0) + 1
    for s in summary.get("splitVotes", []):
        vid = f"lg-{s['item']}"
        roll = _roll(s)
        extra = {k: s.get(k, []) for k in ("absent", "abstain") if s.get(k)}
        seed["votes"].append({
            "id": vid, "date": s["date"], "topic": s["topic"],
            "headline": s["headline"] if s.get("inShort") else auto_headline(s, bool(s.get("file")) and per_item[(s.get("file"), s.get("date"))] > 1),
            "inShort": s["inShort"],
            "officialTitle": s["officialTitle"],
            "sourceUrl": urls.get(str(s["ev"]), seed["sources"][SRC]["url"]),
            "fileNumber": s.get("file"), "mover": s.get("mover"), "seconder": s.get("seconder"), "motion": s.get("motion"),
            "split": True, "rollExtra": extra,
            **({"public": pc} if (pc := parse_public(s.get("minutesNote"))) else {}),
            "claims": {
                "result": [{"value": s["result"], "source": SRC}],
                "roll": [{"value": roll, "source": SRC}],
            },
            "facts": [{"text": t, "claims": [{"value": t, "source": SRC}]} for t in s.get("facts", [])],
        })

    # 3. Each member's full record and attendance.
    recusals = {}
    for r in summary.get("recusals", []):
        recusals.setdefault(r["person"], []).append(r)
    questions = {}
    for q in summary.get("conflictQuestions", []):
        questions.setdefault(q["person"], []).append(q)

    for p in seed["people"]:
        st = summary.get("stats", {}).get(p["id"])
        if not st:
            continue
        cast = st["aye"] + st["nay"] + st["abstain"]
        attended = st["meetingsHeld"] - st["meetingsMissed"]
        p["claims"]["record"] = [{"value": (
            f"Voted on {cast:,} roll calls: {st['aye']:,} yes, {st['nay']} no"
            + (f", {st['abstain']} abstained" if st["abstain"] else "")
            + f". Marked absent on {st['absent']} items."), "source": SRC}]
        p["claims"]["attendance"] = [{"value": f"Attended {attended} of {st['meetingsHeld']} meetings with roll calls", "source": SRC}]
        notes = [f"Recused on {r['date']}: {r['minutes']}" for r in recusals.get(p["id"], [])]
        notes += [f"Asked about a possible conflict on {q['date']}: {q['minutes']}" for q in questions.get(p["id"], [])]
        if notes:
            p["claims"]["conflicts"] = [{"value": notes, "source": SRC}]
        p["record"] = {
            "scored_votes": cast,
            "meetings_held": st["meetingsHeld"],
            "meetings_attended": attended,
            "stake_votes": [{"disclosed": r["disclosed"], "abstained": r["abstained"]} for r in recusals.get(p["id"], [])],
            "nay": st["nay"], "aye": st["aye"], "absent": st["absent"], "abstain": st["abstain"],
        }

    seed["legistarTotals"] = summary.get("totals")
    seed["legistarScope"] = summary.get("scope")
    seed["legistarPulledAt"] = summary.get("pulledAt")
    return seed
