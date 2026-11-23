# Glass Ballot: purpose, rules and backlog

This file is the standing brief for whoever works on Glass Ballot next, including the weekly automatic check-in.
Read it first. Work the backlog from the top, tick items off here, and add what you find.

## What the site is for

Glass Ballot (glassballot.org) is a free, nonpartisan guide to Florida local government. It started from a simple
problem: most people vote for county commission and school board without knowing who the candidates are or what
the job does, and only find out what they decided a year later from a headline about taxes or a school closing.

The goal is to make every Florida race, big and small, understandable in plain English: who holds each seat, how they
vote, who funds them, what they promised, and whether they kept it. Florida first (all 67 counties, statewide,
Congress, Legislature, county, city, special districts, ballot questions), then other states.

Between elections the site is an accountability record: how officials vote and whether they keep campaign promises.
Around elections it is a ballot guide, then a results guide.

## Rules that never bend

- Nonpartisan. Never recommend, rank or favor a candidate, party or position. Treat every side the same.
- Every fact has a source, labeled by tier (government record first). A candidate's own claim is shown as a claim.
- Never call a race. Show the county's count, say "unofficial" until certified, and show a projected winner only when
  a named news organization has called it, and say who.
- Never get around a site's bot protection. If a source blocks automated requests, read it in a browser and save it
  with a script (see tools/import_clarity.py), or find another official copy.
- Corrections are public: every change to a fact is listed on /corrections.
- Who runs the site stays citizen-anonymous in public. No names, no agency branding.
- Costs stay at zero: Cloudflare Pages free plan (500 builds a month; we use about 3 a day), GitHub Actions on a
  public repo (free), Web3Forms free plan (250 reports a month), GoatCounter. Don't add anything that bills.
- Never send email from any automated job. Reports to the owner go by app notification.

## How it runs (no one needs to touch it)

- `.github/workflows/refresh.yml`: every night at 5:17 am Eastern, pulls official records, rebuilds, commits.
- `.github/workflows/results.yml`: twice a day through Nov 30, 2026, pulls election results.
- Cloudflare Pages deploys `dist/` on every push to `main` (project "glassballot", Atlas Cloudflare account).
- The report-a-mistake form sends to glassballotinfo@gmail.com through Web3Forms.
- From the day after Election Day the site reads as a results guide (`after()` in site/template.html, `_after()` in
  pipeline/dist.py). Certified winners become "in office" on the term start date (Nov 17, 2026; s. 100.041).

## Backlog, most important first

### Now (November 2026)

- [ ] **Certification.** County official returns were due by noon Mon Nov 16; the state commission certified Nov 17.
      Done Nov 23: the results reader only looked at page headings, but most counties write "Official Results" in a
      message box under the summary (id="BottomMessage"). It now reads that box too (any "unofficial" there wins), so
      31 counties read official on their own, plus Pinellas (Clarity, set by hand) and Lake (its box says the
      canvassing board filed official results Nov 13; `"certified": true` in data/enr_ids.json). 41 winners were
      seated; logged on /corrections. Still "unofficial" because their pages say nothing either way (or Baker, which
      still says "UNOFFICIAL"): alachua, baker, bay, bradford, calhoun, charlotte, columbia, desoto, escambia,
      franklin, gadsden, gilchrist, glades, gulf, hardee, hendry, highlands, holmes, lafayette, lee, liberty,
      okeechobee, pasco, sarasota, seminole, suwannee, union, wakulla, walton, washington. For each, confirm on the
      county Supervisor of Elections' own site (canvass/certification notice or official results PDF), then set
      `"certified": true` with a `certifiedNote` naming the source. Pasco first (Tampa Bay).
- [x] **Pinellas School Board D3 recount.** No recount: Dawn Peters told the elections office she would not contest
      (Tampa Bay Times, Nov 4). The race page now says so. Official margin: 751 votes (0.21%).
