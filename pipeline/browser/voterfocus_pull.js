// Run on https://www.voterfocus.com/CampaignFinance/candidate_pr.php?c=Pinellas
// Downloads each candidate's itemized report export and parses it.
// Find account ids (ca=...) by hovering a candidate's row on that page.
(async () => {
  const ACCOUNTS = { scott: 1174, peters: 1177, eggers: 1182, hughes: 1208, glenn: 1186, campogni: 1180, dpeters: 1181,
                     scherer: 1118, nowicki: 1122, flowers: 1121, latvala: 1098 };
  const parse = t => { const rows = []; let row = [], f = "", q = false;
    for (let i = 0; i < t.length; i++) { const c = t[i];
      if (q) { if (c === '"') { if (t[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
      else if (c === '"') q = true; else if (c === ",") { row.push(f); f = ""; } else if (c === "\n") { row.push(f); rows.push(row); row = []; f = ""; } else if (c !== "\r") f += c; }
    if (f || row.length) { row.push(f); rows.push(row); }
    const h = rows.shift(); return rows.filter(r => r.length > 5).map(r => Object.fromEntries(h.map((k, j) => [k.trim(), (r[j] || "").trim()]))); };
  const out = {};
  for (const [id, ca] of Object.entries(ACCOUNTS)) {
    const t = await (await fetch(`/CampaignFinance/export.php?op=CFINANCE&cand_id=${ca}&dhc=0&county=pinellas`)).text();
    // Keep contributions; drop lines the filer marked deleted (Amend. code "D").
    out[id] = parse(t).filter(r => r["Cont/Exp"] === "C" && r["Amend. code"] !== "D")
      .map(r => ({ date: r["item date"], name: r.name.replace(/\s+/g, " "), city: r.city, state: r.state, zip: r.zip, type: r["cont. type"], occupation: r.occupation, item: r["item type"], amount: +r.amount }));
  }
  window.__contributions = out;
  console.log("Done. Copy with: copy(JSON.stringify(window.__contributions))  (street addresses are dropped on purpose)");
})();
