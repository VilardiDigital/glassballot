# Glass Ballot pipeline (Pinellas pilot)

Collects public records about elected officials and candidates, labels every
fact by how well its sources agree, and builds the Glass Ballot site.
Python 3.10+ standard library only: nothing to install.

## Run it

```bash
python -m unittest discover -s tests -v           # 26 tests: labels, scoring, Legistar merge
python -m pipeline.build --accessed 2026-10-26 \
  --legistar-summary data/legistar_pinellas_summary.json \
  --money data/money_pinellas.json --html          # what the published site uses
python -m pipeline.sources.legistar --since 2024-11-19   # fresh raw pull of official votes (normal internet)
```

## Where the data came from (pulled Oct 26, 2026)

| File | Source | What it holds |
| --- | --- | --- |
| `data/legistar_pinellas_summary.json` | Pinellas County Legistar API | 42 meetings, 1,346 agenda items, 1,268 roll calls; every split vote with minutes; each member's totals and attendance; recusals |
| `data/money_pinellas.json` | Pinellas Supervisor of Elections (VoterFocus exports), Sunbiz, FL Commission on Ethics | Totals and donor breakdowns for 11 people; donors named in county votes; gifts between officials; Form 6 filing dates |
| `data/seed_pinellas.json` | County pages, Ballotpedia, The Ballot Brief, news | People, races, promises, and news-reported votes, each claim tied to its source |

Scripts used in the browser are in `pipeline/browser/`.

`site/glassballot.html` is the finished page. Without `--legistar`, the build uses only
the hand-gathered facts in `data/seed_pinellas.json`.

## How the pieces fit

| File | Job |
| --- | --- |
| `data/seed_pinellas.json` | Facts gathered by hand, each one a claim tied to a source id and tier |
| `pipeline/sources/legistar.py` | Pulls meetings, agenda items and roll-call votes from the county's public Legistar API; archives every raw response to `data/raw/` |
| `pipeline/normalize.py` | Matches Legistar votes to seed votes (date plus keywords), turns roll calls into tier 1 claims, logs tally mismatches and unmatched names |
| `pipeline/verify.py` | The labeling rules: Verified, Single source, Unverified, Conflict, Unknown. Conflicts keep every version |
| `pipeline/score.py` | Pocket or Public: four parts, public formula, no overall score under 25 scored votes |
| `pipeline/sources/legistar_summary.py` | Merges the official roll calls, split votes, attendance and recusals |
| `pipeline/sources/money.py` | Merges campaign money, donor-to-vote connections and disclosure filing dates |
| `pipeline/build.py` | Merges everything into `site/data.json` and bakes it into the page |
| `site/template.html` | The site: ballot, officials, votes, topics, race comparison, Ask, record problems, methods |

## Labeling rules

- **Verified**: a tier 1 legal record plus a second independent source agree.
- **Single source**: one official record, nothing yet to check against.
- **Unverified**: only data groups, news, or self-reported claims, even when several agree.
- **Conflict**: sources disagree. Every version is published, the official one first.
- **Unknown**: nothing found. Shown for fields every profile must have.

Two outlets from the same publisher count as one source.

## Adding a county

1. Add its sources and people to a new seed file.
2. If it uses Legistar, run `legistar.py --client <name>`. Other agenda vendors
   (BoardDocs, Diligent, CivicPlus) each need a module in `pipeline/sources/` that
   outputs the same shape.
3. Add campaign finance and Form 1 disclosure modules so the Pocket or Public
   score can fill in.

## Rules for linking donors to votes

- **Named**: the donor's exact name appears in the agenda item. Counts in Money timing when the gift is within 90 days of the vote.
- **Linked by records**: state business records tie the donor to the named company (same address or officers). Shown, not scored.
- **Possible link**: names look related but no record confirms it (example: a PAC named like a firm). Labeled Unverified.
- **Industry**: the vote regulates the donor's industry without naming it (example: towing rates). Shown, not scored.
- Name matches alone never link: "Hubbard's Sea Adventures" is not "Hubbard Construction Company."

## What's next

- Form 6 contents (income sources, assets) by public records request; the state search shows filing dates only.
- City councils and school board votes (BoardDocs, Diligent and city Legistar sites).
- District boundary files for address lookup and maps.
- Social post archiving for confirmed official accounts.
- A nightly scheduled run of the pulls on the Mac mini.
