"""What the clerk's minutes say about public comment on an item.

We report counts and stated sides only. Members of the public are private people, so we never
publish their names; we keep the city they gave, which the minutes record.
"""
from __future__ import annotations

import re

from ..rtf import rtf_to_text

WORD_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _side(phrase: str) -> str:
    p = phrase.lower()
    if re.search(r"support|in favor", p):
        return "for"
    if re.search(r"oppos|concern|against|object", p):
        return "against"
    return "other"


def parse(note: str) -> dict | None:
    t = rtf_to_text(note or "")
    if not t:
        return None
    out: dict = {"applicant": 0, "speakers": None, "for": 0, "against": 0, "other": 0, "cities": [], "groups": False, "mail": None}
    m = re.search(r"((?:no|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+(?:emails?|letters?|pieces? of correspondence)[^.]*?(?:ha(?:s|ve) been|was|were) received)", t, re.I)
    if m:
        out["mail"] = m.group(1)[0].upper() + m.group(1)[1:] + "."
    elif re.search(r"no correspondence has been received", t, re.I):
        out["mail"] = "No letters or emails were received."
    if re.search(r"no citizens appeared|there was no public input|no one appeared", t, re.I):
        out["speakers"] = 0
    found = False
    # "the following individuals appeared and expressed their support:" then one "Name, City" per line
    for blk in re.finditer(r"following (?:individuals|persons|citizens) appeared(?: and)? ([^:\n]*):\s*\n((?:\s*[^\n]+,\s*[A-Z][^\n]*\n?)+)", t):
        side = _side(blk.group(1))
        for line in blk.group(2).strip().split("\n"):
            line = line.strip()
            if not line:
                continue  # the minutes often leave a blank line between names
            if len(line) > 90 or re.search(r"\b(Commissioner|Chair|Attorney|staff|whereupon)\b", line) or not re.match(r"^[A-Z][\w.'\- ]+,\s*[A-Z]", line):
                break
            city = re.sub(r"\s*\(.*$", "", line.split(",", 1)[1]).strip()
            out[side] += 1
            out["cities"].append(city)
            if "on behalf of" in line:
                out["groups"] = True
            found = True
    # "Jane Doe, Belleair, appeared and expressed her support for the item"
    for one in re.finditer(r"([A-Z][\w.'\-]+(?: [A-Z][\w.'\-]+){1,3}), ([A-Z][a-zA-Z .]+), appeared(?:,| and) ([^;.]*)", t):
        if re.search(r"applicant|petitioner|property owner|represents|is with|on behalf of the", one.group(3) + t[max(0, one.start() - 60):one.start()], re.I):
            out["applicant"] += 1  # the person asking for the decision, or their team: not public comment
            continue
        out[_side(one.group(3))] += 1
        out["cities"].append(one.group(2).strip())
        found = True
    if found:
        out["speakers"] = out["for"] + out["against"] + out["other"]
    elif out["speakers"] is None and re.search(r"accepted public input|public input was received|public comment was (?:taken|received)", t, re.I):
        out["speakers"] = "some"
    if out["speakers"] is None and out["applicant"]:
        out["speakers"] = 0
    if out["speakers"] is None and not out["mail"]:
        return None
    out["cities"] = sorted(set(out["cities"]))
    return out
