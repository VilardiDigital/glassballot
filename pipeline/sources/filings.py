"""Financial disclosure filing dates from the Florida Commission on Ethics (EFDMS public search).

Florida's Form 1 and Form 6 are due July 1 for the prior year. State law gives a grace period
until September 1 before automatic fines start. We state the filing date and whether it came
after July 1; we don't say a fine applied, because weekends and holidays can move the deadline.
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = "ethics-efdms"
SOURCE = {"title": "Florida Commission on Ethics, financial disclosure public search", "url": "https://disclosure.floridaethics.gov/PublicSearch/Filings",
          "publisher": "Florida Commission on Ethics", "tier": 1, "accessed": "2026-10-27"}


def _fmt(d: date) -> str:
    return d.strftime("%b %-d, %Y")


def merge(seed: dict, county: str) -> dict:
    files = sorted((ROOT / "data").glob("ethics_filings_*.json"))
    if not files:
        return seed
    data = json.loads(files[-1].read_text())
    people = {p["id"]: p for p in seed["people"]}
    hit = False
    for key, rows in data.items():
        c, pid = key.split("/")
        p = people.get(pid)
        if c != county or not p or p.get("claims", {}).get("filings"):
            continue
        lines, recs = [], []
        for r in [x.strip() for x in rows.split(";") if x.strip()]:
            year, form, filed = r.split("|")[:3]
            y, fd = int(year), date.fromisoformat(filed)
            due = date(y + 1, 7, 1)
            while due.weekday() >= 5:  # a weekend due date moves to Monday
                due = date.fromordinal(due.toordinal() + 1)
            late = (fd - due).days
            note = "" if late <= 0 else f", {late} day{'s' if late != 1 else ''} after the {_fmt(due)} due date"
            lines.append(f"Form {form} for {y}: filed {_fmt(fd)}{note}")
            if not form.endswith("X"):
                recs.append({"on_time": fd <= due, "complete": None})
        p.setdefault("claims", {})["filings"] = [{"value": lines, "source": SRC}]
        p.setdefault("record", {})["filings"] = recs
        hit = True
    if hit:
        seed["sources"].setdefault(SRC, SOURCE)
    return seed
