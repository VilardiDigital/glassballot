"""The Pocket or Public score.

Four parts, each 0 to 100, each computed only from records. An overall
score appears only when an official has at least MIN_SCORED_VOTES votes
with enough data to score. The formula is public on purpose.

  conflict_handling  Of votes where the official, family, business or a
                     major donor had a direct stake, the share where they
                     disclosed it and stepped aside (Form 8B, recusal).
  money_timing       100 minus the share of their money that arrived
                     within 90 days of a vote that directly helped that donor.
  promise_match      Share of tracked promises their votes matched.
  openness           Average of on-time complete filings and meeting attendance.

Overall = plain average of the parts that have data (at least 3 of 4).
"""

from __future__ import annotations

from datetime import date, timedelta

MIN_SCORED_VOTES = 25
DONOR_WINDOW_DAYS = 90


def conflict_handling(stake_votes: list[dict]) -> float | None:
    """stake_votes: [{"disclosed": bool, "abstained": bool}] for votes with a direct stake."""
    if not stake_votes:
        return None
    handled = sum(1 for v in stake_votes if v.get("disclosed") and v.get("abstained"))
    return round(100 * handled / len(stake_votes), 1)


def money_timing(contributions: list[dict], stake_votes_by_donor: dict[str, list[str]]) -> float | None:
    """contributions: [{"donor_id", "amount", "date"}]; stake_votes_by_donor: donor_id -> [vote dates]."""
    total = sum(c["amount"] for c in contributions)
    if total <= 0:
        return None
    window = timedelta(days=DONOR_WINDOW_DAYS)
    flagged = 0.0
    for c in contributions:
        given = date.fromisoformat(c["date"])
        for vd in stake_votes_by_donor.get(c["donor_id"], []):
            if abs(date.fromisoformat(vd) - given) <= window:
                flagged += c["amount"]
                break
    return round(100 - 100 * flagged / total, 1)


def promise_match(promises: list[dict]) -> float | None:
    """promises: [{"matched": bool | None}]; None means no vote has tested it yet."""
    tested = [p for p in promises if p.get("matched") is not None]
    if not tested:
        return None
    return round(100 * sum(1 for p in tested if p["matched"]) / len(tested), 1)


def openness(filings: list[dict], meetings_held: int, meetings_attended: int) -> float | None:
    parts = []
    if filings:
        # "complete" is None when the form itself can't be read; then only timeliness counts.
        ok = sum(1 for f in filings if f.get("on_time") and f.get("complete") is not False)
        parts.append(100 * ok / len(filings))
    if meetings_held:
        parts.append(100 * meetings_attended / meetings_held)
    if not parts:
        return None
    return round(sum(parts) / len(parts), 1)


def pocket_or_public(record: dict) -> dict:
    """record keys: scored_votes, stake_votes, contributions, stake_votes_by_donor,
    promises, filings, meetings_held, meetings_attended. Missing keys mean no data."""
    parts = {
        "conflict_handling": conflict_handling(record.get("stake_votes", [])),
        "money_timing": record["money_timing_value"] if record.get("money_timing_value") is not None
                        else money_timing(record.get("contributions", []), record.get("stake_votes_by_donor", {})),
        "promise_match": promise_match(record.get("promises", [])),
        "openness": openness(record.get("filings", []), record.get("meetings_held", 0), record.get("meetings_attended", 0)),
    }
    scored_votes = record.get("scored_votes", 0)
    have = [v for v in parts.values() if v is not None]
    overall = None
    reason = None
    if scored_votes < MIN_SCORED_VOTES:
        reason = f"Not enough record yet: {scored_votes} of {MIN_SCORED_VOTES} scored votes loaded."
    elif len(have) < 3:
        reason = f"Not enough record yet: {len(have)} of 4 parts have data."
    else:
        overall = round(sum(have) / len(have))
    return {"overall": overall, "parts": parts, "scoredVotes": scored_votes, "reason": reason}
