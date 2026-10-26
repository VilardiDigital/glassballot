# Browser pulls

Some public record sites only answer from a normal browser. These scripts were run
in the browser console (or the Claude app's built-in browser) on Oct 26, 2026 to build
the files in `data/`. Paste each one into the console while on the named site.

| Script | Run on | Produces |
| --- | --- | --- |
| `legistar_pull.js` | https://webapi.legistar.com/v1/pinellas/bodies | Every agenda item and roll call since Nov 19, 2024, then a summary for `data/legistar_pinellas_summary.json` |
| `voterfocus_pull.js` | https://www.voterfocus.com/CampaignFinance/candidate_pr.php?c=Pinellas | Itemized contributions per candidate, totals, top donors, shared donors |
| Ethics filings | https://disclosure.floridaethics.gov/PublicSearch/Filings | `fetch('/api/PublicFiling/SearchPublicFilers?filterByFirstName=..&filterByLastName=..&filterByFormYear=2025&pageSize=25&pageNumber=1&sortColumn=fullName&sortDirection=ASC')` returns filing dates |

The Python client in `pipeline/sources/legistar.py` does the Legistar pull directly
from any machine with normal internet, no browser needed.
