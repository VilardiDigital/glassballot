"""Merge the reporting digs (research/dig_<county>.json) into a county seed.

Each dig lists, per person, past campaign promises, election history, positions taken
in office and any public ethics items, each with a source. Items flagged as resting on
a single weak source are kept out until a second source confirms them (see SKIP_SOURCES).
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Sources we won't publish on their own: secondhand accounts of unseen video, unverified residency claims.
SKIP_SOURCES = {"rnews-allocco-terms", "rnews-mitten-seat"}
SKIP_WORDS = ("viewer-supplied", "residency", "not independently confirmed")


def _d(iso: str | None) -> str:
    try:
        y, m, dd = (int(x) for x in str(iso)[:10].split("-"))
        return date(y, m, dd).strftime("%b %-d, %Y")
    except Exception:
        return str(iso or "")


def _pct(x) -> str:
    try:
        return f"{float(x):.1f}%"
    except Exception:
        return str(x)


def _end(t: str) -> str:
    t = (t or "").strip()
    return t if not t or t[-1] in ".!?" or t.endswith((".\"", "?\"", "!\"")) else t + "."


def _clean(t: str) -> str:
    # Our internal source ids belong in the source link, not in the sentence.
    t = re.sub(r"\s*\((?:see )?[a-z0-9]+(?:-[a-z0-9]+)+\)", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:1].upper() + t[1:]


def _text(kind: str, it) -> str:
    return _clean(_raw(kind, it))


def _raw(kind: str, it) -> str:
    if isinstance(it, str):
        return it
    v = it.get("value")
    if kind == "promises":
        yr = it.get("year")
        return f"{yr} campaign: {v}" if yr and v and not str(v).startswith(str(yr)) else (v or "")
    if kind == "electionHistory":
        if v:
            return v
        opp = "; ".join(f"{o.get('name')}" + (f" {_pct(o['pct'])}" if o.get("pct") is not None else "") for o in it.get("opponents", []) if isinstance(o, dict))
        stage = it.get("stage", "") or ""
        if stage.split(" ")[0] in ("General", "Primary", "Universal", "Runoff", "Special"):
            stage = stage[:1].lower() + stage[1:]
        base = f"{it.get('year', '')}{' ' + stage if stage else ''}, {it.get('office', '')}: {it.get('result', '')}"
        if it.get("pct") is not None:
            base += f" with {_pct(it['pct'])}"
            if it.get("votes"):
                base += f" ({int(it['votes']):,} votes)"
        if opp:
            base += f". Others: {opp}"
        if it.get("note"):
            base += f". {it['note']}"
        return base.strip()
    if kind == "keyPositions":
        if v:
            return (f"{_d(it['date'])}: " if it.get("date") else "") + v
        out = (f"{_d(it['date'])}: " if it.get("date") else "") + _end(it.get("issue", "")) + " " + _end(it.get("position", ""))
        if it.get("detail"):
            out += " " + _end(it["detail"])
        return out.strip()
    return v or ""


FIELDS = {"promises": "promises", "electionHistory": "electionHistory", "keyPositions": "keyPositions", "conflicts": "conflicts"}


def merge(seed: dict, county: str) -> dict:
    f = ROOT / "data" / f"dig_{county}.json"
    if not f.exists():
        return seed
    dig = json.loads(f.read_text())
    # Fact-check results: data/dig_checks.json lists items to fix or drop after checking them against the source.
    cf = ROOT / "data" / "dig_checks.json"
    checks = {(c["person"], c["kind"], c["index"]): c for c in (json.loads(cf.read_text()) if cf.exists() else []) if c.get("county") == county}
    for sid, s in dig.get("sources", {}).items():
        if sid not in seed["sources"]:
            seed["sources"][sid] = {k: s.get(k) for k in ("title", "url", "publisher", "tier") if s.get(k) is not None} | ({"accessed": s["date"]} if s.get("date") else {})
    people = {p["id"]: p for p in seed["people"]}
    for pid, blocks in dig.get("people", {}).items():
        p = people.get(pid)
        if not p:
            continue
        p.pop("dig", None)
        out = p.setdefault("dig", {})
        for kind, field in FIELDS.items():
            items = blocks.get(kind) or []
            for idx, it in enumerate(items):
                chk = checks.get((pid, kind, idx))
                if chk and chk.get("verdict") == "drop":
                    continue
                if chk and chk.get("verdict") == "fix" and chk.get("fix") and isinstance(it, dict):
                    it = {**it, "value": chk["fix"]}
                src = it.get("source") if isinstance(it, dict) else None
                note = (it.get("note") or "") if isinstance(it, dict) else ""
                if not src or (isinstance(it, dict) and it.get("caution")) or src in SKIP_SOURCES or src not in seed["sources"] or any(w in note.lower() for w in SKIP_WORDS):
                    continue
                t = _text(kind, it)
                if not t:
                    continue
                row = {"text": t, "source": src}
                if isinstance(it, dict) and (it.get("year") or it.get("date")):
                    row["when"] = str(it.get("year") or it["date"][:4])
                if t not in [r["text"] for r in out.get(field, [])]:
                    out.setdefault(field, []).append(row)
    return seed
