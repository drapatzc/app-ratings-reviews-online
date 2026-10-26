  // Fragen und Antworten (Überblick), Apps im Vergleich (Downloads & Store), App-Bericht zum Drucken, Hinweis zum nächsten Abruf.
  // Alles aus vorhandenen Daten: Store-Kennzahlen und Stabilität (nur Apple), offizielle Store-Note, Rezensionen mit Themen.
  // Fenster wie in den übrigen Bereichen: Zeitraum aus dem Filter, sonst die letzten 90 Tage (windowOf).
  // FQ: Mindestmengen für „sichere Aussage“ und ▲/▼ (Einblendungen, Downloads, Installationen, Sitzungen, negative Rezensionen
  // mit Thema), Abweichung vom Median relativ (step, 25 %), Tage für den Anteil der neuesten Version (latestDays).
  const FQ = { minImp: 1000, minDl: 30, minInst: 100, minSess: 500, minNeg: 30, minStore: 20, step: .25, latestDays: 7, webLow: 2 };
  const isNewDl = t => t === "First-time download" || t === "Redownload";
  // „iOS 26.6“ → „iOS 26“; ohne Zahl „unbekannt“
  const osMajor = v => { const m = /^(\D*?)\s*(\d+)/.exec(v || ""); return m ? (m[1].trim() + " " + m[2]).trim() : tx("unbekannt", "unknown"); };
  const medianOf = xs => { const v = xs.filter(x => x !== null && x !== undefined).sort((a, b) => a - b); if (!v.length) return null; const i = v.length >> 1; return v.length % 2 ? v[i] : (v[i - 1] + v[i]) / 2; };
  // Kennzahlen einer App im Fenster; alle Summen aus den gespeicherten Zeilen, nichts geschätzt
  function appFacts(a, win) {
    const key = appKeyOf(a), f = { a, key, imp: 0, views: 0, dl: 0, first: 0, src: {}, inst: 0, del: 0, sess: 0, crashes: 0, os: {}, latest: null, latestShare: null, latestSess: 0, store: null };
    const sm = (DATA.storeMetrics || []).find(x => appKeyOf(x) === key && x.platform === a.platform);
    f.hasStore = !!sm;
    if (sm) {
      for (const r of sm.engagement) if (inWin(r[0], win)) { if (r[1] === "Impression") f.imp += r[3]; else if (r[1] === "Page view") f.views += r[3]; }
      for (const r of sm.downloads) if (inWin(r[0], win) && isNewDl(r[1])) { f.dl += r[5]; if (r[1] === "First-time download") { f.first += r[5]; f.src[r[2]] = (f.src[r[2]] || 0) + r[5]; } }
      for (const r of sm.installs) if (inWin(r[0], win)) { if (r[1] === "Install") f.inst += r[4]; else if (r[1] === "Delete") f.del += r[4]; }
    }
    const st = (DATA.stability || []).find(x => appKeyOf(x) === key && x.platform === a.platform);
    if (st) {
      const sess = st.sessions.filter(r => inWin(r[0], win));
      for (const r of sess) { f.sess += r[4]; const m = osMajor(r[2]); f.os[m] = (f.os[m] || 0) + r[4]; }
      for (const r of st.crashes) if (inWin(r[0], win)) f.crashes += r[4];
      // Neueste Version = höchste Versionsnummer in den Sitzungen; Anteil an den Sitzungen der letzten Datentage im Fenster
      const vers = [...new Set(sess.map(r => r[1]).filter(Boolean))].sort((x, y) => y.localeCompare(x, "de", { numeric: true }));
      f.latest = vers[0] || null;
      if (f.latest) { const lastDay = sess.reduce((m, r) => r[0] > m ? r[0] : m, ""), from = daysBefore(lastDay, FQ.latestDays); let all = 0, mine = 0;
        for (const r of sess) if (r[0] > from) { all += r[4]; if (r[1] === f.latest) mine += r[4]; }
        f.latestSess = all; f.latestShare = all ? 100 * mine / all : null; }
    }
    const snaps = new Map();  // jüngster Store-Stand je Land; verwendet wird das Land mit den meisten Bewertungen
    for (const x of DATA.ratings) if (x.origin === "store-official" && appKeyOf(x) === key && x.platform === a.platform && x.total > 0) { const c = snaps.get(x.country); if (!c || x.capturedAt > c.capturedAt) snaps.set(x.country, x); }
    f.store = [...snaps.values()].sort((x, y) => y.total - x.total)[0] || null;
    f.conv = f.imp ? 100 * f.dl / f.imp : null;
    f.reach = a.audience && f.hasStore ? 1000 * f.first / a.audience : null;
    f.delRate = f.inst ? 100 * f.del / f.inst : null;
    f.crashRate = f.sess ? 1000 * f.crashes / f.sess : null;
    f.webShare = f.first ? 100 * (f.src["Web referrer"] || 0) / f.first : null;
    return f;
  }
  // Kennzahlen für Vergleich und App-Bericht: better 1 = höher ist besser, -1 = niedriger ist besser; ok = genug Daten;
  // abs = feste Schwelle für ▲/▼ statt der relativen (FQ.step); sde/sen = kurze Spaltenköpfe der Vergleichstabelle
  const METRICS = [
    { id: "reach", de: "Downloads je 1000 der Zielgruppe", en: "Downloads per 1,000 of target group", sde: "Reichweite je 1000", sen: "Reach per 1,000", better: 1, val: f => f.reach, ok: f => f.reach !== null && f.first >= FQ.minDl, show: v => fmt(v, 1) },
    { id: "conv", de: "Einblendungen, die zum Download führen", en: "Impressions leading to a download", sde: "Einblendung → Download", sen: "Impression → download", better: 1, val: f => f.conv, ok: f => f.imp >= FQ.minImp && f.dl >= FQ.minDl, show: v => fmt(v, 1) + " %" },
    { id: "store", de: "Store-Note", en: "Store rating", sde: "Store-Note", sen: "Store rating", better: 1, val: f => f.store ? f.store.average : null, ok: f => !!f.store && f.store.total >= FQ.minStore, show: v => fmt(v, 1), abs: .2 },
    { id: "crash", de: "Abstürze je 1000 Sitzungen", en: "Crashes per 1,000 sessions", sde: "Abstürze je 1000", sen: "Crashes per 1,000", better: -1, val: f => f.crashRate, ok: f => f.sess >= FQ.minSess, show: v => fmt(v, 2) },
    { id: "del", de: "Löschungen je 100 Installationen", en: "Deletions per 100 installs", sde: "Löschungen je 100", sen: "Deletions per 100", better: -1, val: f => f.delRate, ok: f => f.inst >= FQ.minInst, show: v => fmt(v, 0) },
    { id: "latest", de: "Sitzungen auf neuester Version", en: "Sessions on latest version", sde: "Neueste Version", sen: "Latest version", better: 1, val: f => f.latestShare, ok: f => f.latestSess >= FQ.minSess, show: v => fmt(v, 0) + " %", abs: 10 }];
  // Median und Rang je Kennzahl über eine Gruppe von Apps; nur Apps mit genug Daten zählen, Median erst ab drei Apps
  function peerStats(facts) {
    const out = {};
    for (const m of METRICS) { const vals = facts.filter(m.ok).map(m.val); out[m.id] = { med: vals.length >= 3 ? medianOf(vals) : null, vals, n: vals.length }; }
    return out;
  }
  // +1 deutlich besser, -1 deutlich schlechter als der Median, 0 unauffällig oder nicht beurteilbar
  function markOf(m, f, ps) {
    const p = ps[m.id], v = m.val(f);
    if (p.med === null || v === null || !m.ok(f)) return 0;
    const diff = v - p.med, big = m.abs ? Math.abs(diff) >= m.abs : p.med !== 0 && Math.abs(diff) / Math.abs(p.med) >= FQ.step;
    return big ? Math.sign(diff) * m.better : 0;
  }
  const rankOf = (m, f, ps) => { const v = m.val(f); if (v === null || !m.ok(f) || ps[m.id].n < 2) return null; return 1 + ps[m.id].vals.filter(x => m.better > 0 ? x > v : x < v).length; };
  const arrow = k => k > 0 ? "▲ " : k < 0 ? "▼ " : "";
  const sure = ok => ok ? h("span", { class: "pill r5" }, tx("✓ sichere Aussage", "✓ reliable")) : h("span", { class: "pill r3" }, tx("! Hinweis: wenig Daten", "! indication: little data"));
  const toTab = (id, de, en) => h("button", { type: "button", class: "linkbtn", onclick: () => setTab(id) }, tx(de, en) + " ›");
  function qcard(q, answer, viz, ok, link) {
    return h("div", { class: "ovcard qcard" }, h("h3", {}, q), h("p", { class: "qans" }, answer), viz, h("div", { class: "qfoot" }, ok === null ? h("span", {}) : sure(ok), link));
  }
  const qempty = (q, text) => h("div", { class: "ovcard qcard" }, h("h3", {}, q), h("p", { class: "muted" }, text));
  // Punkte je App auf einer Linie, senkrechter Strich = Median
  function strip(vals, med, show) {
    const lo = Math.min(...vals), hi = Math.max(...vals), pos = v => hi > lo ? 100 * (v - lo) / (hi - lo) : 50;
    return [h("div", { class: "qstrip", role: "img", "aria-label": tx("Werte je App, Strich = Median", "values per app, line = median") },
      vals.map(v => h("i", { class: v <= lo + (hi - lo) * .2 ? "lo" : v >= hi - (hi - lo) * .2 ? "hi" : "", style: "left:" + pos(v).toFixed(1) + "%", "data-tip": show(v) })),
      med !== null ? h("b", { style: "left:" + pos(med).toFixed(1) + "%" }) : null),
      h("div", { class: "qscale" }, h("span", {}, show(lo)), med !== null ? h("span", {}, tx("Median ", "median ") + show(med)) : null, h("span", {}, show(hi)))];
  }
  function stack(parts) {
    const total = parts.reduce((s, p) => s + p.n, 0);
    return [h("div", { class: "qstack", role: "img", "aria-label": parts.map(p => p.label + " " + fmt(100 * p.n / total, 0) + " %").join(", ") },
      parts.map(p => h("span", { class: "q-" + p.cls, style: "width:" + (100 * p.n / total).toFixed(2) + "%", "data-tip": p.label + ": " + fmtInt(p.n) }))),
      h("div", { class: "qlegend" }, parts.map(p => h("span", {}, h("i", { class: "qsw q-" + p.cls }), p.label + " " + fmt(100 * p.n / total, 0) + " %")))];
  }
  function rowBars(rows) {
    const max = Math.max(...rows.map(r => r.pct), 1);
    return h("div", { class: "bars" }, rows.map(r => { const fill = h("div", { class: "fill" }); fill.style.background = r.warn ? "var(--mid)" : "var(--accent)"; grow(fill, 100 * r.pct / max);
      return h("div", { class: "bar", "data-tip": r.label + ": " + fmt(r.pct, 1) + " %" }, h("div", { class: "t" }, r.label), h("div", { class: "track" }, fill), h("div", { class: "v" }, fmt(r.pct, r.pct < 10 ? 1 : 0) + " %")); }));
  }

  // ---- Fragen und Antworten: sechs Karten, folgen Kunde, App, Plattform und Zeitraum ----
  function renderQuestions() {
    const box = $("frout"); box.replaceChildren();
    const win = windowOf(), apps = DATA.apps.filter(inScope), facts = apps.filter(a => a.platform === "apple").map(a => appFacts(a, win));
    const sum = k => facts.reduce((s, f) => s + f[k], 0), withStore = facts.filter(f => f.hasStore), many = facts.length > 1, cards = [];
    const noStore = tx("Für diese Auswahl liegen keine Store-Kennzahlen vor (nur Apple, Abruf: ./ratings.sh store).", "No store figures for this selection (Apple only, fetch: ./ratings.sh store).");
    const noStab = tx("Für diese Auswahl liegen keine Sitzungsdaten vor (nur Apple, Abruf: ./ratings.sh stability).", "No session data for this selection (Apple only, fetch: ./ratings.sh stability).");
    // 1. Konversion: Downloads (Erst- und erneute) je 100 Einblendungen im Store
    const q1 = tx("Laden Store-Besucher die App?", "Do store visitors download the app?"), imp = sum("imp"), dl = sum("dl");
    if (!withStore.length || !imp) cards.push(qempty(q1, noStore));
    else { const ok = facts.filter(METRICS[1].ok), vals = ok.map(f => f.conv);
      cards.push(qcard(q1, tx("Von 100 Einblendungen im Store führen " + fmt(100 * dl / imp, 1) + " zu einem Download.", fmt(100 * dl / imp, 1) + " of 100 impressions in the store lead to a download.")
        + (vals.length >= 2 ? tx(" Zwischen den Apps liegen " + fmt(Math.min(...vals), 1) + " bis " + fmt(Math.max(...vals), 1) + " %.", " Between the apps it ranges from " + fmt(Math.min(...vals), 1) + " to " + fmt(Math.max(...vals), 1) + " %.") : ""),
        [vals.length >= 2 ? strip(vals, vals.length >= 3 ? medianOf(vals) : null, v => fmt(v, 1) + " %") : null,
          h("p", { class: "note", style: "margin:0" }, fmtInt(imp) + tx(" Einblendungen · ", " impressions · ") + fmtInt(sum("views")) + tx(" Seitenaufrufe · ", " page views · ") + fmtInt(dl) + " Downloads")],
        imp >= FQ.minImp && dl >= FQ.minDl, toTab("store", "Je App ansehen", "See per app"))); }
    // 2. Herkunft der Erstinstallationen
    const q2 = tx("Woher kommen die Downloads?", "Where do downloads come from?"), first = sum("first");
    if (!first) cards.push(qempty(q2, withStore.length ? tx("Im Zeitraum gibt es keine Erstinstallationen.", "No first-time downloads in the period.") : noStore));
    else { const src = {}; for (const f of facts) for (const [k, n] of Object.entries(f.src)) src[k] = (src[k] || 0) + n;
      const order = [["App Store search", "search"], ["App Store browse", "browse"], ["Web referrer", "web"], ["App referrer", "appref"], ["Unavailable", "none"]];
      const parts = order.filter(([k]) => src[k]).map(([k, cls]) => ({ n: src[k], cls, label: SOURCES[k] || k }));
      const share = k => 100 * (src[k] || 0) / first, low = facts.filter(f => f.first >= FQ.minDl && f.webShare < FQ.webLow).length;
      cards.push(qcard(q2, tx(fmt(share("App Store search"), 0) + " % der Erstinstallationen kommen über die App-Store-Suche, " + fmt(share("Web referrer"), 0) + " % über Verweise von Webseiten.",
        fmt(share("App Store search"), 0) + " % of first-time downloads come from App Store search, " + fmt(share("Web referrer"), 0) + " % from website referrers.")
        + (many && low ? tx(" Bei " + low + (low === 1 ? " App" : " Apps") + " kommt fast nichts über Webseiten.", " For " + low + (low === 1 ? " app" : " apps") + " almost nothing comes from websites.") : ""),
        stack(parts), first >= 100, toTab("charts", "Zu den Diagrammen", "To the charts"))); }
    // 3. Löschungen je 100 Installationen
    const q3 = tx("Behalten die Nutzer die App?", "Do users keep the app?"), inst = sum("inst"), del = sum("del");
    if (!inst) cards.push(qempty(q3, noStore));
    else { const vals = facts.filter(METRICS[4].ok).map(f => f.delRate);
      cards.push(qcard(q3, tx("Auf 100 Installationen kommen " + fmt(100 * del / inst, 0) + " Löschungen.", "There are " + fmt(100 * del / inst, 0) + " deletions per 100 installs.")
        + (vals.length >= 2 ? tx(" Spanne zwischen den Apps: " + fmt(Math.min(...vals), 0) + " bis " + fmt(Math.max(...vals), 0) + ".", " Range between the apps: " + fmt(Math.min(...vals), 0) + " to " + fmt(Math.max(...vals), 0) + ".") : ""),
        [vals.length >= 2 ? strip(vals, vals.length >= 3 ? medianOf(vals) : null, v => fmt(v, 0)) : null, h("p", { class: "note", style: "margin:0" }, fmtInt(inst) + tx(" Installationen · ", " installs · ") + fmtInt(del) + tx(" Löschungen", " deletions"))],
        inst >= FQ.minInst, toTab("store", "Je App ansehen", "See per app"))); }
    // 4. Anteil der Sitzungen auf der jeweils neuesten Version
    const q4 = tx("Wie schnell kommen Nutzer auf die neueste Version?", "How fast do users move to the latest version?"), ls = facts.filter(f => f.latestSess);
    if (!ls.length) cards.push(qempty(q4, noStab));
    else { const all = ls.reduce((s, f) => s + f.latestSess, 0), mine = ls.reduce((s, f) => s + f.latestSess * f.latestShare / 100, 0);
      cards.push(qcard(q4, tx(fmt(100 * mine / all, 0) + " % der Sitzungen der letzten " + FQ.latestDays + " Tage laufen auf " + (ls.length === 1 ? "Version " + ls[0].latest : "der jeweils neuesten Version") + ".",
        fmt(100 * mine / all, 0) + " % of sessions in the last " + FQ.latestDays + " days run on " + (ls.length === 1 ? "version " + ls[0].latest : "the latest version of each app") + "."),
        ls.length > 1 ? rowBars(ls.slice().sort((x, y) => y.latestShare - x.latestShare).slice(0, 5).map(f => ({ label: appLabel(f.a) + " " + f.latest, pct: f.latestShare }))) : null,
        all >= FQ.minSess, toTab("stabil", "Zur Stabilität", "To stability"))); }
    // 5. Systemversionen: Hauptversionen der häufigsten Systemfamilie, neueste zuerst
    const q5 = tx("Welche Systemversionen sind noch im Einsatz?", "Which OS versions are still in use?"), sess = sum("sess");
    if (!sess) cards.push(qempty(q5, noStab));
    else { const os = {}; for (const f of facts) for (const [k, n] of Object.entries(f.os)) os[k] = (os[k] || 0) + n;
      const fam = {}; for (const [k, n] of Object.entries(os)) { const name = k.replace(/\s*\d+$/, ""); fam[name] = (fam[name] || 0) + n; }
      const main = Object.entries(fam).sort((x, y) => y[1] - x[1])[0][0], num = k => parseInt((/\d+$/.exec(k) || ["0"])[0], 10);
      const majors = Object.keys(os).filter(k => k.replace(/\s*\d+$/, "") === main && num(k) > 0).sort((x, y) => num(y) - num(x)), famN = fam[main];
      const top2 = majors.slice(0, 2).reduce((s, k) => s + os[k], 0), rows = majors.slice(0, 4).map((k, i) => ({ label: k, pct: 100 * os[k] / famN, warn: i >= 2 }));
      const rest = majors.slice(4).reduce((s, k) => s + os[k], 0); if (rest) rows.push({ label: tx("älter", "older"), pct: 100 * rest / famN, warn: true });
      if (!majors.length) cards.push(qempty(q5, tx("Die Sitzungsdaten nennen keine Systemversion.", "The session data names no OS version.")));
      else cards.push(qcard(q5, majors.length > 2 ? tx("Die beiden neuesten Versionen (" + majors.slice(0, 2).join(", ") + ") decken " + fmt(100 * top2 / famN, 0) + " % der Sitzungen ab; " + fmt(100 - 100 * top2 / famN, 1) + " % laufen auf " + majors[2] + " oder älter.",
        "The two newest versions (" + majors.slice(0, 2).join(", ") + ") cover " + fmt(100 * top2 / famN, 0) + " % of sessions; " + fmt(100 - 100 * top2 / famN, 1) + " % run on " + majors[2] + " or older.")
        : tx("Alle Sitzungen laufen auf " + majors.join(" oder ") + ".", "All sessions run on " + majors.join(" or ") + "."),
        rowBars(rows), sess >= FQ.minSess, toTab("stabil", "Zur Stabilität", "To stability"))); }
    // 6. Negative Rezensionen nach Bereich der Themen (config/themen.json „bereich“: app oder anbieter)
    const q6 = tx("Liegt es an der App oder am Anbieter?", "Is it the app or the provider?"), area = new Map(TOPICS.filter(t => t.bereich).map(t => [t.id, t]));
    const neg = reviews.filter(r => inScope(r) && r.rating >= 1 && r.rating <= 2 && inWin(r.createdAt, win));
    if (!area.size) cards.push(qempty(q6, tx("Die Themenliste ordnet keinem Thema einen Bereich zu (Feld „bereich“ in config/themen.json).", "The topic list assigns no area to any topic (field “bereich” in config/themen.json).")));
    else { const cnt = { app: 0, anbieter: 0 }, per = new Map(); let tagged = 0;
      for (const r of neg) { const ts = reviewTopics(r).filter(id => area.has(id)); if (!ts.length) continue; tagged++;
        for (const b of new Set(ts.map(id => area.get(id).bereich))) cnt[b]++; for (const id of ts) per.set(id, (per.get(id) || 0) + 1); }
      if (!tagged) cards.push(qempty(q6, tx("Keine negative Rezension im Zeitraum passt zu einem Thema mit Bereich.", "No negative review in the period matches a topic with an area.")));
      else { const tot = cnt.app + cnt.anbieter, top = b => [...per.entries()].filter(([id]) => area.get(id).bereich === b).sort((x, y) => y[1] - x[1]).slice(0, 3).map(([id, n]) => tx(area.get(id).de, area.get(id).en) + " (" + n + ")").join(" · ") || "–";
        cards.push(qcard(q6, tx("Von " + tagged + (tagged === 1 ? " negativen Rezension" : " negativen Rezensionen") + " mit Thema betreffen " + fmt(100 * cnt.anbieter / tot, 0) + " % Abläufe des Anbieters und " + fmt(100 * cnt.app / tot, 0) + " % die App selbst.",
          "Of " + tagged + (tagged === 1 ? " negative review" : " negative reviews") + " with a topic, " + fmt(100 * cnt.anbieter / tot, 0) + " % concern the provider’s processes and " + fmt(100 * cnt.app / tot, 0) + " % the app itself."),
          [stack([{ n: cnt.anbieter, cls: "prov", label: tx("Anbieter", "Provider") }, { n: cnt.app, cls: "search", label: "App" }].filter(p => p.n)),
            h("div", { class: "qsplit" }, h("div", {}, h("b", {}, tx("Anbieter", "Provider")), h("div", { class: "muted" }, top("anbieter"))), h("div", {}, h("b", {}, "App"), h("div", { class: "muted" }, top("app"))))],
          tagged >= FQ.minNeg, toTab("rez", "Rezensionen lesen", "Read reviews"))); } }
    put(box, h("div", { class: "ovcards" }, cards), h("div", { class: "note" }, tx("Zeitraum: ", "Period: ") + win.label + tx(". Store-Kennzahlen und Sitzungen nur Apple. „Sichere Aussage“ heißt: genug Daten, um die Zahl ernst zu nehmen.", ". Store figures and sessions Apple only. “Reliable” means: enough data to take the figure seriously.")));
  }

  // ---- Apps im Vergleich: eine Zeile je Apple-App, Median über die gezeigten Apps, ▲/▼ bei deutlicher Abweichung ----
  function renderAppCompare(target, forPrint) {
    const box = target || $("avout"); box.replaceChildren();
    const win = windowOf(), facts = DATA.apps.filter(a => inScope(a) && a.platform === "apple").map(a => appFacts(a, win));
    if (!facts.length) { put(box, h("div", { class: "muted" }, tx("Der Vergleich braucht Apple-Apps in der Auswahl (Store-Kennzahlen liefert bisher nur Apple).", "The comparison needs Apple apps in the selection (only Apple provides store figures so far)."))); return; }
    const ps = peerStats(facts), noAud = !facts.some(f => f.a.audience), kiCols = kiCompareOn(facts);
    const cellOf = (m, f) => { const v = m.val(f); if (v === null) return h("td", { class: "num muted" }, "–"); const k = markOf(m, f, ps);
      return h("td", { class: "num" + (m.ok(f) ? "" : " pale") + (k > 0 ? " up" : k < 0 ? " down" : ""), "data-tip": m.ok(f) ? tx(m.de, m.en) : tx("zu wenig Daten für ein Urteil", "too little data for a verdict") }, arrow(k) + m.show(v)); };
    put(box, h("div", { class: "row", style: "justify-content:space-between;flex-wrap:wrap;gap:.6rem;margin-bottom:.6rem" },
      h("span", { class: "note", style: "margin:0" }, tx("Zeitraum: ", "Period: ") + win.label), forPrint ? null : printControl(facts)),
      h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "App"), METRICS.map(m => h("th", { title: tx(m.de, m.en) }, tx(m.sde, m.sen))), kiCols ? kiCompareHeads().map(t => h("th", {}, t)) : null)),
        h("tbody", {}, facts.map(f => h("tr", { class: "click", onclick: () => selectApp(f.key) }, h("td", { class: "nw" }, h("b", {}, appLabel(f.a))), METRICS.map(m => cellOf(m, f)), kiCols ? kiCompareCells(f.a, win) : null)),
          facts.length >= 3 ? h("tr", {}, h("td", {}, h("b", {}, tx("Median aller ", "Median of all ") + facts.length)), METRICS.map(m => h("td", { class: "num" }, h("b", {}, ps[m.id].med === null ? "–" : m.show(ps[m.id].med)))), kiCols ? kiCompareHeads().map(() => h("td", {})) : null) : null))),
      h("div", { class: "note" }, tx("▲ deutlich besser, ▼ deutlich schlechter als der Median (ab drei Apps mit genug Daten). Blass: zu wenig Daten für ein Urteil. Klick auf eine Spalte sortiert, Klick auf eine Zeile wählt die App im Filter.",
        "▲ clearly better, ▼ clearly worse than the median (from three apps with enough data). Pale: too little data for a verdict. Click a column to sort, click a row to select the app in the filter.")),
      kiCols ? h("div", { class: "note" }, tx("Spalten mit (KI): Anteil verärgerter oder resignierter Nutzer laut KI im Zeitraum; Hauptlob, Hauptkritik und Einschätzung aus der Zusammenfassung der jüngsten Rezensionen je App. Vorschläge eines Sprachmodells, keine Messwerte.", "Columns marked (AI): share of annoyed or resigned users according to the AI in the period; main praise, main criticism and assessment from the summary of each app’s most recent reviews. Suggestions from a language model, not measurements."), " ", kiMark()) : null,
      noAud ? h("div", { class: "note" }, tx("Downloads je 1000 der Zielgruppe: Für keine App ist die Größe der Zielgruppe eingetragen („audience“ je App in config/config.json).", "Downloads per 1,000 of target group: no app has a target group size (“audience” per app in config/config.json).")) : null);
    if (!forPrint) sortTables(box, "appvgl");
    if (!forPrint) reportButtons("appvgl", PRINTERS.store);
  }
  // Downloads & Store als Druckbericht: die drei Karten des Reiters nacheinander (Apps im Vergleich, Sterne im App Store, Neueste Version)
  function buildStoreReport(opts) {
    const part = (title, fill) => { const d = h("div"); fill(d); return [h("h2", {}, title), d]; };
    return [opts && opts.all ? null : h("div", { class: "pr-head" }, h("div", { class: "pr-k" }, tx("Downloads & Store", "Downloads & store")), h("h1", {}, tx("Downloads und Store", "Downloads and store"))),
      part(tx("Apps im Vergleich", "Apps compared"), d => renderAppCompare(d, true)), part(tx("Sterne im App Store", "Stars in the App Store"), d => renderOfficial(d)),
      part(tx("Neueste Version im Store", "Latest version in the store"), d => renderLatest(d)),
      h("div", { class: "pr-foot" }, tx("Quellen: App Store Connect (Analytics-Berichte), öffentliche Store-Bewertung. Datenstand ", "Sources: App Store Connect (analytics reports), public store rating. Data as of ") + fmtDate(DATA.dataAsOf || "") + ".")];
  }

  // ---- App-Bericht zum Drucken: eine App gegen alle Apple-Apps des gewählten Kunden, andere Apps ohne Namen ----
  function printControl(facts) {
    const sel = h("select", { "aria-label": tx("App für den App-Bericht", "App for the app report") }, facts.map(f => h("option", { value: f.key }, appLabel(f.a))));
    if (facts.length === 1) sel.setAttribute("disabled", "");
    return h("span", { class: "row", style: "gap:.5rem" }, sel, h("button", { type: "button", class: "btn", onclick: () => printApp(sel.value || facts[0].key) }, tx("App-Bericht drucken", "Print app report")));
  }
  function printApp(key) {
    const win = windowOf(), peers = DATA.apps.filter(a => a.platform === "apple" && inSel(state.f.customerId, a.customerId)).map(a => appFacts(a, win));
    const me = peers.find(f => f.key === key); if (!me) return;
    const ps = peerStats(peers), n = peers.length;
    const tiles = METRICS.map(m => { const v = m.val(me), k = markOf(m, me, ps), r = rankOf(m, me, ps);
      return h("div", { class: "pr-tile" }, h("div", { class: "pr-l" }, tx(m.de, m.en)), h("div", { class: "pr-v" }, v === null ? "–" : m.show(v), h("small", {}, ps[m.id].med === null ? "" : tx(" Median ", " median ") + m.show(ps[m.id].med))),
        h("div", { class: "pr-r" + (k > 0 ? " up" : k < 0 ? " down" : "") }, r === null ? tx("kein Rang (zu wenig Daten)", "no rank (too little data)") : arrow(k) + tx("Platz " + r + " von " + ps[m.id].n, "rank " + r + " of " + ps[m.id].n))); });
    const notes = METRICS.filter(m => markOf(m, me, ps)).map(m => { const k = markOf(m, me, ps);
      return h("li", {}, h("b", { class: k > 0 ? "up" : "down" }, arrow(k)), tx(m.de + ": " + m.show(m.val(me)) + ", Median " + m.show(ps[m.id].med) + (k > 0 ? " – deutlich besser als die anderen Apps." : " – deutlich schlechter als die anderen Apps."),
        m.en + ": " + m.show(m.val(me)) + ", median " + m.show(ps[m.id].med) + (k > 0 ? " – clearly better than the other apps." : " – clearly worse than the other apps."))); });
    const hints = [];
    if (markOf(METRICS[1], me, ps) < 0) hints.push(tx("Weniger Einblendungen als üblich führen zum Download. Da der Code gleich ist, lohnt ein Blick auf den Store-Auftritt: Bilder, Beschreibung, Name.", "Fewer impressions than usual lead to a download. Since the code is the same, look at the store listing: images, description, name."));
    const webMed = medianOf(peers.filter(f => f.first >= FQ.minDl).map(f => f.webShare));
    if (me.first >= FQ.minDl && webMed !== null && me.webShare < webMed / 2) hints.push(tx("Nur " + fmt(me.webShare, 0) + " % der Erstinstallationen kommen über Webseiten, im Median " + fmt(webMed, 0) + " %. Ein Link zur App auf der eigenen Webseite kann helfen.", "Only " + fmt(me.webShare, 0) + " % of first-time downloads come from websites, median " + fmt(webMed, 0) + " %. A link to the app on the provider’s website can help."));
    if (markOf(METRICS[4], me, ps) < 0) hints.push(tx("Mehr Löschungen als bei den anderen Apps. Die negativen Rezensionen im Zeitraum nennen oft den Grund.", "More deletions than the other apps. The negative reviews in the period often name the reason."));
    const conv = peers.filter(METRICS[1].ok).sort((x, y) => y.conv - x.conv), cmax = conv.length ? conv[0].conv : 1;
    let anon = 0;
    const bars = conv.map(f => h("div", { class: "pr-bar" + (f === me ? " me" : "") }, h("span", {}, f === me ? appLabel(f.a) : "App " + (++anon)), h("i", {}, h("u", { style: "width:" + (100 * f.conv / cmax).toFixed(1) + "%" })), h("span", { class: "num" }, fmt(f.conv, 1) + " %")));
    printOut([h("div", { class: "pr-head" }, h("div", { class: "pr-k" }, tx("App-Bericht · ", "App report · ") + win.label), h("h1", {}, appLabel(me.a)),
      h("p", {}, n > 1 ? tx("Vergleich mit " + (n - 1) + " weiteren Apps. Die anderen Apps werden nicht genannt.", "Compared with " + (n - 1) + " other apps. The other apps are not named.") : tx("Keine weiteren Apps zum Vergleich in der Auswahl.", "No other apps to compare with in the selection."))),
      h("div", { class: "pr-tiles" }, tiles),
      h("h2", {}, tx("Was auffällt", "What stands out")), notes.length ? h("ul", {}, notes) : h("p", {}, tx("Keine Kennzahl weicht deutlich vom Median ab.", "No figure differs clearly from the median.")),
      conv.length >= 2 ? [h("h2", {}, tx("Einblendungen, die zum Download führen", "Impressions leading to a download")), h("div", { class: "pr-bars" }, bars)] : null,
      hints.length ? [h("h2", {}, tx("Hinweise", "Suggestions")), h("ul", {}, hints.map(t => h("li", {}, t)))] : null,
      h("div", { class: "pr-foot" }, tx("Quellen: App Store Connect (Analytics-Berichte), öffentliche Store-Bewertung. Abstürze und Sitzungen nur von Geräten mit Zustimmung zur Datenweitergabe. Datenstand ", "Sources: App Store Connect (analytics reports), public store rating. Crashes and sessions only from devices that agreed to share data. Data as of ") + fmtDate(DATA.dataAsOf) + ".")], tx("App-Bericht-", "App-report-") + fileSlug(me.a.appName));
  }
  // ---- Druckberichte: gemeinsames Gerüst für alle Ausdrucke und für die Zwischenablage ----
  // Jeder Ausdruck beginnt mit Datum und Uhrzeit des Drucks und dem eingestellten Filter (Wunsch des Nutzers, 25.10.2026): Die Bauer
  // (buildMonthly, buildTopicsReport, …) liefern nur den Inhalt; printFrame setzt Stempel und Filterkasten davor.
  const printStamp = () => h("div", { class: "pr-stamp" }, tx("Gedruckt am ", "Printed on ") + fmtDate(new Date().toISOString()));
  function printFilterBox() {
    const pool = reviews.filter(r => !rivalHidden(r, state.f)).length;
    return h("div", { class: "pr-filter" }, h("div", { class: "pr-k" }, tx("Filter (Auswahl im Bericht)", "Filter (selection in the report)")),
      h("table", {}, h("tbody", {}, filterSummary().map(r => h("tr", {}, h("th", {}, r.label), h("td", {}, r.value))))),
      h("div", { class: "pr-fsum" }, fmtInt(current.length) + tx(" von ", " of ") + fmtInt(pool) + tx(" Rezensionen in der Auswahl · Datenstand ", " reviews in the selection · data as of ") + fmtDate(DATA.dataAsOf || "")));
  }
  const printFrame = nodes => [printStamp(), printFilterBox(), nodes];
  // Dateiname für „Als PDF sichern“ (Wunsch des Nutzers, 25.10.2026): Browser nehmen den Seitentitel als Vorschlag. Aufbau
  // „<bericht>-<auswahl>-JJJJMMTT-HHMMSS“, Auswahl = App-Namen (bis zwei), sonst Kunde, sonst „alle-apps“; nur ASCII, Umlaute umgeschrieben.
  const fileSlug = v => String(v || "").replace(/[ÄÀÁÂ]/g, "Ae").replace(/[ÖÒÓÔ]/g, "Oe").replace(/[ÜÙÚÛ]/g, "Ue").replace(/[äàáâ]/g, "ae").replace(/[öòóô]/g, "oe").replace(/[üùúû]/g, "ue").replace(/ß/g, "ss")
    .replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  function printFileName(base) {
    const apps = (state.f.appKey || []).map(k => (appsByKey.get(k) || {}).appName).filter(Boolean), custs = (state.f.customerId || []).map(id => (DATA.apps.find(a => a.customerId === id) || {}).customerName || id);
    const scope = apps.length && apps.length <= 2 ? apps.map(fileSlug).join("-") : custs.length && custs.length <= 2 ? custs.map(fileSlug).join("-") : tx("alle-Apps", "all-apps");
    const now = new Date(), two = n => String(n).padStart(2, "0");
    return [base, scope, now.getFullYear() + two(now.getMonth() + 1) + two(now.getDate()) + "-" + two(now.getHours()) + two(now.getMinutes()) + two(now.getSeconds())].filter(Boolean).join("-");
  }
  // Druckausgabe (#printout): nur während body.printing sichtbar, im hellen Schema
  function printOut(nodes, fileBase) {
    const out = $("printout"); out.replaceChildren();
    put(out, printFrame(nodes));
    // Papier ist weiß: für den Druck das helle Schema, danach das vorherige wiederherstellen; der Seitentitel wird zum Dateinamen
    const root = document.documentElement, theme = root.dataset.theme, title = document.title;
    document.body.classList.add("printing"); root.dataset.theme = "light"; document.title = printFileName(fileBase || tx("Bericht", "Report"));
    const done = () => { document.body.classList.remove("printing"); document.title = title; if (theme) root.dataset.theme = theme; else delete root.dataset.theme; };
    if (window.print) { if (window.addEventListener) window.addEventListener("afterprint", done, { once: true }); window.print(); setTimeout(done, 1000); } else done();
  }
  // Zwischenablage (Wunsch des Nutzers, 25.10.2026: Bericht in Jira, Word, Teams oder Mail einfügen): derselbe Bericht wie der Ausdruck.
  // Der Bericht wird kurz unsichtbar gerendert (body.copying), damit die berechneten Stile vorliegen; eine Kopie bekommt sie als
  // style-Attribute (Word und Co. kennen unser CSS nicht), jedes SVG wird zu einem PNG, dann gehen HTML und reiner Text in die Ablage.
  const COPY_PROPS = ["color", "background-color", "font-family", "font-size", "font-weight", "font-style", "line-height", "text-align", "text-transform",
    "letter-spacing", "border-top", "border-right", "border-bottom", "border-left", "border-radius", "border-collapse", "border-spacing", "padding", "margin",
    "display", "width", "height", "vertical-align", "white-space", "text-decoration", "list-style", "opacity", "fill", "stroke", "stroke-width", "box-sizing"];
  function inlineStyles(src) {
    const clone = src.cloneNode(true);
    const walk = (a, b) => { if (a.nodeType !== 1) return; const cs = getComputedStyle(a); const css = [];
      for (const prop of COPY_PROPS) { const v = cs.getPropertyValue(prop); if (v && v !== "none" && v !== "normal" && v !== "auto") css.push(prop + ":" + v); }
      b.setAttribute("style", css.join(";")); b.removeAttribute("class"); b.removeAttribute("data-tip"); b.removeAttribute("tabindex");
      for (let i = 0; i < a.children.length; i++) walk(a.children[i], b.children[i]); };
    walk(src, clone);
    return clone;
  }
  const svgToPng = (svgSrc, svgClone) => new Promise(resolve => {
    const box = svgSrc.getBoundingClientRect(), w = Math.max(1, Math.round(box.width)), hgt = Math.max(1, Math.round(box.height));
    svgClone.setAttribute("xmlns", "http://www.w3.org/2000/svg"); svgClone.setAttribute("width", w); svgClone.setAttribute("height", hgt);
    const img = new Image(), done = src => { const el = document.createElement("img"); el.setAttribute("width", w); el.setAttribute("height", hgt); el.setAttribute("src", src); el.setAttribute("style", "display:block;max-width:100%"); svgClone.replaceWith(el); resolve(); };
    img.onload = () => { try { const cv = document.createElement("canvas"); cv.width = w * 2; cv.height = hgt * 2; const g = cv.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, cv.width, cv.height); g.drawImage(img, 0, 0, cv.width, cv.height); done(cv.toDataURL("image/png")); } catch (e) { svgClone.remove(); resolve(); } };
    img.onerror = () => { svgClone.remove(); resolve(); };
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(svgClone));
  });
  async function writeClipboard(html, text) {
    if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.write && typeof ClipboardItem !== "undefined") {
      await navigator.clipboard.write([new ClipboardItem({ "text/html": new Blob([html], { type: "text/html" }), "text/plain": new Blob([text], { type: "text/plain" }) })]);
      return;
    }
    const listener = e => { e.clipboardData.setData("text/html", html); e.clipboardData.setData("text/plain", text); e.preventDefault(); };
    document.addEventListener("copy", listener);
    const ok = document.execCommand && document.execCommand("copy");
    document.removeEventListener("copy", listener);
    if (!ok) throw new Error("clipboard");
  }
  async function copyOut(nodes) {
    const out = $("printout"); out.replaceChildren();
    put(out, printFrame(nodes));
    if (typeof getComputedStyle !== "function" || !out.cloneNode) throw new Error("unsupported");
    const root = document.documentElement, theme = root.dataset.theme;
    document.body.classList.add("copying"); root.dataset.theme = "light";
    try {
      await new Promise(res => setTimeout(res, 50));  // Layout abwarten, damit Maße und Stile stimmen
      const clone = inlineStyles(out), srcSvgs = Array.from(out.querySelectorAll("svg")), cloneSvgs = Array.from(clone.querySelectorAll("svg"));
      for (let i = 0; i < srcSvgs.length; i++) await svgToPng(srcSvgs[i], cloneSvgs[i]);
      const html = "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body>" + new XMLSerializer().serializeToString(clone) + "</body></html>";
      await writeClipboard(html, out.innerText || out.textContent || "");
    } finally { document.body.classList.remove("copying"); if (theme) root.dataset.theme = theme; else delete root.dataset.theme; }
  }
  async function copyPlain(text) {
    if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) { await navigator.clipboard.writeText(text); return; }
    const ta = h("textarea", { style: "position:fixed;left:-9999px;top:0" }); ta.value = text; document.body.append(ta); if (ta.select) ta.select();
    const ok = document.execCommand && document.execCommand("copy"); ta.remove();
    if (!ok) throw new Error("clipboard");
  }
  // Knopf, der nach dem Kopieren kurz „Kopiert ✓“ zeigt (bzw. die Fehlermeldung); `run` liefert ein Promise
  function feedbackButton(cls, label, run) {
    const btn = h("button", { type: "button", class: cls }, label);
    btn.addEventListener("click", e => { if (e && e.stopPropagation) e.stopPropagation(); if (btn.dataset.busy) return; btn.dataset.busy = "1";
      Promise.resolve().then(run).then(() => { btn.textContent = tx("Kopiert ✓", "Copied ✓"); }, () => { btn.textContent = tx("Kopieren fehlgeschlagen", "Copy failed"); })
        .then(() => setTimeout(() => { btn.textContent = label; delete btn.dataset.busy; }, 2000)); });
    return btn;
  }
  const copyTextButton = textOf => feedbackButton("linkbtn", tx("In Zwischenablage", "Copy to clipboard"), () => copyPlain(textOf()));
  // Knopfpaar „Bericht drucken“ / „In Zwischenablage“ je Karte, links neben dem Zuklappknopf (CSS .sec>.prbar); ohne cardId nur gebaut
  // (Diagrammkarte setzt es selbst in die Kopfzeile). Die alte Leiste wird ersetzt, weil der Inhalt vom Filter abhängt.
  const prBars = {};
  function removeReportButtons(cardId) { if (prBars[cardId] && prBars[cardId].remove) prBars[cardId].remove(); delete prBars[cardId]; }
  function reportButtons(cardId, entry, printLabel) {
    const bar = h("div", { class: "prbar" }, h("button", { type: "button", class: "btn", onclick: () => printOut(entry.build(), entry.file) }, printLabel || tx("Bericht drucken", "Print report")),
      feedbackButton("btn", tx("In Zwischenablage", "Copy to clipboard"), () => copyOut(entry.build())));
    if (!cardId) return bar;
    const card = $(cardId); if (!card || !card.append) return bar;
    if (prBars[cardId] && prBars[cardId].remove) prBars[cardId].remove();
    // direkt hinter der Kopfzeile (.chead): absolut positioniert oben rechts; auf schmalen Bildschirmen (CSS) als Zeile unter dem Titel
    const head = card.firstElementChild;
    if (head && head.nextSibling && card.insertBefore) card.insertBefore(bar, head.nextSibling); else card.append(bar);
    prBars[cardId] = bar;
    return bar;
  }
  // Alle Druckberichte, in der Reihenfolge der Reiter. `on` sagt, ob es für die Auswahl etwas zu drucken gibt; `build(opts)` liefert den
  // Inhalt (opts.all = Teil des Gesamtberichts, dann ohne eigene Kopfzeile). Ohne KI gibt es keinen KI-Bericht (featOn/aiOn in ki.js).
  const PRINTERS = {
    overview: { file: tx("Monatsbericht", "Monthly-report"), title: tx("Überblick", "Overview"), on: () => overviewRows().length > 0, build: opts => buildMonthly(overviewRows(), opts) },
    topics: { file: tx("Rezensionen-Themen", "Review-topics"), title: tx("Rezensionen", "Reviews"), on: () => current.length > 0, build: opts => buildTopicsReport(opts) },
    stability: { file: tx("Stabilitaet", "Stability"), title: tx("Stabilität", "Stability"), on: () => stabilityPrintable(), build: opts => [opts && opts.all ? null : h("div", { class: "pr-head" }, h("div", { class: "pr-k" }, tx("Stabilität", "Stability")), h("h1", {}, tx("Abstürze und Sitzungen", "Crashes and sessions"))), buildStability(),
      h("div", { class: "pr-foot" }, tx("Quelle: App Store Connect (Analyse-Berichte), nur Geräte mit Zustimmung zur Datenweitergabe, Näherungswerte. Datenstand ", "Source: App Store Connect (analytics reports), only devices that agreed to share data, approximations. Data as of ") + fmtDate(DATA.dataAsOf || "") + ".")] },
    store: { file: tx("Downloads-Store", "Downloads-store"), title: tx("Downloads & Store", "Downloads & store"), on: () => DATA.apps.some(inScope), build: opts => buildStoreReport(opts) },
    charts: { file: tx("Diagramme", "Charts"), title: tx("Diagramme", "Charts"), on: () => chartStores().length > 0, build: opts => buildChartsReport(opts) },
    questions: { file: tx("KI-Anfragen", "AI-questions"), title: tx("KI-Anfragen", "AI questions"), on: () => aiOn() && featOn("questions") && (DATA.aiQuestions || []).length > 0, build: opts => buildQuestionsReport(opts) },
    limits: { file: tx("Datenstand", "Data-status"), title: tx("Datenstand", "Data status"), on: () => true, build: opts => { const d = h("div"); renderLimits(d); return [opts && opts.all ? null : h("div", { class: "pr-head" }, h("div", { class: "pr-k" }, tx("Datenstand", "Data status")), h("h1", {}, tx("Wie vollständig sind die Daten?", "How complete is the data?"))), d]; } },
  };
  const PRINT_ORDER = ["overview", "topics", "stability", "store", "charts", "questions", "limits"];
  // Gesamtbericht (Knöpfe neben „Filter zurücksetzen“): alle verfügbaren Berichte, gruppiert nach Reitern, mit Inhaltsverzeichnis
  function buildAllReport(opts) {
    const parts = PRINT_ORDER.filter(k => !(opts && opts.skipQuestions && k === "questions")).map(k => PRINTERS[k]).filter(p => p.on());
    return [h("div", { class: "pr-head" }, h("div", { class: "pr-k" }, tx("Gesamtbericht", "Full report")), h("h1", {}, tx("Bewertungen und Rezensionen", "Ratings and reviews")),
        h("p", {}, tx("Inhalt: ", "Contents: ") + parts.map(p => p.title).join(" · "))),
      parts.map(p => h("div", { class: "pr-section" }, h("h1", { class: "pr-tab" }, p.title), p.build({ all: true })))];
  }
  PRINTERS.all = { file: tx("Gesamtbericht", "Full-report"), title: tx("Gesamtbericht", "Full report"), on: () => true, build: () => buildAllReport() };
  // Gesamtbericht mit KI-Anfragen: vorher fragen, ob die gespeicherten Fragen und Antworten mit hinein sollen (Wunsch des Nutzers,
  // 25.10.2026); „Nein“ lässt den ganzen Block weg. Ohne KI oder ohne Fragen gibt es keine Rückfrage.
  function withQuestionChoice(run) {
    if (!PRINTERS.questions.on()) { run({}); return; }
    const n = (DATA.aiQuestions || []).length;
    confirmDialog(tx("Sollen die KI-Anfragen mit ausgegeben werden?", "Include the AI questions?"),
      tx(n + (n === 1 ? " gespeicherte Frage mit Antwort" : " gespeicherte Fragen mit Antworten") + " im Reiter „KI-Anfragen“. Bei „Nein“ fehlt der ganze Block im Bericht.", n + (n === 1 ? " stored question with answer" : " stored questions with answers") + " on the “AI questions” tab. With “No” the whole block is left out."),
      () => run({}), () => run({ skipQuestions: true }));
  }
  if ($("printall").addEventListener) {
    $("printall").addEventListener("click", () => withQuestionChoice(opts => printOut(buildAllReport(opts), PRINTERS.all.file)));
    const copyAll = feedbackButton("btn", tx("In Zwischenablage", "Copy to clipboard"), () => new Promise((res, rej) => withQuestionChoice(opts => copyOut(buildAllReport(opts)).then(res, rej))));
    if ($("copyall").replaceWith) $("copyall").replaceWith(copyAll); else $("copyall").addEventListener("click", () => copyAll.listeners.click.forEach(f => f()));
  }

  // ---- Kopfzeile: wann frühestens wieder abgerufen wird (settings.minRefreshMinutes, wie collect.py ohne --force) ----
  (function refreshHint() {
    const last = DATA.apps.map(a => a.lastSuccessfulSync).filter(Boolean).sort().pop(), mins = (DATA.refresh || {}).minRefreshMinutes, el = $("refresh");
    if (!last || !mins || isNaN(Date.parse(last))) { el.textContent = ""; return; }
    const next = new Date(Date.parse(last) + mins * 6e4), ago = Math.round((Date.now() - Date.parse(last)) / 6e4);
    el.textContent = tx("Letzter Abruf vor ", "Last fetch ") + (ago < 120 ? ago + tx(" Minuten", " minutes ago") : Math.round(ago / 60) + tx(" Stunden", " hours ago"))
      + (next.getTime() > Date.now() ? tx(" · neuer Abruf frühestens ", " · next fetch not before ") + fmtDate(next.toISOString()) : tx(" · ein neuer Abruf ist möglich", " · a new fetch is possible"));
  })();