- [x] **Seats missing from county results (14).** All 14 were settled in the Aug 18 primary. Winners and sources
      (each county's primary results on enr.electionsfl.org) are in data/decided_2026.json, which pipeline/bootstrap.py
      applies on every nightly rebuild, so the automatic counties keep them. Logged on /corrections.
- [ ] **Results readers for 5 counties** whose results sites we can't read yet: broward, escambia, martin, osceola,
      volusia. Find each Supervisor of Elections' results system and add it to data/enr_ids.json and
      pipeline/sources/results.py.

- [ ] **Write-in candidates on race pages.** Hernando County Commission D4 lists Donald Bigelow as a candidate, but
      the county reports his votes only as "Write-in" (11.8%), so his row shows no votes. Show write-in candidates'
      votes under their own name when the county lists them as write-ins, or label the row "Write-in (Donald Bigelow)"
      only if the county's own report says so. Check other counties for the same pattern.
- [x] **GitHub Actions on Node 20 is deprecated.** Done Nov 16: all five workflows moved from checkout@v4 and
      setup-python@v5 to checkout@v6 and setup-python@v6 (Node 24). Check the next runs no longer warn.
- [ ] **State district results file won't download.** Since at least Nov 9, flelectionfiles.floridados.gov fails TLS
      ("certificate has expired", now "self-signed certificate in certificate chain"), so data/results/districts.json
      is frozen at its last good pull. That's the state's problem; never turn off certificate checks. Find another
      official copy (the floridaelectionwatch.gov Downloads page, or the certified file after Nov 17) or wait it out.

### Next (December 2026 to spring 2027)

- [ ] **Promise tracker.** For each official, list campaign promises (already in seed data for the Tampa Bay four) and
      track each one against real votes: kept, broken, in progress, no action yet. Sourced, never our opinion.
- [ ] **Deep data beyond Tampa Bay.** Campaign money and plain-English vote summaries for counties that already have
      Legistar vote records: brevard, broward, charlotte, desoto, marion, martin, polk, seminole.
- [ ] **More offices.** State House, State Senate and mayors, as the owner asked.
- [ ] **Results share cards** for social posts (static images only, brand name a little lower in frame on TikTok).
- [ ] **README** still describes the Pinellas pilot. Rewrite it for the statewide site.

### Later

- [ ] 2027 municipal elections calendar for cities that vote in odd years.
- [ ] Expand to other states once Florida is complete.

## Check-in log

Each weekly check-in adds one short dated line here: what it checked, what it fixed, what needs the owner.

- 2026-11-04: Moved hosting from Netlify to Cloudflare Pages (free). Turned on the report form. Site switched to
  results mode. Pinellas general results added (browser import; site blocks GitHub). D6 seat-name bug fixed.
- 2026-11-09: All nightly and results runs green Nov 2 to 8 (only expected "pinellas pull failed"; GitHub blocked).
  Live site loads, Hillsborough/Pasco/Hernando updated Nov 8. Re-imported Pinellas (late ballots, no leader changes)
  and noted the D3 recount was declined. Marked 14 seats settled in the August primary. Oct builds: about 93.
  Sent one labeled test through the report form; it reached the inbox. Privacy page now says Web3Forms passes
  along the sender's IP address, and the report email shows a readable "opened" time.
- 2026-11-16: All nightly and results runs green Nov 9 to 16 (Nov 16 nightly not yet run at check time); one Nov 11 results run is stuck "queued" (harmless).
  Expected "pinellas pull failed" plus a new "districts pull failed": the state's flelectionfiles.floridados.gov has a
  bad TLS certificate on their side, so the last good districts file stays. Live site loads, Hillsborough results
  updated Nov 15. Pinellas imported as official (SB D3 margin 751). Bumped Actions to Node 24 versions. Nov builds so
  far: 112 (on pace for about 210).
- 2026-11-23: All nightly and results runs green Nov 16 to 23 (Nov 23 nightly not yet run at check time). Expected
  "districts pull failed" (state TLS) only. Found most counties' "Official Results" sat in a box the reader skipped;
  fixed it, so 33 counties now read official and 41 certified winners are seated (Hillsborough, Hernando and others).
  30 counties still need certification confirmed by hand. Oct builds: 93; Nov so far: 136.
