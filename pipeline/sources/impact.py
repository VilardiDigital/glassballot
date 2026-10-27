"""Merge data/impact_<county>.json: what each vote does, and what happened after, each with sources.

Only fact-checked files live in data/. Research drafts stay in research/impact/ until checked.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def merge(seed: dict, county: str) -> dict:
    f = ROOT / "data" / f"impact_{county}.json"
    if not f.exists():
        return seed
    imp = json.loads(f.read_text())
    for sid, s in imp.get("sources", {}).items():
        if sid not in seed["sources"]:
            seed["sources"][sid] = {k: s.get(k) for k in ("title", "url", "publisher", "tier") if s.get(k) is not None} | ({"accessed": s["date"]} if s.get("date") else {})
    have = set(seed["sources"])
    for v in seed["votes"]:
        x = imp.get("votes", {}).get(v["id"])
        if not x:
            continue
        out = {}
        w = x.get("whatItDoes")
        if w and w.get("text") and any(s in have for s in w.get("sources", [])):
            out["does"] = {"text": w["text"], "sources": [s for s in w["sources"] if s in have]}
        after = [a for a in x.get("afterward") or [] if a.get("text") and any(s in have for s in a.get("sources", []))]
        if after:
            out["after"] = sorted(({"date": a.get("date"), "text": a["text"], "sources": [s for s in a["sources"] if s in have]} for a in after), key=lambda a: a["date"] or "")
        if out:
            v["impact"] = out
    return seed
