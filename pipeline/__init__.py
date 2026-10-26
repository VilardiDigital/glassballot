"""Glass Ballot data pipeline.

Pulls public records, labels every fact by how well its sources agree,
and writes the JSON the Glass Ballot site reads. Standard library only.
"""

LABELS = ("verified", "single", "unverified", "conflict", "unknown")

# Source tiers (lower number = stronger). See the plan doc, "Verification engine".
TIER_LEGAL_RECORD = 1      # approved minutes, filed reports, certified results, official county pages
TIER_OFFICIAL_SECONDARY = 2  # meeting video, agenda packets, government press releases
TIER_DATA_GROUP = 3        # LegiScan, Ballotpedia, Ballot Brief, Wikipedia
TIER_JOURNALISM = 4        # news outlets, meeting-summary services
TIER_SELF_REPORTED = 5     # candidate sites, posts, questionnaires
