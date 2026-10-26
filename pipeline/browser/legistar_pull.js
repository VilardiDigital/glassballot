// Run on https://webapi.legistar.com/v1/pinellas/bodies (same-origin fetches).
// Pulls every BCC meeting since the current board was seated, every acted-on item and its roll call.
(async () => {
  const SINCE = "2024-11-19", BODIES = [213, 212]; // 213 = Board of County Commissioners, 212 = special sessions
  const get = async u => { for (let a = 0; a < 3; a++) { try { const r = await fetch(u); if (r.ok) return r.json(); } catch {} await new Promise(s => setTimeout(s, 800 * (a + 1))); } return null; };
  const q = encodeURIComponent(`(${BODIES.map(b => `EventBodyId eq ${b}`).join(" or ")}) and EventDate ge datetime'${SINCE}'`);
  const events = (await get(`/v1/pinellas/events?$filter=${q}&$orderby=EventDate desc`)) || [];
  const out = [];
  for (const e of events.filter(e => e.EventMinutesStatusName !== "Hidden")) {
    const items = (await get(`/v1/pinellas/events/${e.EventId}/eventitems?AgendaNote=1&MinutesNote=1`)) || [];
    const acted = items.filter(i => i.EventItemPassedFlag !== null || i.EventItemActionName);
    for (const i of acted) i._votes = ((await get(`/v1/pinellas/eventitems/${i.EventItemId}/votes`)) || []).map(v => [v.VotePersonName, v.VoteValueName]);
    out.push({ id: e.EventId, date: e.EventDate.slice(0, 10), url: e.EventInSiteURL, items: acted.map(i => ({
      id: i.EventItemId, file: i.EventItemMatterFile, title: i.EventItemTitle, action: i.EventItemActionName, passed: i.EventItemPassedFlag,
      tally: i.EventItemTally, mover: i.EventItemMover, seconder: i.EventItemSeconder, minutes: i.EventItemMinutesNote, votes: i._votes })) });
  }
  window.__legistar = out;
  console.log(`Pulled ${out.length} meetings, ${out.reduce((n, e) => n + e.items.length, 0)} items. Copy with: copy(JSON.stringify(window.__legistar))`);
})();
