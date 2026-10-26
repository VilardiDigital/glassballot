"""Turn claims from several sources into one labeled fact.

A claim is {"value": ..., "source": "<source id>"}. The source registry
gives each source a tier and a publisher. The rules here are the ones
voters see on the site:

  verified    a legal-record source (tier 1) agrees with at least one
              other independent source
  single      exactly one tier 1 or tier 2 source, nothing to check against
  unverified  only data groups, news or self-reported claims, even if
              several agree (they still need matching to a legal record)
  conflict    sources disagree; every version is kept and shown
  unknown     no source has this fact

Nothing is ever averaged or quietly picked. When sources conflict, the
fact carries every version, and the strongest source is marked as the
official record when it is tier 1.
"""

from __future__ import annotations

from typing import Any, Iterable

from . import TIER_LEGAL_RECORD, TIER_OFFICIAL_SECONDARY


def _norm(value: Any) -> Any:
    """Compare values loosely enough that formatting differences don't count as conflicts."""
    if isinstance(value, str):
        return " ".join(value.lower().replace(",", "").replace("$", "").split())
    if isinstance(value, list):
        return sorted(_norm(v) for v in value)
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in sorted(value.items())}
    return value


def label_fact(claims: Iterable[dict], registry: dict[str, dict], prefer_official: bool = False) -> dict:
    """Return a fact: {value, label, sources, versions?, note?}.

    prefer_official is for profile facts (dates, jobs, totals): when exactly one official
    record exists, it stands and the differing non-official reports are listed with it.
    Votes keep the strict rule, so news that contradicts the minutes is always a conflict.
    """
    claims = [c for c in claims if c.get("value") is not None]
    if not claims:
        return {"value": None, "label": "unknown", "sources": []}

    # Group claims by normalized value.
    groups: dict[str, dict] = {}
    for c in claims:
        key = repr(_norm(c["value"]))
        g = groups.setdefault(key, {"value": c["value"], "sources": []})
        if c["source"] not in g["sources"]:
            g["sources"].append(c["source"])

    def tier(src: str) -> int:
        return registry.get(src, {}).get("tier", 9)

    def publishers(srcs: list[str]) -> set[str]:
        return {registry.get(s, {}).get("publisher", s) for s in srcs}

    # A less detailed version of the same fact is agreement, not a conflict:
    # "approved" (news) and "passed unanimously" (minutes) say the same thing.
    if len(groups) > 1 and all(isinstance(g["value"], str) for g in groups.values()):
        def gen(v: str) -> str:
            return _norm(v).replace("approved", "passed").rstrip(".")
        keys = sorted(groups, key=lambda k: len(gen(groups[k]["value"])))
        merged: dict[str, dict] = {}
        for k in keys:
            g = groups[k]
            def general_of(short: str, long: str) -> bool:
                # Only plain words can be "less detailed": numbers and dates must match exactly.
                if any(ch.isdigit() for ch in short):
                    return False
                if long == short or long.startswith(short + " "):
                    return True
                # "Urologist" inside "Board-certified urologist in Brandon": same fact, less detail.
                sw = [w.strip(".;:()") for w in short.split()]
                lw = {w.strip(".;:()") for w in long.replace("-", " ").split()} | {w.strip(".;:()") for w in long.split()}
                return len(sw) <= 6 and all(w in lw for w in sw)
            host = next((mk for mk in merged if general_of(gen(merged[mk]["value"]), gen(g["value"]))
                         or general_of(gen(g["value"]), gen(merged[mk]["value"]))), None)
            if host is None:
                merged[k] = {"value": g["value"], "sources": list(g["sources"])}
            else:
                h = merged[host]
                if len(gen(g["value"])) > len(gen(h["value"])):
                    h["value"] = g["value"]  # keep the more specific wording
                h["sources"] += [s for s in g["sources"] if s not in h["sources"]]
        groups = merged

    if len(groups) > 1:
        versions = []
        for g in groups.values():
            best = min(tier(s) for s in g["sources"])
            versions.append({
                "value": g["value"],
                "sources": g["sources"],
                "official": best == TIER_LEGAL_RECORD,
                "bestTier": best,
            })
        versions.sort(key=lambda v: v["bestTier"])
        official = [v for v in versions if v["bestTier"] <= TIER_OFFICIAL_SECONDARY]
        if prefer_official and len(official) == 1:
            # One official record against differently worded or older non-official reports:
            # the official record stands, and the other reports stay visible next to it.
            o = official[0]
            others = [v for v in versions if v is not o]
            lab = "verified" if o["bestTier"] == TIER_LEGAL_RECORD and len(publishers(o["sources"])) >= 2 else "single"
            return {"value": o["value"], "label": lab, "sources": o["sources"],
                    "note": "From the official record. Other reports word it differently or are older; they're listed below it.",
                    "otherReports": [{"value": v["value"], "sources": v["sources"]} for v in others]}
        return {
            "value": versions[0]["value"] if versions[0]["official"] else None,
            "label": "conflict",
            "sources": [s for v in versions for s in v["sources"]],
            "versions": versions,
        }

    g = next(iter(groups.values()))
    srcs = g["sources"]
    best = min(tier(s) for s in srcs)
    independent = len(publishers(srcs))

    if best == TIER_LEGAL_RECORD and independent >= 2:
        lab, note = "verified", None
    elif best <= TIER_OFFICIAL_SECONDARY and independent == 1:
        lab, note = "single", "One official record, nothing yet to check it against."
    elif best <= TIER_OFFICIAL_SECONDARY:
        lab, note = "single", "Official source plus non-official confirmation."
    else:
        lab = "unverified"
        note = (f"{independent} independent sources agree, but none is an official record yet."
                if independent >= 2 else "One non-official source. Not yet matched to an official record.")
    out = {"value": g["value"], "label": lab, "sources": srcs}
    if note:
        out["note"] = note
    return out


def find_problems(facts: dict[str, dict], subject_names: dict[str, str]) -> list[dict]:
    """Every conflict becomes an entry on the public Record problems log."""
    problems = []
    for key, fact in facts.items():
        if fact.get("label") != "conflict":
            continue
        subject, _, field = key.partition(".")
        problems.append({
            "id": "conflict-" + key.replace(".", "-"),
            "subject": subject_names.get(subject, subject),
            "field": field,
            "kind": "Sources disagree",
            "versions": fact["versions"],
            "status": "Open: needs the official record",
        })
    return problems
