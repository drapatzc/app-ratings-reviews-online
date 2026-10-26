  // Offizielle Store-Kennzahlen, Datenvollständigkeit und erster Aufruf von render().
  // ---- Offizielle Kennzahlen und Einschränkungen (folgen Kunde, App, Plattform aus dem Filter oben) ----
  function renderOfficial(target) {
    const latest = new Map();
    for (const x of DATA.ratings.filter(x => x.origin === "store-official" && inScope(x))) latest.set(x.customerId + "/" + x.appId + "/" + x.country, x);
    const box = target || $("official"); box.replaceChildren();
    if (!latest.size) { put(box, h("div", { class: "muted" }, tx("Keine offiziellen Store-Gesamtbewertungen erfasst (Apple: ratingCountries in der Konfiguration; Google bietet keine solche API).", "No official store ratings captured (Apple: ratingCountries in the configuration; Google offers no such API).")), h("div", { class: "note" }, tx("Alle Durchschnittswerte oben sind aus den erfassten Rezensionen berechnet und nicht identisch mit der Store-Gesamtbewertung.", "All averages above are calculated from the collected reviews and are not the official store rating."))); return; }
    const all = [...latest.values()], rated = all.filter(x => x.total > 0).sort((a, b) => b.total - a.total), hidden = all.length - rated.length;
    if (!rated.length) { put(box, h("div", { class: "muted" }, tx("Der Store meldet für die konfigurierten Länder noch keine Bewertungen.", "The store reports no ratings yet for the configured countries."))); return; }
    // Zeitraum aus dem Filter: zusätzliche Spalten „neu im Zeitraum“ aus den gespeicherten Store-Ständen (storeChange)
    const per = state.f.from || state.f.to, snapsOf = x => DATA.ratings.filter(y => y.origin === "store-official" && y.customerId === x.customerId && y.appId === x.appId && y.country === x.country)
      .sort((a, b) => (a.capturedAt || "") < (b.capturedAt || "") ? -1 : 1);
    const chg = new Map(per ? rated.map(x => [x, storeChange(snapsOf(x), state.f.from || "", state.f.to || "")]) : []);
    const anyPartial = [...chg.values()].some(c => c && c.partial), firstDay = [...chg.values()].filter(c => c && c.partial).map(c => c.since).sort()[0];
    if (per) put(box, h("div", { class: "warn", style: "margin-top:0" }, tx("Apple nennt nur die Gesamtzahl seit Erscheinen der App. Die Spalten „gesamt“ folgen deshalb nicht dem Zeitraum. Die Spalten „neu im Zeitraum“ sind aus den gespeicherten Store-Ständen berechnet", "Apple only reports the total since the app was released, so the “total” columns do not follow the period. The “new in period” columns are calculated from the stored store snapshots")
      + (anyPartial ? tx(", die erst seit " + fmtDay(firstDay) + " aufgezeichnet werden. Für die Zeit davor gibt es keine Zahlen.", ", which have only been recorded since " + fmtDay(firstDay) + ". There are no figures for the time before.") : ".")));
    const chgCells = x => { if (!per) return []; const c = chg.get(x); if (!c) return [h("td", { class: "muted" }, "–"), h("td", { class: "muted" }, "–")];
      const tip = c.partial ? tx("seit Beginn der Aufzeichnung am ", "since recording began on ") + fmtDay(c.since) : tx("seit ", "since ") + fmtDay(c.since);
      return [h("td", { class: "num", "data-tip": c.delta < 0 ? tip + tx(" · Apple hat Bewertungen entfernt", " · Apple removed ratings") : tip }, (c.delta > 0 ? "+" : "") + fmtInt(c.delta) + (c.partial ? " *" : "")),
        h("td", { class: "num" }, c.avg === null ? h("span", { class: "muted" }, "–") : fmt(c.avg))]; };
    const heads = ["App", tx("Land", "Country"), tx("Ø Sterne gesamt", "Avg stars total"), tx("Bewertungen gesamt", "Ratings total")]
      .concat(per ? [tx("Neu im Zeitraum", "New in period"), tx("Ø der neuen", "Avg of new")] : [], [tx("Erfasst am", "Captured at")]);
    put(box, h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, heads.map(t => h("th", {}, t)))),
      h("tbody", {}, rated.map(x => h("tr", {}, h("td", {}, h("b", {}, x.appName)), h("td", {}, x.country), h("td", {}, h("span", { class: "row", style: "gap:.5rem" }, starsSvg(x.average, 14), fmt(x.average))), h("td", { class: "num" }, fmtInt(x.total || 0)), chgCells(x), h("td", { class: "num" }, fmtDate(x.capturedAt))))))),
      per && anyPartial ? h("div", { class: "note" }, tx("* nur seit Beginn der Aufzeichnung am ", "* only since recording began on ") + fmtDay(firstDay) + tx(", nicht für den ganzen Zeitraum.", ", not for the whole period.")) : null,
      hidden ? h("div", { class: "note" }, hidden + tx(" App/Land-Kombinationen ohne Bewertungen sind ausgeblendet.", " app/country combinations without ratings are hidden.")) : null);
    if (!target) sortTables(box, "official");
  }
  function renderLimits(target) {
    const box = target || $("limits"); box.replaceChildren();
    put(box, h("ul", { style: "margin:0 0 1rem;padding-left:1.2rem" }, (DATA.limitations[LANG] || DATA.limitations.de || []).map(t => h("li", { style: "margin:.3rem 0" }, t))));
    put(box, h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, ["App", tx("Plattform", "Platform"), tx("Datensätze", "Records"), "Status", tx("Letzter Erfolg", "Last success"), tx("Hinweis", "Note")].map(t => h("th", {}, t)))),
      h("tbody", {}, DATA.apps.filter(inScope).map(a => h("tr", {}, h("td", {}, a.appName), h("td", {}, plat(a.platform)), h("td", { class: "num" }, fmtInt(a.reviewCount)), h("td", { class: a.status === "ok" ? "yes" : "no" }, a.status), h("td", { class: "num" }, fmtDate(a.lastSuccessfulSync)),
        h("td", {}, a.lastError ? tx("Fehler: ", "Error: ") + a.lastError : (a.dataGaps.length ? tx("Mögliche Datenlücken: ", "Possible data gaps: ") + a.dataGaps.map(g => fmtDate(g.from) + " – " + fmtDate(g.to)).join("; ") : ""))))))));
    if (!target) sortTables(box, "limits");
  }
  render();
