"""Legistar public Web API client (Granicus).

Pinellas County publishes its commission agendas, minutes and roll-call
votes in Legistar. The public API lives at
https://webapi.legistar.com/v1/<client>/... and needs no key for most
counties. Every response is archived to data/raw/ with the URL and the
time it was pulled, so any fact on the site can be traced to the exact
response it came from.

Usage:
    python -m pipeline.sources.legistar --client pinellas --since 2026-01-01
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://webapi.legistar.com/v1"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
POLITE_DELAY_S = 0.5  # crawl gently; these are public servers


def _get(client: str, path: str, params: dict | None = None, fetch=None) -> list | dict:
    url = f"{BASE}/{client}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, safe="$ '")
    if fetch is not None:  # tests inject a fake fetcher
        data = fetch(url)
    else:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "GlassBallot/0.1 (+https://glassballot.org)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        time.sleep(POLITE_DELAY_S)
    _archive(client, url, data)
    return data


def _archive(client: str, url: str, data) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    name = hashlib.sha1(url.encode()).hexdigest()[:16]
    (RAW_DIR / f"{client}-{name}.json").write_text(json.dumps({"url": url, "pulledAt": stamp, "data": data}))


def pull(client: str, body_name: str, since: str, fetch=None) -> dict:
    """Pull one governing body's meetings, items and roll-call votes since a date."""
    bodies = _get(client, "bodies", fetch=fetch)
    body = next((b for b in bodies if b.get("BodyName", "").lower() == body_name.lower()), None)
    if body is None:
        names = ", ".join(b.get("BodyName", "?") for b in bodies)
        raise SystemExit(f"Body '{body_name}' not found. Bodies in {client}: {names}")

    persons = _get(client, "persons", fetch=fetch)
    events = _get(client, "events", {
        "$filter": f"EventBodyId eq {body['BodyId']} and EventDate ge datetime'{since}'",
        "$orderby": "EventDate desc",
    }, fetch=fetch)

    out_events = []
    for ev in events:
        items = _get(client, f"events/{ev['EventId']}/eventitems", {"AgendaNote": 1, "MinutesNote": 1, "Attachments": 1}, fetch=fetch)
        for it in items:
            # Only items with a recorded action can have votes.
            if it.get("EventItemPassedFlag") is not None or it.get("EventItemActionName"):
                it["_votes"] = _get(client, f"eventitems/{it['EventItemId']}/votes", fetch=fetch)
            else:
                it["_votes"] = []
        ev["_items"] = items
        out_events.append(ev)

    return {"client": client, "body": body, "persons": persons, "events": out_events,
            "pulledAt": datetime.now(timezone.utc).isoformat()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", default="pinellas")
    ap.add_argument("--body", default="Board of County Commissioners")
    ap.add_argument("--since", default="2025-01-01")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "data" / "legistar_pinellas.json"))
    a = ap.parse_args()
    result = pull(a.client, a.body, a.since)
    Path(a.out).write_text(json.dumps(result, indent=1))
    n_items = sum(len(e["_items"]) for e in result["events"])
    print(f"Pulled {len(result['events'])} meetings and {n_items} agenda items into {a.out}")


if __name__ == "__main__":
    main()
