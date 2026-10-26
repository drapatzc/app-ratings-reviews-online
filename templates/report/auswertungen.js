  // Auswertungen und render() (zeichnet alle Bereiche neu): neueste Version, wichtigste Zahlen je App, Überblick mit Ampel, Vergleich nach Version, Updates, Themen, Antworten.
  // ---- Neueste Store-Version (abhängig von Kunde, App, Plattform) ----
  function renderLatest(target) {
    const box = target || $("latestout"), latest = new Map();
    for (const x of DATA.ratings.filter(x => x.origin === "store-official" && x.appVersion)) {
      if (!inScope(x)) continue;
      const k = x.customerId + "/" + x.appId + "/" + x.platform, cur = latest.get(k);
      if (!cur || x.capturedAt > cur.capturedAt) latest.set(k, x);
    }
    box.replaceChildren();
    if (!latest.size) { put(box, h("div", { class: "muted" }, tx("Für diese Auswahl ist keine Store-Version erfasst (nur Apple liefert sie über die öffentliche Bewertungsübersicht).", "No store version captured for this selection (only Apple provides it via the public rating summary)."))); return; }
    const rows = [...latest.values()].sort((a, b) => a.appName.localeCompare(b.appName, "de"));
    put(box, h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, ["App", tx("Plattform", "Platform"), tx("Version im Store", "Version in store"), tx("Erfasst am", "Captured at")].map(t => h("th", {}, t)))),
      h("tbody", {}, rows.map(x => h("tr", {}, h("td", {}, h("b", {}, x.appName)), h("td", {}, plat(x.platform)), h("td", { class: "num" }, x.appVersion), h("td", { class: "num" }, fmtDate(x.capturedAt))))))),
      null);
    if (!target) sortTables(box, "latest");
  }
  // Kennzahlen-Kacheln unter der Gesamtbewertung (Reiter Rezensionen); auch im Themen-Bericht zum Drucken
  function kpiTiles(st) {
    const since30 = daysBefore(asOfDate, 30);
    const recent = current.filter(r => (r.createdAt || "") >= since30).length;
    const lastSync = DATA.apps.map(a => a.lastSuccessfulSync).filter(Boolean).sort().pop();
    const periodSet = state.f.from || state.f.to;
    const kp = (value, label) => { const b = h("b", { class: "num" }, typeof value === "number" ? fmtInt(value) : value); if (typeof value !== "number") b.style.fontSize = "1.2rem"; return h("div", { class: "card kpi" }, b, h("span", {}, label)); };
    return [kp(st.count, tx("Rezensionen (gefiltert)", "reviews (filtered)")), kp(st.pos, tx("positiv (4–5 ★)", "positive (4–5 ★)")), kp(st.neg, tx("negativ (1–2 ★)", "negative (1–2 ★)")),
      kp(st.noReply, tx("ohne Entwicklerantwort", "without developer reply")), kp(periodSet ? current.length : recent, periodSet ? tx("neu im gewählten Zeitraum", "new in the selected period") : tx("neu in den letzten 30 Tagen", "new in the last 30 days")),
      kp(lastSync ? (LANG === "de" ? lastSync.slice(8, 10) + "." + lastSync.slice(5, 7) + "." + lastSync.slice(0, 4) : lastSync.slice(0, 10)) : "–", tx("letzter erfolgreicher Abruf", "last successful fetch") + (lastSync ? " · " + lastSync.slice(11, 16) + " UTC" : "")),
      ...kiTiles(current)];
  }
  function render() {
    current = applyFilters(reviews, state.f);
    const st = stats(current);
    const pool = reviews.filter(r => !rivalHidden(r, state.f)).length;  // Wettbewerber zählen nur, wenn sie gewählt sind
    $("count").textContent = fmtInt(current.length) + tx(" von ", " of ") + fmtInt(pool) + tx(" Rezensionen entsprechen den Filtern", " reviews match the filters");
    renderChips(); renderScore(st); renderLatest(); renderOfficial(); renderLimits(); renderStability();
    $("kpis").replaceChildren(...kpiTiles(st));
    renderKiStrip(current);
    renderCharts();
    renderOverview(); renderQuestions(); renderAppCompare(); renderProfile(); renderCompare(); renderRelease(); renderTopics(); renderReplies();
    renderKi();
    renderRivals();
    renderTable();
    // Kopfzeile: Stand der Abrufe (grün = alle Ziele ok, rot = Fehler; Einzelheiten unter „Wie vollständig sind die Daten?“)
    const failed = DATA.apps.filter(a => a.status !== "ok"), fb = $("fetchbadge");
    fb.className = "pill " + (failed.length ? "r1" : "r5");
    fb.textContent = failed.length ? failed.length + tx(failed.length === 1 ? " Abruf fehlgeschlagen" : " Abrufe fehlgeschlagen", failed.length === 1 ? " fetch failed" : " fetches failed") : tx("alle Abrufe erfolgreich", "all fetches successful");
    if (failed.length) fb.setAttribute("data-tip", failed.map(a => a.appName + " (" + platName(a.platform) + ")").join(", ")); else fb.removeAttribute("data-tip");
  }
  const kpTile = (value, label, tip) => { const b = h("b", { class: "num" }, typeof value === "number" ? fmtInt(value) : value); if (typeof value !== "number") b.style.fontSize = "1.2rem"; return h("div", Object.assign({ class: "card kpi" }, tip ? { "data-tip": tip } : {}), b, h("span", {}, label)); };
  const smallMark = n => n < SMALL ? " ⚠" : "";
  const deltaPill = (d, step, digits) => { if (d === null) return h("span", { class: "muted" }, "–"); const cls = d >= step ? "r5" : d <= -step ? "r1" : "r3"; return h("span", { class: "pill " + cls }, (d > 0 ? "▲ +" : d < 0 ? "▼ " : "• ") + fmt(d, digits)); };
  const pct = v => v === null ? "–" : fmt(v, 0) + " %";
  const windowOf = () => { const f = state.f.from || "", t = state.f.to || ""; return f || t ? { from: f, to: t, label: tx("im Zeitraum", "in the period") } : { from: daysBefore(asOfDate, 90), to: "", label: tx("letzte 90 Tage", "last 90 days") }; };
  const inWin = (d, w) => (d || "") >= w.from && (!w.to || (d || "").slice(0, 10) <= w.to);
  const appLabel = a => custIds.length > 1 ? a.customerName + " · " + a.appName : a.appName;

  // ---- Steckbrief: eine Zeile je App in der Auswahl; Kennzahlen aus den gefilterten Rezensionen ----
  function renderProfile() {
    const box = $("steckout"); box.replaceChildren();
    const byKey = groupBy(current, r => r.customerId + "/" + r.appId + "/" + r.platform), win = windowOf();
    const prior = { apple: stats(reviews.filter(r => r.platform === "apple")).avg, google: stats(reviews.filter(r => r.platform === "google")).avg };
    const dl = new Map();  // Erstinstallationen je App im Fenster (nur Apple)
    for (const x of DATA.storeMetrics || []) { let n = 0; for (const r of x.downloads) if (r[1] === "First-time download" && inWin(r[0], win)) n += r[5]; dl.set(appKeyOf(x) + "/" + x.platform, n); }
    const rows = DATA.apps.filter(inScope).map(a => {
      const key = a.customerId + "/" + a.appId + "/" + a.platform, rs = byKey.get(key) || [], st = stats(rs), rec = rs.filter(r => inWin(r.createdAt, win)), rst = stats(rec);
      const sum = rs.reduce((s, r) => s + (r.rating >= 1 && r.rating <= 5 ? r.rating : 0), 0), d = dl.get(key);
      return { a, st, rst, bayes: bayesAvg(sum, st.rated, prior[a.platform]), ci: ciHalf(rs), net: netScore(st), one: st.rated ? 100 * st.dist[1] / st.rated : null,
        complaints: d > 0 ? 1000 * rst.neg / d : null, downloads: d === undefined ? null : d, replyRate: st.count ? 100 * (st.count - st.noReply) / st.count : null, prior: prior[a.platform],
        churn: kiChurnOn() ? kiChurnShare(rec) : null };
    }).filter(x => x.st.rated).sort((x, y) => y.bayes - x.bayes);
    if (!rows.length) { put(box, noData()); return; }
    const both = new Set(rows.map(x => x.a.platform)).size > 1, churnCol = kiChurnOn();
    const head = [tx("Rang", "Rank"), "App", both ? tx("Plattform", "Platform") : null, tx("Rezensionen", "Reviews"), tx("Faire Note", "Fair rating"), tx("Zufrieden minus unzufrieden", "Happy minus unhappy"),
      tx("Ø ", "avg ") + win.label + tx(" vs. gesamt", " vs. total"), tx("Anteil 1 ★", "Share 1 ★"), tx("Beschwerden je 1000 Downloads", "Complaints per 1,000 downloads"), tx("Antwortquote", "Reply rate"),
      churnCol ? tx("Drohen zu wechseln (KI)", "Threaten to leave (AI)") : null].filter(Boolean);
    put(box, h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, head.map(t => h("th", {}, t)))),
      h("tbody", {}, rows.map((x, i) => { const small = x.st.rated < SMALL, netCls = x.net >= 20 ? "r5" : x.net < 0 ? "r1" : "r3";
        return h("tr", { class: small ? "pale" : "" },
          h("td", { class: "num" }, String(i + 1)), h("td", { class: "nw" }, h("b", {}, appLabel(x.a))), both ? h("td", {}, plat(x.a.platform)) : null,
          h("td", { class: "num" }, fmtInt(x.st.rated) + smallMark(x.st.rated)),
          h("td", { class: "num", "data-tip": tx("Roher Durchschnitt ", "Plain average ") + fmt(x.st.avg) + tx(" · Vergleichsmittel ", " · reference mean ") + fmt(x.prior) + " (" + platName(x.a.platform) + ")" + tx(" · 10 Pseudostimmen", " · 10 pseudo-votes") }, h("b", {}, fmt(x.bayes)), x.ci !== null ? h("span", { class: "muted" }, " ± " + fmt(x.ci, 1)) : null),
          h("td", {}, h("span", { class: "pill " + netCls, "data-tip": x.st.pos + tx(" positiv, ", " positive, ") + x.st.neg + tx(" negativ", " negative") }, (x.net > 0 ? "+" : "") + fmt(x.net, 0))),
          h("td", { "data-tip": fmt(x.rst.avg) + " (" + x.rst.rated + ")" + tx(" gegen ", " vs. ") + fmt(x.st.avg) + " (" + x.st.rated + ")" }, x.rst.rated >= 3 ? deltaPill(x.rst.avg - x.st.avg, .2, 2) : h("span", { class: "muted" }, "–")),
          h("td", { class: "num" }, pct(x.one)),
          h("td", { class: "num", "data-tip": x.downloads === null ? tx("keine Download-Daten", "no download data") : x.rst.neg + tx(" negative Rezensionen auf ", " negative reviews on ") + fmtInt(x.downloads) + tx(" Erstinstallationen ", " first-time downloads ") + win.label }, x.complaints === null ? "–" : fmt(x.complaints, 1)),
          h("td", { class: "num" }, pct(x.replyRate)),
          churnCol ? h("td", { class: "num", "data-tip": x.churn ? fmtInt(x.churn.n) + tx(" von " + fmtInt(x.churn.of) + " analysierten Rezensionen " + win.label + " kündigen Wechsel oder Löschen an", " of " + fmtInt(x.churn.of) + " analysed reviews " + win.label + " announce leaving or deleting") : tx("keine analysierten Rezensionen im Zeitraum", "no analysed reviews in the period") }, x.churn ? h("span", { class: "pill " + (x.churn.share >= 20 ? "r1" : x.churn.share >= 10 ? "r3" : "r5") }, fmt(x.churn.share, 0) + " %") : h("span", { class: "muted" }, "–")) : null); })))),
      h("div", { class: "note" }, tx("Blass und ⚠: unter " + SMALL + " Rezensionen, Werte nicht belastbar. Rang nach fairer Note; Klick auf eine Spalte sortiert." + (churnCol ? " Drohen zu wechseln: Anteil der von der KI analysierten Rezensionen im Zeitraum mit angekündigtem Wechsel oder Löschen (rot ab 20 %)." : ""),
        "Pale and ⚠: fewer than " + SMALL + " reviews, values not reliable. Rank by fair rating; click a column to sort." + (churnCol ? " Threaten to leave: share of AI-analysed reviews in the period announcing leaving or deleting (red from 20 %)." : ""))));
    sortTables(box, "profile");
  }

  // ---- Überblick: drei Antwortkarten und Ampel je App. Feste Fenster ab Datenstand (30 Tage, 7 Tage, 14 Tage je Update),
  // unabhängig vom Zeitraum im Filter; Kunde, App und Plattform gelten. Rezensionen ohne Sternefilter (reviews.filter(inScope)).
  // Die Ampel selbst (Stufe und Gründe) rechnet src/metrics.py beim Erzeugen und legt sie als DATA.ampel ab; dieselben Regeln
  // nutzen die Markdown-Zusammenfassungen. Fenster und Faktoren kommen als DATA.ampelRules (metrics.AMPEL) mit.
  const OV = Object.assign({ days: 30, negDays: 7, minRate: 1, doubled: 2, raised: 1.5, win: 14, cmpStep: .2, hideGreenFrom: 4 }, DATA.ampelRules || {});
  const reasonText = x => x.code === "neg" ? x.count + tx(" × 1–2 ★ in " + x.days + " Tagen", " × 1–2 ★ in " + x.days + " days")
    : x.code === "open" ? x.count + tx(" ohne Antwort", " without reply")
    : x.code === "crash" ? tx("Abstürze ", "crashes ") + fmt(x.rate) + tx(" je 1000", " per 1,000")
    : x.code === "crashUp" ? tx("Abstürze ", "crashes ") + fmt(x.before) + " → " + fmt(x.rate)
    : tx("Store unter " + x.stars + " ★", "store below " + x.stars + " ★");
  const dayOf = r => (r.createdAt || "").slice(0, 10);
  function overviewRows() {
    const d30 = daysBefore(asOfDate, OV.days), d60 = daysBefore(asOfDate, 2 * OV.days), d7 = daysBefore(asOfDate, OV.negDays), d28 = daysBefore(asOfDate, 28);
    const inSc = reviews.filter(inScope);
    return DATA.apps.filter(a => inScope(a) && !a.competitor).map(a => {  // Ampel und Maßnahmen nur für eigene Apps
      const key = appKeyOf(a), rs = inSc.filter(r => appKeyOf(r) === key && r.platform === a.platform);
      const last = rs.filter(r => dayOf(r) >= d30), negRecent = rs.filter(r => r.rating <= 2 && dayOf(r) >= d7), openNeg = last.filter(r => r.rating <= 2 && !hasReply(r));
      const snaps = new Map();  // jüngster Store-Stand je Land; angezeigt wird das Land mit den meisten Bewertungen
      for (const x of DATA.ratings) if (x.origin === "store-official" && appKeyOf(x) === key && x.platform === a.platform && x.total > 0) { const c = snaps.get(x.country); if (!c || x.capturedAt > c.capturedAt) snaps.set(x.country, x); }
      const store = [...snaps.values()].sort((x, y) => y.total - x.total)[0] || null;
      const st = (DATA.stability || []).find(x => appKeyOf(x) === key && x.platform === a.platform);
      const rate = (f, t) => { if (!st) return null; return stabilityBy(st.crashes.filter(x => x[0] >= f && x[0] < t), st.sessions.filter(x => x[0] >= f && x[0] < t), () => "x")[0] || null; };
      const now = rate(d30, "9999"), prev = rate(d60, d30), enough = !!(now && now.sessions >= ZONE.minSessions && now.rate !== null);
      const sm = (DATA.storeMetrics || []).find(x => appKeyOf(x) === key && x.platform === a.platform);
      const dl = sm ? sm.downloads.filter(x => x[1] === "First-time download" && x[0] >= d28).reduce((s, x) => s + x[5], 0) / 4 : null;
      const amp = (DATA.ampel || {})[key + "/" + a.platform] || { level: 0, reasons: [] };  // 0 grün, 1 gelb, 2 rot
      const level = amp.level, why = amp.reasons.map(reasonText);
      return { a, key, last, lastSt: stats(last), negRecent, openNeg, store, now, prev, enough, dl, level, why };
    }).sort((x, y) => y.level - x.level || y.negRecent.length - x.negRecent.length || appLabel(x.a).localeCompare(appLabel(y.a), LANG));
  }
  const dot = lvl => h("i", { class: "dot " + (lvl === 2 ? "r" : lvl === 1 ? "y" : lvl === 0 ? "g" : "n"), "aria-hidden": "true" });
  const lvlName = lvl => lvl === 2 ? tx("rot", "red") : lvl === 1 ? tx("gelb", "yellow") : tx("grün", "green");
  function renderOverview() {
    const box = $("ovout"); box.replaceChildren();
    const rows = overviewRows();
    if (!rows.length) { put(box, noData()); return; }
    const d30 = daysBefore(asOfDate, OV.days), d60 = daysBefore(asOfDate, 2 * OV.days), inSc = reviews.filter(inScope);
    const ls = stats(inSc.filter(r => dayOf(r) >= d30)), ps = stats(inSc.filter(r => dayOf(r) >= d60 && dayOf(r) < d30));
    // Karte 1: Store-Note über alle Apps der Auswahl (gewichtet nach Bewertungen), Veränderung gegen den Stand vor 30 Tagen
    const weighted = xs => { let s = 0, n = 0; for (const x of xs) { s += x.average * x.total; n += x.total; } return n ? s / n : null; };
    const latestBy = new Map(), oldBy = new Map();
    for (const x of DATA.ratings) { if (x.origin !== "store-official" || !inScope(x) || !(x.total > 0)) continue; const k = appKeyOf(x) + "/" + x.platform + "/" + x.country;
      const c = latestBy.get(k); if (!c || x.capturedAt > c.capturedAt) latestBy.set(k, x);
      if ((x.capturedAt || "").slice(0, 10) <= d30) { const o = oldBy.get(k); if (!o || x.capturedAt > o.capturedAt) oldBy.set(k, x); } }
    const cur = weighted([...latestBy.values()]), pairs = [...oldBy.keys()].filter(k => latestBy.has(k));
    const delta = pairs.length ? weighted(pairs.map(k => latestBy.get(k))) - weighted(pairs.map(k => oldBy.get(k))) : null;
    const cmp = ls.rated >= 3 && ps.rated >= 3 ? (ls.avg - ps.avg >= OV.cmpStep ? tx("Besser als in den 30 Tagen davor.", "Better than in the 30 days before.") : ps.avg - ls.avg >= OV.cmpStep ? tx("Schlechter als in den 30 Tagen davor.", "Worse than in the 30 days before.") : tx("Etwa wie in den 30 Tagen davor.", "About the same as in the 30 days before."))
      : tx("Zu wenige Rezensionen für einen Vergleich mit den 30 Tagen davor.", "Too few reviews for a comparison with the 30 days before.");
    const months = []; for (let i = 11; i >= 0; i--) { const t = new Date(asOfDate + "T00:00:00Z"); t.setUTCDate(1); t.setUTCMonth(t.getUTCMonth() - i); months.push(t.toISOString().slice(0, 7)); }
    const byM = groupBy(inSc, monthKey), pts = months.map((m, i) => { const st = stats(byM.get(m) || []); return st.rated ? [i, st.avg, st.rated, m] : null; }).filter(Boolean);
    let spark = null;
    if (pts.length >= 2) {
      const Wd = 300, Hd = 44, x = i => 6 + i * (Wd - 12) / 11, y = v => 4 + (Hd - 8) * (1 - (v - 1) / 4);
      spark = s("svg", { class: "spark", viewBox: `0 0 ${Wd} ${Hd}`, preserveAspectRatio: "none", role: "img", "aria-label": tx("Ø Sterne der Rezensionen je Monat, letzte 12 Monate", "avg stars of reviews per month, last 12 months") });
      spark.append(s("polyline", { points: pts.map(p => x(p[0]) + "," + y(p[1])).join(" "), fill: "none", stroke: "var(--accent)", "stroke-width": 2, "vector-effect": "non-scaling-stroke" }));
      pts.forEach(p => spark.append(s("circle", { cx: x(p[0]), cy: y(p[1]), r: 3, fill: "var(--accent)", "data-tip": fmtMonth(p[3]) + ": " + fmt(p[1]) + " ★ (" + p[2] + ")" })));
    }
    const link = (text, f) => h("button", { type: "button", class: "linkbtn", onclick: f }, text + " ›");
    const card1 = h("div", { class: "ovcard" }, h("h3", {}, tx("Wie läuft es insgesamt?", "How is it going overall?")),
      h("div", { class: "big num" }, cur === null ? "–" : fmt(cur, 1), h("small", {}, cur === null ? tx("keine Store-Bewertung", "no store rating") : tx("★ im Store", "★ in the store")), delta !== null ? deltaPill(delta, .1, 1) : null),
      h("p", {}, tx("Letzte 30 Tage: ", "Last 30 days: "), h("b", {}, fmtInt(ls.rated)), tx(ls.rated === 1 ? " neue Rezension, " : " neue Rezensionen, ", ls.rated === 1 ? " new review, " : " new reviews, "), h("b", {}, fmtInt(ls.pos)), tx(" zufrieden, ", " happy, "), h("b", {}, fmtInt(ls.neg)), tx(" unzufrieden. ", " unhappy. "), cmp),
      spark, link(tx("Verlauf in den Diagrammen", "Trend in the charts"), () => setTab("charts")));
    // Karte 2: Apps mit Ampel rot oder gelb, höchstens drei
    const alerts = rows.filter(r => r.level > 0).slice(0, 3), greens = rows.filter(r => r.level === 0).length;
    const card2 = h("div", { class: "ovcard" }, h("h3", {}, tx("Was ist jetzt auffällig? (7 und 30 Tage)", "What stands out now? (7 and 30 days)")),
      h("ul", { class: "ovlist" }, alerts.map(r => h("li", {}, dot(r.level), h("div", {}, h("b", {}, appLabel(r.a)), h("span", {}, r.why.join(" · "))))),
        greens ? h("li", {}, dot(0), h("div", {}, h("b", {}, alerts.length ? greens + tx(greens === 1 ? " weitere App" : " weitere Apps", greens === 1 ? " more app" : " more apps") : greens + tx(greens === 1 ? " App" : " Apps", greens === 1 ? " app" : " apps")), h("span", {}, tx("keine Auffälligkeit", "nothing unusual")))) : null),
      link(tx("Alle Apps in der Tabelle unten", "All apps in the table below"), () => { const t = $("ovtable"); if (t && t.scrollIntoView) t.scrollIntoView({ block: "start" }); }));
    // Karte 3: jüngste Veröffentlichung in der Auswahl, 14 Tage davor und danach
    // Jüngste Veröffentlichung, zu der es Rezensionen oder Absturzdaten im Fenster gibt; sonst die jüngste überhaupt
    const rels = chartStores().flatMap(k => releaseList(k)).filter(r => r.date <= asOfDate).sort((a, b) => a.date < b.date ? 1 : -1);
    const hasData = r => { const key = appKeyOf(r.app), b = addDays(r.date, -OV.win), af = addDays(r.date, OV.win), st = (DATA.stability || []).find(x => appKeyOf(x) === key && x.platform === r.app.platform);
      return inSc.some(x => appKeyOf(x) === key && x.platform === r.app.platform && dayOf(x) >= b && dayOf(x) < af) || !!(st && st.sessions.some(x => x[0] >= b && x[0] < af)); };
    const rel = rels.find(hasData) || rels[0] || null;
    let card3;
    if (!rel) card3 = h("div", { class: "ovcard" }, h("h3", {}, tx("Was hat das letzte Update verändert?", "What did the latest update change?")), h("p", { class: "muted" }, tx("Keine Veröffentlichung in der Auswahl bekannt.", "No release known for the selection.")));
    else {
      const W = OV.win, d = rel.date, b = addDays(d, -W), af = addDays(d, W), key = appKeyOf(rel.app), rv = inSc.filter(x => appKeyOf(x) === key && x.platform === rel.app.platform);
      const before = stats(rv.filter(x => dayOf(x) >= b && dayOf(x) < d)), after = stats(rv.filter(x => dayOf(x) >= d && dayOf(x) < af));
      const st = (DATA.stability || []).find(x => appKeyOf(x) === key && x.platform === rel.app.platform);
      const rate = (f, t) => { if (!st) return null; const o = stabilityBy(st.crashes.filter(x => x[0] >= f && x[0] < t), st.sessions.filter(x => x[0] >= f && x[0] < t), () => "x")[0]; return o && o.rate !== null ? o.rate : null; };
      const rb = rate(b, d), ra = rate(d, af), sm = (DATA.storeMetrics || []).find(x => appKeyOf(x) === key && x.platform === rel.app.platform);
      const dlIn = (f, t) => sm ? sm.downloads.filter(x => x[1] === "First-time download" && x[0] >= f && x[0] < t).reduce((s, x) => s + x[5], 0) / (W / 7) : null;
      const db = dlIn(b, d), da = dlIn(d, af), elapsed = Math.round((Date.parse(asOfDate) - Date.parse(d)) / DAYMS);
      const crashLvl = rb === null && ra === null ? null : ra !== null && rb !== null && rb > 0 && ra >= OV.minRate && ra >= OV.doubled * rb ? 2 : ra !== null && rb !== null && rb > 0 && ra >= OV.minRate && ra >= OV.raised * rb ? 1 : 0;
      const revLvl = before.rated >= 3 && after.rated >= 3 ? (after.avg - before.avg <= -.3 ? 2 : after.avg - before.avg >= .3 ? 0 : null) : null;
      const item = (lvl, text, sub) => h("li", {}, dot(lvl), h("div", {}, h("b", {}, text), h("span", {}, sub)));
      card3 = h("div", { class: "ovcard" }, h("h3", {}, tx("Was hat das letzte Update verändert?", "What did the latest update change?")),
        h("div", { class: "big", style: "font-size:1.25rem" }, appLabel(rel.app) + " " + rel.version, h("small", {}, tx("seit ", "since ") + fmtDay(d) + (rel.exact ? "" : tx(" (geschätzt)", " (estimated)")))),
        h("ul", { class: "ovlist" },
          item(crashLvl, tx("Abstürze: ", "Crashes: ") + (rb === null ? "–" : fmt(rb)) + " → " + (ra === null ? "–" : fmt(ra)) + tx(" je 1000 Sitzungen", " per 1,000 sessions"), crashLvl === null ? tx("keine Absturzdaten", "no crash data") : W + tx(" Tage vor und nach dem Update", " days before and after the update")),
          item(revLvl, tx("Rezensionen: ", "Reviews: ") + fmt(before.avg) + " → " + fmt(after.avg) + " ★", after.rated + tx(after.rated === 1 ? " neue, davon " : " neue, davon ", " new, ") + after.neg + tx(" negativ", " negative") + (revLvl === null && !(before.rated >= 3 && after.rated >= 3) ? tx(" · zu wenige für einen Sterne-Vergleich", " · too few for a star comparison") : "")),
          db === null ? item(null, tx("Downloads: keine Daten", "Downloads: no data"), "") : item(null, tx("Downloads: ", "Downloads: ") + fmtInt(Math.round(db)) + " → " + fmtInt(Math.round(da)) + tx(" je Woche", " per week"), db > 0 ? (da >= db ? "+" : "") + fmt(100 * (da - db) / db, 0) + " %" : "")),
        elapsed < W ? h("p", { class: "muted" }, tx("Erst " + elapsed + " Tage seit dem Update; die Zeit danach ist noch unvollständig.", "Only " + elapsed + " days since the update; the time after is still incomplete.")) : null,
        link(tx("Alle Updates", "All updates"), () => { secState.more = true; saveSecs(); applyTabs(); const t = $("release"); if (t && t.scrollIntoView) t.scrollIntoView({ block: "start" }); }));
    }
    // Monatsbericht drucken / kopieren: gilt für den ganzen Überblick (drei Karten, Maßnahmen, Ampel), deshalb oben in der Karte
    // links neben dem Zuklappknopf (reportButtons in fragen.js, CSS .sec>.prbar); bei jeder Neuzeichnung neu, weil `rows` vom Filter abhängt
    reportButtons("ueberblick", PRINTERS.overview, tx("Monatsbericht drucken", "Print monthly report"));
    put(box, h("div", { class: "ovcards" }, card1, card2, card3), actionList(rows));
    // Ampeltabelle: unauffällige Apps ab OV.hideGreenFrom Stück zu einer Zeile zusammengefasst (state.showGreen blendet sie ein);
    // mit KI je App der Knopf „Was sagen die Nutzer?“ (öffnet ein Overlay); der Knopf „Monatsbericht drucken“ sitzt oben in der Karte neben dem Zuklappknopf
    const multi = custIds.length > 1, greenRows = rows.filter(r => r.level === 0), fold = greenRows.length >= OV.hideGreenFrom && !state.showGreen;
    const head = ["", "App", multi ? tx("Kunde", "Customer") : null, tx("Store ★", "Store ★"), tx("Neu (30 T.)", "New (30 d)"), tx("Abstürze / 1000", "Crashes / 1,000"), tx("Downloads / Woche", "Downloads / week"), tx("Warum", "Why")].filter(x => x !== null);
    const sumOf = new Map(rows.map(r => [r.key + "/" + r.a.platform, kiSummaryCell(r.a)]));
    const kiBtn = r => { const id = r.key + "/" + r.a.platform; if (!sumOf.get(id)) return null;
      return h("button", { type: "button", class: "linkbtn kiopen", "aria-haspopup": "dialog", onclick: e => { e.stopPropagation(); openKiDialog(tx("Was sagen die Nutzer?", "What do users say?"), r.a.appName + " · " + platName(r.a.platform), () => kiSummaryCell(r.a)); } }, tx("Was sagen die Nutzer?", "What do users say?"), " ", kiMark(), " ›"); };
    const rateCell = r => !r.now || r.now.rate === null ? h("td", { class: "num muted" }, "–") : h("td", { class: "num" + (r.enough ? "" : " pale"), "data-tip": fmtInt(r.now.crashes) + tx(" Abstürze auf ", " crashes in ") + fmtInt(r.now.sessions) + tx(" Sitzungen in 30 Tagen", " sessions in 30 days") + (r.enough ? "" : tx(" · unter " + ZONE.minSessions + " Sitzungen, nicht belastbar", " · below " + ZONE.minSessions + " sessions, not reliable")) }, fmt(r.now.rate));
    const tr = r => h("tr", { class: "click", tabindex: "0", "aria-label": tx("Ampel " + lvlName(r.level) + ": ", "Traffic light " + lvlName(r.level) + ": ") + appLabel(r.a), onclick: () => selectApp(r.key), onkeydown: e => { if (e.key === "Enter") selectApp(r.key); } },
      h("td", {}, dot(r.level)), h("td", { class: "nw" }, h("b", {}, r.a.appName), DATA.apps.filter(x => appKeyOf(x) === r.key).length > 1 ? " · " + platName(r.a.platform) : ""), multi ? h("td", {}, r.a.customerName) : null,
      r.store ? h("td", { class: "num", "data-tip": r.store.country + ": " + fmtInt(r.store.total) + tx(" Bewertungen", " ratings") }, fmt(r.store.average, 1)) : h("td", { class: "num muted" }, "–"),
      h("td", { class: "num" }, fmtInt(r.lastSt.rated), r.negRecent.length ? h("span", { class: "pill r1", style: "margin-left:.4rem" }, r.negRecent.length + " × 1–2 ★") : null),
      rateCell(r), h("td", { class: "num" }, r.dl === null ? h("span", { class: "muted" }, "–") : fmtInt(Math.round(r.dl))), h("td", { class: "why" }, r.why.join(" · ") || "–", kiBtn(r) ? h("div", {}, kiBtn(r)) : null));
    const foldRow = () => { const stars = greenRows.map(r => r.store && r.store.average).filter(x => x !== null && x !== undefined), nw = greenRows.map(r => r.lastSt.rated), rates = greenRows.map(r => r.now && r.now.rate).filter(x => x !== null && x !== undefined);
      const range = (xs, f) => !xs.length ? "–" : Math.min(...xs) === Math.max(...xs) ? f(xs[0]) : f(Math.min(...xs)) + "–" + f(Math.max(...xs));
      return h("tr", { id: "ovfold" }, h("td", {}, dot(0)), h("td", {}, h("b", {}, greenRows.length + tx(" weitere Apps", " more apps")), " ", h("span", { class: "muted" }, tx("ohne Auffälligkeit", "nothing unusual"))), multi ? h("td", {}) : null,
        h("td", { class: "num" }, range(stars, v => fmt(v, 1))), h("td", { class: "num" }, range(nw, fmtInt)), h("td", { class: "num" }, rates.length ? "≤ " + fmt(Math.max(...rates)) : "–"), h("td", {}),
        h("td", { class: "why" }, h("button", { type: "button", class: "linkbtn", onclick: () => { state.showGreen = true; renderOverview(); } }, tx("einblenden", "show") + " ›"))); };
    put(box, h("h3", { class: "sub3", style: "margin:.2rem 0 .6rem" }, tx("Ampel je App: Warnung von heute", "Traffic light per app: today’s warning")),
      h("div", { class: "tablewrap", style: "max-height:none" }, h("table", { id: "ovtable" }, h("thead", {}, h("tr", {}, head.map(t => h("th", {}, t)))),
      h("tbody", {}, rows.filter(r => !(fold && r.level === 0)).map(tr), fold ? foldRow() : null))),
      h("div", { class: "note" }, tx("Ampel: Warnung von heute, ohne den Zeitraum im Filter. Das Diagramm „Alle Apps auf einen Blick“ (Reiter Diagramme) zeigt dagegen die Lage über den gewählten Zeitraum und kann dieselbe App anders einstufen. Rot = handeln, gelb = ansehen, grün = nichts zu tun; Grund in der Spalte „Warum“. Store ★ = offizielle Store-Note im Land mit den meisten Bewertungen. Neu, Abstürze: letzte 30 Tage; Downloads: Erstinstallationen je Woche, Mittel aus 4 Wochen. Blass: unter " + ZONE.minSessions + " Sitzungen. Klick auf eine Zeile wählt die App im Filter.",
        "Traffic light: today’s warning, ignoring the period in the filter. The chart “All apps at a glance” (Charts tab) shows the position over the selected period instead and can rate the same app differently. Red = act, yellow = look, green = nothing to do; reason in the “Why” column. Store ★ = official store rating in the country with the most ratings. New, crashes: last 30 days; downloads: first-time downloads per week, 4-week average. Pale: below " + ZONE.minSessions + " sessions. Click a row to select the app in the filter.")));
  }

  // ---- Monatsbericht zum Drucken: Lage (Store-Note, neue Rezensionen, Abstürze), Ampel mit einem Satz je App, „Das sollten wir
  // tun“, mit KI je App die Zusammenfassung in drei Sätzen. Nutzt #printout wie der App-Bericht (printOut in fragen.js). ----
  function buildMonthly(rows, opts) {
    const d30 = daysBefore(asOfDate, OV.days), d60 = daysBefore(asOfDate, 2 * OV.days), inSc = reviews.filter(inScope);
    const ls = stats(inSc.filter(r => dayOf(r) >= d30)), ps = stats(inSc.filter(r => dayOf(r) >= d60 && dayOf(r) < d30));
    const sumCr = (f, t) => { let c = 0, se = 0; for (const r of rows) { const o = f === d30 ? r.now : r.prev; if (o) { c += o.crashes; se += o.sessions; } } return se ? 1000 * c / se : null; };
    const crNow = sumCr(d30), crPrev = sumCr(d60), storeAvg = (() => { let s = 0, n = 0; for (const r of rows) if (r.store) { s += r.store.average * r.store.total; n += r.store.total; } return n ? s / n : null; })();
    const arrow = (a, b, digits, inv) => a === null || b === null ? "" : (a - b) * (inv ? -1 : 1) > 0 ? " ▲" : (a - b) * (inv ? -1 : 1) < 0 ? " ▼" : " •";
    const tile = (label, value, sub) => h("div", { class: "pr-tile" }, h("div", { class: "pr-l" }, label), h("div", { class: "pr-v" }, value), h("div", { class: "pr-r" }, sub));
    const items = actionItems(rows), scopeName = [...new Set(rows.map(r => r.a.customerName))].join(", ");
    const nodes = [h("div", { class: "pr-head" }, h("div", { class: "pr-k" }, tx("Monatsbericht · letzte 30 Tage bis ", "Monthly report · last 30 days to ") + fmtDay(asOfDate)), h("h1", {}, tx("Bewertungen und Rezensionen", "Ratings and reviews") + (scopeName ? " · " + scopeName : "")),
        h("p", {}, rows.length + tx(rows.length === 1 ? " App in der Auswahl." : " Apps in der Auswahl.", rows.length === 1 ? " app in the selection." : " apps in the selection."))),
      h("div", { class: "pr-tiles" }, tile(tx("Store-Note (gewichtet)", "Store rating (weighted)"), storeAvg === null ? "–" : fmt(storeAvg, 1) + " ★", tx("offizielle Note, nach Bewertungen gewichtet", "official rating, weighted by ratings")),
        tile(tx("Neue Rezensionen", "New reviews"), fmtInt(ls.rated) + arrow(ls.rated, ps.rated, 0), tx("davor " + fmtInt(ps.rated) + " · Ø " + fmt(ls.avg, 1) + " ★ (davor " + fmt(ps.avg, 1) + ")", "before " + fmtInt(ps.rated) + " · avg " + fmt(ls.avg, 1) + " ★ (before " + fmt(ps.avg, 1) + ")")),
        tile(tx("Abstürze je 1000 Sitzungen", "Crashes per 1,000 sessions"), crNow === null ? "–" : fmt(crNow) + arrow(crNow, crPrev, 2, true), crPrev === null ? tx("keine Vergleichsdaten", "no comparison data") : tx("davor ", "before ") + fmt(crPrev))),
      h("h2", {}, tx("Ampel je App", "Traffic light per app")),
      h("table", { class: "pr-table" }, h("tbody", {}, rows.map(r => h("tr", {}, h("td", {}, dot(r.level)), h("td", {}, h("b", {}, appLabel(r.a))), h("td", {}, r.store ? fmt(r.store.average, 1) + " ★" : "–"), h("td", {}, fmtInt(r.lastSt.rated) + tx(" neu", " new")), h("td", {}, r.why.join(" · ") || tx("keine Auffälligkeit", "nothing unusual")))))),
      items.length ? [h("h2", {}, tx("Das sollten wir tun", "What we should do")), h("ol", {}, items.map(it => h("li", {}, h("b", {}, it.text + (it.ki ? " (KI)" : "")), " – " + it.why)))] : null];
    const sums = rows.map(r => { const d = aiDocOf(r.a), sm = d && d.summary; return sm && sm.text && featOn("summary") ? h("div", { class: "pr-sum" }, h("b", {}, appLabel(r.a)), " (KI, " + (d.provider || "?") + "): " + sm.text) : null; }).filter(Boolean);
    if (sums.length) nodes.push(h("h2", {}, tx("Was sagen die Nutzer? (KI)", "What do users say? (AI)")), sums);
    // im Gesamtbericht trägt die Reitergruppe die Überschrift; der feste Berichtszeitraum (30 Tage) bleibt als Zeile stehen
    if (opts && opts.all) nodes[0] = h("p", { class: "pr-k" }, tx("Monatsbericht · letzte 30 Tage bis ", "Monthly report · last 30 days to ") + fmtDay(asOfDate) + " · " + rows.length + tx(" Apps in der Auswahl", " apps in the selection"));
    nodes.push(h("div", { class: "pr-foot" }, tx("Quellen: App Store Connect, Google Play, öffentliche Store-Bewertung; KI-Texte sind Vorschläge eines Sprachmodells, Zahlen stammen aus den Daten. Datenstand ", "Sources: App Store Connect, Google Play, public store rating; AI texts are suggestions from a language model, figures come from the data. Data as of ") + fmtDate(DATA.dataAsOf) + "."));
    return nodes;
  }

  // ---- Vergleich nach Version: App × Version; Apple-Rezensionen über das Datum der jeweils aktuellen Store-Version zugeordnet ----
  const releasesByApp = () => { const m = new Map(); for (const k of ["apple", "google"]) for (const r of releaseList(k)) { const key = appKeyOf(r.app) + "/" + k; if (!m.has(key)) m.set(key, []); m.get(key).push(r); } return m; };
  function versionOfReview(r, rels) { if (r.appVersion) return r.appVersion; const d = (r.createdAt || "").slice(0, 10); let v = null; for (const x of rels) { if (x.date <= d) v = x.version; else break; } return v; }
  function renderCompare() {
    const box = $("vglout"); box.replaceChildren();
    const apps = DATA.apps.filter(inScope);
    if (apps.length < 2) { put(box, h("div", { class: "muted" }, tx("Der Vergleich braucht mindestens zwei Apps in der Auswahl.", "The comparison needs at least two apps in the selection."))); return; }
    const rels = releasesByApp(), cells = new Map(), count = new Map();
    for (const r of current) { const key = r.customerId + "/" + r.appId + "/" + r.platform, v = versionOfReview(r, rels.get(key) || []); if (!v) continue;
      const ck = v + "|" + key; if (!cells.has(ck)) cells.set(ck, []); cells.get(ck).push(r); count.set(v, (count.get(v) || 0) + 1); }
    if (!count.size) { put(box, h("div", { class: "muted" }, tx("Keine Rezension lässt sich einer Version zuordnen. Apple: möglich erst ab der ersten erfassten Veröffentlichung (Versionsleiste); Google: Version steht in der Rezension.", "No review can be assigned to a version. Apple: only from the first captured release onwards (release lane); Google: the version is part of the review."))); return; }
    const vers = [...count.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(x => x[0]).sort((a, b) => b.localeCompare(a, "de", { numeric: true }));
    const keyOf = a => a.customerId + "/" + a.appId + "/" + a.platform, cols = apps.filter(a => vers.some(v => cells.has(v + "|" + keyOf(a)))), both = new Set(cols.map(a => a.platform)).size > 1;
    const shared = vers.filter(v => cols.filter(a => cells.has(v + "|" + keyOf(a))).length >= 2).length;
    const cell = rs => { const st = stats(rs); if (!st.rated) return h("td", { class: "c muted" }, "–"); return h("td", { class: "c" + (st.rated < 5 ? " pale" : ""), "data-tip": st.rated + tx(" Rezensionen · negativ ", " reviews · negative ") + pct(st.negShare === null ? null : 100 * st.negShare) }, h("span", { class: "pill " + (st.avg >= 4 ? "r5" : st.avg >= 3 ? "r3" : "r1") }, fmt(st.avg, 1) + " (" + st.rated + ")")); };
    const median = v => { const xs = cols.map(a => stats(cells.get(v + "|" + keyOf(a)) || []).avg).filter(x => x !== null).sort((a, b) => a - b); if (!xs.length) return "–"; const m = xs.length % 2 ? xs[(xs.length - 1) / 2] : (xs[xs.length / 2 - 1] + xs[xs.length / 2]) / 2; return fmt(m, 1); };
    // Apps als Zeilen, Versionen als Spalten: Die Zahl der Spalten bleibt bei höchstens zehn, auch bei vielen Apps
    put(box, h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "App"), vers.map(v => h("th", { class: "c" }, v)))),
      h("tbody", {}, cols.map(a => h("tr", {}, h("td", { class: "nw" }, h("b", {}, appLabel(a) + (both ? " · " + platName(a.platform) : ""))), vers.map(v => cell(cells.get(v + "|" + keyOf(a)) || [])))),
        h("tr", {}, h("td", {}, h("b", {}, tx("Median", "Median"))), vers.map(v => h("td", { class: "c num" }, h("b", {}, median(v)))))))),
      h("div", { class: shared ? "note" : "warn" }, (shared ? "" : tx("Keine Version kommt bei zwei Apps vor; ein direkter Vergleich ist erst bei gleicher Version möglich. ", "No version occurs in two apps; a direct comparison needs the same version. ")) +
        tx("Zelle: Ø Sterne (Anzahl), blass unter 5 Rezensionen. Spalten: die zehn Versionen mit den meisten Rezensionen, neueste links; letzte Zeile: Median über alle Apps.", "Cell: avg stars (count), pale below 5 reviews. Columns: the ten versions with the most reviews, newest on the left; last row: median across all apps.")),
      kiVersionNote(rels));
  }

  // ---- Release-Effekt: gleich lange Fenster vor und nach jeder Veröffentlichung ----
  function renderRelease() {
    const box = $("relout"); box.replaceChildren();
    const W = state.relWin || 30, ctl = h("div", { class: "row", style: "margin-bottom:.8rem" }, h("span", { class: "lbl" }, tx("Fenster", "Window")), [14, 30].map(n => h("button", { type: "button", class: "secbtn", "aria-pressed": String(n === W), onclick: () => { state.relWin = n; renderRelease(); } }, n + tx(" Tage", " days"))));
    // Zeitraum aus dem Filter: nur Veröffentlichungen in diesem Zeitraum; die Fenster davor/danach dürfen darüber hinausreichen
    const inPeriod = r => (!state.f.from || r.date >= state.f.from) && (!state.f.to || r.date <= state.f.to);
    const rels = chartStores().flatMap(k => releaseList(k)).filter(inPeriod).sort((a, b) => a.date < b.date ? 1 : -1).slice(0, 20), inSc = reviews.filter(inScope);
    if (!rels.length) { put(box, ctl, h("div", { class: "muted" }, tx("Keine Veröffentlichung in der Auswahl und im gewählten Zeitraum bekannt (Datum aus dem iTunes Lookup oder Näherung aus Sitzungsdaten).", "No release known for the selection and the selected period (date from the iTunes Lookup or approximation from session data)."))); return; }
    const day = r => (r.createdAt || "").slice(0, 10);
    const rows = rels.map(r => { const key = appKeyOf(r.app), rv = inSc.filter(x => appKeyOf(x) === key && x.platform === r.app.platform && x.createdAt), d = r.date, b = addDays(d, -W), a = addDays(d, W);
      const before = stats(rv.filter(x => day(x) >= b && day(x) < d)), after = stats(rv.filter(x => day(x) >= d && day(x) < a)), st = (DATA.stability || []).find(x => appKeyOf(x) === key && x.platform === r.app.platform);
      const rate = (f, t) => { if (!st) return null; const o = stabilityBy(st.crashes.filter(x => x[0] >= f && x[0] < t), st.sessions.filter(x => x[0] >= f && x[0] < t), () => "x")[0]; return o && o.rate !== null ? o.rate : null; };
      return { r, before, after, rb: rate(b, d), ra: rate(d, a), rvB: rv.filter(x => day(x) >= b && day(x) < d), rvA: rv.filter(x => day(x) >= d && day(x) < a) }; }).filter(x => x.before.rated || x.after.rated || x.rb !== null || x.ra !== null), hidden = rels.length - rows.length;
    const kiCol = kiReleaseOn();
    if (!rows.length) { put(box, ctl, h("div", { class: "muted" }, tx("Zu keiner Veröffentlichung in der Auswahl gibt es Rezensionen oder Absturzdaten im Fenster.", "No release in the selection has reviews or crash data in the window."))); return; }
    const both = new Set(rels.map(r => r.app.platform)).size > 1, arrow = (x, y) => x + " → " + y;
    put(box, ctl, h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, ["Version", "App", tx("Datum", "Date"), tx("Rezensionen vorher → nachher", "Reviews before → after"), tx("Ø Sterne vorher → nachher", "Avg stars before → after"), "Δ", tx("negativ vorher → nachher", "negative before → after"), tx("Abstürze je 1000 vorher → nachher", "Crashes per 1,000 before → after"), kiCol ? tx("Beschwerden (KI)", "Complaints (AI)") : null].filter(Boolean).map(t => h("th", {}, t)))),
      h("tbody", {}, rows.map(x => { const small = x.before.rated < 5 || x.after.rated < 5;
        return h("tr", { class: small ? "pale" : "" }, h("td", {}, h("b", {}, x.r.version)), h("td", { class: "nw" }, appLabel(x.r.app) + (both ? " · " + platName(x.r.app.platform) : "")),
          h("td", { class: "num", "data-tip": x.r.exact ? tx("App Store, exakt", "App Store, exact") : tx("Näherung aus Sitzungsdaten", "approximation from session data") }, fmtDay(x.r.date) + (x.r.exact ? "" : " ≈")),
          h("td", { class: "num" }, arrow(x.before.rated, x.after.rated) + (small ? " ⚠" : "")), h("td", { class: "num" }, arrow(fmt(x.before.avg), fmt(x.after.avg))),
          h("td", {}, x.before.rated >= 3 && x.after.rated >= 3 ? deltaPill(x.after.avg - x.before.avg, .3, 2) : h("span", { class: "muted" }, "–")),
          h("td", { class: "num" }, arrow(pct(x.before.negShare === null ? null : 100 * x.before.negShare), pct(x.after.negShare === null ? null : 100 * x.after.negShare))),
          h("td", { class: "num" }, arrow(x.rb === null ? "–" : fmt(x.rb), x.ra === null ? "–" : fmt(x.ra))), kiCol ? kiReleaseCell(x.rvB, x.rvA) : null); })))),
      kiCol ? h("div", { class: "note" }, tx("Beschwerden (KI): Kernaussagen negativer oder dringender Rezensionen im Fenster nach dem Update, die davor fehlten („neu“), und solche von davor, die danach fehlen („weg“); Klick öffnet eine Rezension dazu, Maus über die Zeile zeigt die volle Liste. Gleiche Formulierungen werden zusammengezählt, ähnliche nicht.", "Complaints (AI): core statements of negative or urgent reviews in the window after the update that were missing before (“new”), and those from before that are missing after (“gone”); click opens one of the reviews, hover shows the full list. Identical phrasings are added up, similar ones are not."), " ", kiMark()) : null,
      h("div", { class: "note" }, tx("Fenster " + W + " Tage vor und ab dem Veröffentlichungstag, Gezeigt werden Veröffentlichungen im gewählten Zeitraum; die Fenster davor und danach können über ihn hinausreichen. Die Sternefilter wirken hier nicht, weil sonst der Vergleich der Sterne keinen Sinn ergibt. ≈ = Datum aus Sitzungsdaten geschätzt. Δ ab ±0,3 farbig. Blass und ⚠: unter 5 Rezensionen auf einer Seite." + (hidden ? " " + hidden + " Veröffentlichungen ohne Rezensionen und Absturzdaten sind ausgeblendet." : ""),
        "Window of " + W + " days before and from the release day, Releases within the selected period are shown; the windows before and after may extend beyond it. The star filters do not apply here, because the star comparison would otherwise make no sense. ≈ = date estimated from session data. Δ coloured from ±0.3. Pale and ⚠: fewer than 5 reviews on one side." + (hidden ? " " + hidden + " releases without reviews and crash data are hidden." : ""))));
  }

  // ---- Themen und Wörter: Themenbalken, typische Wörter (negativ gegen positiv), neu auftauchende Begriffe ----
  function renderTopics() {
    const box = $("themout"); box.replaceChildren();
    if (!current.length) { put(box, noData()); return; }
    // Die Themenbalken rechnen auf denselben Rezensionen wie das Diagramm „Themen der Rezensionen“ (`current`), damit
    // beide dieselben Zahlen zeigen. Der Klick auf einen Balken wirkt nur hier im Bereich (`state.topicPick`): Er zeigt
    // die Rezensionen zu diesem Thema als Liste unter den Balken. Den ganzen Bericht ändert nur der Filter oben.
    const onlyNeg = !!state.topicsNeg, base = onlyNeg ? current.filter(r => r.rating <= 2) : current;
    const ctl = h("div", { class: "row", style: "margin-bottom:.6rem" }, [[false, tx("alle Rezensionen", "all reviews")], [true, tx("nur negative (1–2 ★)", "negative only (1–2 ★)")]].map(([v, l]) => h("button", { type: "button", class: "secbtn", "aria-pressed": String(v === onlyNeg), onclick: () => { state.topicsNeg = v; renderTopics(); } }, l)));
    const picked = state.topicPick || "", pick = id => { state.topicPick = id === picked ? "" : id; renderTopics(); };
    const pickedDef = TOPICS.find(t => t.id === picked), filterDef = TOPICS.find(t => t.id === state.f.topic);
    const hint = h("div", { class: "note", style: "margin:0 0 .5rem" }, (filterDef ? tx("Oben im Filter ist das Thema „" + filterDef.de + "“ gewählt; die Balken zählen nur diese Rezensionen. ", "The filter above is set to the topic “" + filterDef.en + "”; the bars count only these reviews. ") : "")
      + tx("Klick auf ein Thema zeigt die Rezensionen dazu hier unter den Balken; der übrige Bericht bleibt unverändert. Dieselben Zahlen zeigt das Diagramm „Themen der Rezensionen“ im Reiter Diagramme.",
        "Click a topic to list its reviews here below the bars; the rest of the report stays unchanged. The chart “Review topics” on the Charts tab shows the same figures."));
    let list = null;
    if (pickedDef) {
      const rs = base.filter(r => reviewTopics(r).includes(picked));
      // Volle Breite unter Balken und Wörtern, dieselbe Liste wie unter „Rezensionen“ (reviewList); Sortierung und Seite
      // gelten nur hier und beginnen bei jedem neuen Thema neu (neueste zuerst)
      if (!state.topicList || state.topicList.id !== picked) state.topicList = { id: picked, sort: { key: "createdAt", dir: -1 }, page: 0 };
      list = h("div", { style: "margin-top:1.2rem" }, h("div", { class: "topicpick", role: "status" },
        h("span", {}, tx("Rezensionen zum Thema ", "Reviews on the topic "), h("b", {}, tx(pickedDef.de, pickedDef.en)), " · " + rs.length + (onlyNeg ? tx(" negative", " negative") : "") + tx(". Klick auf eine Zeile öffnet die Details, Klick auf einen Spaltenkopf sortiert.", ". Click a row for details, click a column header to sort.")),
        h("button", { type: "button", class: "btn", onclick: () => pick(picked) }, tx("Liste schließen", "Close list"))),
        rs.length ? reviewList(rs, state.topicList, renderTopics) : h("div", { class: "muted" }, tx("Keine Rezensionen zu diesem Thema in der Auswahl.", "No reviews on this topic in the selection.")));
    }
    const lo = logOdds(current.filter(r => r.rating <= 2), current.filter(r => r.rating >= 4)), bursts = burstWords(current, asOfDate, 30);
    const words = (items, cls, tipOf) => items.length ? h("div", { class: "words" }, items.map(x => h("span", { class: "word " + cls, "data-tip": tipOf(x) }, x.w))) : h("div", { class: "muted" }, tx("zu wenig Text für einen Vergleich", "not enough text for a comparison"));
    const nNeg = current.filter(r => r.rating <= 2).length, nPos = current.filter(r => r.rating >= 4).length;
    put(box, h("div", { class: "two" },
      h("div", {}, h("h3", {}, tx("Themen", "Topics")), ctl, hint, topicBars(base, pick, picked)),
      h("div", {},
        h("h3", {}, tx("Typisch für negative Rezensionen (1–2 ★)", "Typical of negative reviews (1–2 ★)")), words(lo.a, "neg", x => x.w + ": " + x.a + tx(" negative, ", " negative, ") + x.b + tx(" positive Rezensionen", " positive reviews")),
        h("h3", { style: "margin-top:1rem" }, tx("Typisch für positive Rezensionen (4–5 ★)", "Typical of positive reviews (4–5 ★)")), words(lo.b, "pos", x => x.w + ": " + x.b + tx(" positive, ", " positive, ") + x.a + tx(" negative Rezensionen", " negative reviews")),
        h("h3", { style: "margin-top:1rem" }, tx("Zuletzt häufiger (letzte 30 Tage)", "Recently more frequent (last 30 days)")), bursts.length ? words(bursts, "new", x => x.w + ": " + x.n + tx(" Rezensionen in 30 Tagen, vorher ", " reviews in 30 days, before ") + x.before) : h("div", { class: "muted" }, tx("nichts Auffälliges oder zu wenige Rezensionen", "nothing unusual or too few reviews")),
        h("div", { class: "note" }, tx("Wörter aus " + nNeg + " negativen und " + nPos + " positiven Rezensionen; Wortformen zusammengefasst (häufigste Schreibweise), auch Zweiwortbegriffe; nur deutliche Unterschiede. Maus über ein Wort zeigt die Zahlen.",
          "Words from " + nNeg + " negative and " + nPos + " positive reviews; word forms merged (most frequent spelling), two-word terms included; only clear differences. Hover a word for the numbers.")))), list,
      kiTopicButtons());
    reportButtons("themen", PRINTERS.topics);
  }
  // Themen-Bericht zum Drucken (Wunsch des Nutzers): oben die Gesamtbewertung mit Verteilung und den Kennzahlen, darunter die
  // Themenbalken einmal für alle und einmal nur für negative Rezensionen; mit KI zusätzlich die meistgewünschten Funktionen.
  // Ohne die Wortlisten („Typisch für …“, „Zuletzt häufiger“) und ohne die Rezensionsliste.
  function buildTopicsReport(opts) {
    const st = stats(current), score = h("div", { class: "score pr-score" }); renderScore(st, score);
    const section = (title, rs) => [h("h2", {}, title), rs.length ? topicBars(rs, null, "") : h("p", { class: "muted" }, tx("Keine Rezensionen in der Auswahl.", "No reviews in the selection."))];
    const wishes = kiWishesBlock();
    return [opts && opts.all ? null : h("div", { class: "pr-head" }, h("div", { class: "pr-k" }, tx("Rezensionen · Themen", "Reviews · topics")), h("h1", {}, tx("Themen der Rezensionen", "Review topics"))),
      score, h("div", { class: "grid kpis pr-kpis" }, kpiTiles(st)),
      section(tx("Alle Rezensionen", "All reviews"), current), section(tx("Nur negative Rezensionen (1–2 ★)", "Negative reviews only (1–2 ★)"), current.filter(r => r.rating <= 2)),
      wishes ? [h("h2", {}, tx("Meistgewünschte Funktionen (KI)", "Most requested features (AI)")), wishes] : null,
      h("div", { class: "pr-foot" }, tx("Themen aus festen Wortlisten (config/themen.json); eine Rezension kann mehrere Themen treffen. Zahlen stammen aus den Daten", "Topics from fixed word lists (config/themen.json); a review can match several topics. Figures come from the data")
        + (wishes ? tx("; „Meistgewünschte Funktionen“ zählt Kernaussagen der KI. ", "; “Most requested features” counts AI core statements. ") : ". ") + tx("Datenstand ", "Data as of ") + fmtDate(DATA.dataAsOf || "") + ".")];
  }

  // ---- Antwortverhalten: Quoten, Antwortzeit, Verbesserung nach Antwort, offene negative Rezensionen ----
  function renderReplies() {
    const box = $("antout"); box.replaceChildren();
    if (!current.length) { put(box, noData()); return; }
    const replied = current.filter(hasReply), neg = current.filter(r => r.rating <= 2), negReplied = neg.filter(hasReply), win = windowOf();
    const days = replied.map(r => r.developerReply.repliedAt && r.createdAt ? (Date.parse(r.developerReply.repliedAt) - Date.parse(r.createdAt)) / 864e5 : null).filter(x => x !== null && x >= 0).sort((a, b) => a - b);
    const median = days.length ? days[Math.floor(days.length / 2)] : null;
    const byId = new Map(replied.map(r => [r.id, r])); let improved = 0, worsened = 0;
    for (const [id, at, prev, next] of DATA.ratingChanges || []) { const r = byId.get(id); if (!r || !r.developerReply.repliedAt || !(at > r.developerReply.repliedAt)) continue; if (next > prev) improved++; else if (next < prev) worsened++; }
    const open = neg.filter(r => !hasReply(r) && inWin(r.createdAt, win)).sort((a, b) => (b.createdAt || "") < (a.createdAt || "") ? -1 : 1).slice(0, 20), draftCol = kiDraftOn();
    put(box, h("div", { class: "grid kpis", style: "margin-bottom:1rem" },
      kpTile(pct(current.length ? 100 * replied.length / current.length : null), tx("Antwortquote", "reply rate"), replied.length + tx(" von ", " of ") + current.length),
      kpTile(pct(neg.length ? 100 * negReplied.length / neg.length : null), tx("Antwortquote bei 1–2 ★", "reply rate on 1–2 ★"), negReplied.length + tx(" von ", " of ") + neg.length),
      kpTile(median === null ? "–" : fmt(median, 1) + tx(" Tage", " days"), tx("Median Antwortzeit", "median reply time"), days.length + tx(" Antworten mit Datum", " replies with date")),
      kpTile(replied.length ? improved + tx(" von ", " of ") + replied.length : "–", tx("nach Antwort verbessert", "improved after reply"), tx("Sterne nach der Antwort erhöht; verschlechtert: ", "stars raised after the reply; lowered: ") + worsened)));
    put(box, h("h3", { class: "sub3" }, tx("Offene negative Rezensionen (1–2 ★, ohne Antwort, ", "Open negative reviews (1–2 ★, no reply, ") + win.label + ")"));
    if (!open.length) { put(box, h("div", { class: "muted" }, tx("Keine offenen negativen Rezensionen in diesem Fenster.", "No open negative reviews in this window."))); }
    else put(box, h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, ["App", tx("Sterne", "Stars"), tx("Titel", "Title"), tx("Datum", "Date"), tx("Themen", "Topics"), draftCol ? tx("Entwurf (KI)", "Draft (AI)") : null].filter(Boolean).map(t => h("th", {}, t)))),
      h("tbody", {}, open.map(r => h("tr", { class: "click", tabindex: "0", onclick: () => showDetail(r), onkeydown: e => { if (e.key === "Enter") showDetail(r); } },
        h("td", {}, r.appName), h("td", {}, h("span", { class: "pill r" + r.rating }, "★ " + r.rating)), h("td", { class: "txt" }, r.title || h("span", { class: "muted" }, "–")), h("td", { class: "num" }, fmtDate(r.createdAt)),
        h("td", { class: "muted" }, reviewTopics(r).map(id => { const t = TOPICS.find(x => x.id === id); return t ? tx(t.de, t.en) : id; }).join(", ")), draftCol ? kiDraftCell(r, renderReplies) : null))))));
    put(box, h("div", { class: "note" }, tx("Klick auf eine Zeile öffnet die Rezension.", "Click a row to open the review.") + (draftCol ? tx(" „Entwurf“ öffnet den Antwortentwurf der KI in einem Fenster (nur zum Kopieren, wird nie gesendet).", " “Draft” opens the AI’s reply draft in a window (to copy only, never sent).") : "")));
  }

