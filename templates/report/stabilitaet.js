  // Stabilität: Abstürze und Sitzungen.
  // ---- Stabilität ----
  // ---- Stabilität (folgt Kunde, App, Plattform und Zeitraum aus dem Filter oben) ----
  let renderStability = () => {};
  let buildStability = () => null;      // liefert die Stabilitätsauswertung als frisches Element für den Druckbericht (null ohne Daten)
  let stabilityPrintable = () => false; // ob es für die Auswahl etwas zu drucken gibt
  (function stability() {
    const host = $("stabout"), S = DATA.stability || [];
    if (!S.length) { put(host, h("div", { class: "muted" }, tx("Keine Stabilitätsdaten vorhanden. Abruf: ./ratings.sh stability", "No stability data. Fetch: ./ratings.sh stability"))); return; }
    const pct = r => fmt(r / 10, 2) + " %"; // je 1000 Sitzungen ÷ 10 = Prozent
    function rateCell(o) {
      if (o.rate === null) return h("span", { class: "muted" }, "–");
      const bad = o.rate >= 10, warn = o.rate >= 3;
      return h("span", { class: "pill " + (bad ? "r1" : warn ? "r3" : "r5"), "data-tip": o.crashes + tx(" Abstürze auf ", " crashes in ") + fmtInt(o.sessions) + tx(" Sitzungen", " sessions") }, fmt(o.rate) + " (" + pct(o.rate) + ")");
    }
    function table(title, rows, labeler) {
      const sorted = rows.slice().sort((a, b) => b.sessions - a.sessions).slice(0, 15);
      return h("div", { style: "margin-top:1.2rem" }, h("h3", {}, title), h("div", { class: "tablewrap", style: "max-height:none" },
        h("table", {}, h("thead", {}, h("tr", {}, ["", tx("Sitzungen", "Sessions"), tx("Abstürze", "Crashes"), tx("je 1000 Sitzungen", "per 1,000 sessions"), tx("Zeitraum", "Period"), tx("Hinweis", "Note")].map(t => h("th", {}, t)))),
          h("tbody", {}, sorted.map(o => h("tr", {}, h("td", {}, h("b", {}, labeler(o.key))), h("td", { class: "num" }, fmtInt(o.sessions)), h("td", { class: "num" }, fmtInt(o.crashes)), h("td", {}, rateCell(o)),
            h("td", { class: "num" }, fmtDay(o.first) + " → " + fmtDay(o.last)), h("td", { class: "muted" }, o.sessions === 0 ? tx("keine Sitzungsdaten, keine Rate", "no session data, no rate") : o.small ? tx("⚠ kleine Stichprobe (< 5 Abstürze)", "⚠ small sample (< 5 crashes)") : "")))))));
    }
    function draw(target) {
      const box = target || host; box.replaceChildren();
      if (state.f.platform === "google") { put(box, h("div", { class: "muted" }, tx("Stabilitätsdaten gibt es nur für Apple. Plattformfilter auf „Alle“ oder „Apple“ stellen.", "Stability data exists for Apple only. Set the platform filter to “All” or “Apple”."))); return; }
      const sel = S.filter(inScope);
      if (!sel.length) { put(box, h("div", { class: "muted" }, tx("Für diese Auswahl liegen keine Stabilitätsdaten vor.", "No stability data for this selection."))); return; }
      const from = state.f.from || "", to = state.f.to || "", inPeriod = r => r[0] >= from && (!to || r[0] <= to);
      const all = sel.flatMap(x => x.crashes.concat(x.sessions)).map(r => r[0]).filter(d => inPeriod([d])).sort();
      const maxD = all.length ? all[all.length - 1] : asOfDate;
      const cr = sel.flatMap(x => x.crashes).filter(inPeriod), se = sel.flatMap(x => x.sessions).filter(inPeriod);
      const tot = stabilityBy(cr, se, () => "alle")[0] || { crashes: 0, sessions: 0, rate: null };
      put(box, h("div", { class: "grid kpis", style: "margin-top:1rem" }, [[fmtInt(tot.sessions), tx("Sitzungen", "Sessions")], [fmtInt(tot.crashes), tx("Abstürze", "Crashes")], [tot.rate === null ? "–" : fmt(tot.rate), tx("Abstürze je 1000 Sitzungen", "Crashes per 1,000 sessions") + (tot.rate === null ? "" : " (" + pct(tot.rate) + ")")], [fmtDay(all[0]) + " → " + fmtDay(maxD), tx("Datenzeitraum", "Data period")]].map(([v, l]) => h("div", { class: "card kpi" }, h("b", { class: "num", style: "font-size:" + (v.length > 14 ? "1.05rem" : "1.8rem") }, v), h("span", {}, l)))));
      put(box, h("div", { class: "warn" }, tx("Nur Apple, Näherungswerte. Daten gibt es erst ab Einrichtung der Berichtsanfrage.", "Apple only, approximations. Data exists only from the time the report request was set up.")));
      const byVer = stabilityBy(cr, se, r => r[1]).sort((a, b) => (a.first || "") < (b.first || "") ? -1 : 1);
      put(box, table(tx("Nach App-Version", "By app version"), byVer.slice(-15), k => k));
      put(box, table(tx("Nach Betriebssystemversion", "By OS version"), stabilityBy(cr, se, r => r[2]), k => k));
      put(box, table(tx("Nach Gerätetyp", "By device type"), stabilityBy(cr, se, r => r[3]), k => k));
      const wk = stabilityBy(cr, se, r => weekStart(r[0])).sort((a, b) => a.key < b.key ? -1 : 1);
      const keys = new Set(sel.map(x => x.customerId + "/" + x.appId)), neg = new Map();
      for (const r of reviews) if (keys.has(r.customerId + "/" + r.appId) && r.platform === "apple" && r.rating <= 2 && r.createdAt && inPeriod([r.createdAt.slice(0, 10)])) { const w = weekStart(r.createdAt.slice(0, 10)); neg.set(w, (neg.get(w) || 0) + 1); }
      if (wk.length >= 2) {
        const W = 560, H = 210, L = 30, B = 26, T = 12, n = wk.length, step = (W - L - 10) / n, bw = Math.max(3, Math.min(30, step - 4));
        // Zeitachse: nur so viele Beschriftungen, wie bei ca. 46 px je „TT.MM.“ nebeneinander passen (erste Woche, dann jede k-te)
        const every = Math.max(1, Math.ceil(n / Math.max(1, Math.floor((W - L - 10) / 46)))), label = k => k.slice(8, 10) + "." + k.slice(5, 7) + ".";
        const showLabel = i => i % every === 0;
        const maxRate = Math.max(1, ...wk.map(o => o.rate || 0)), maxNeg = Math.max(1, ...wk.map(o => neg.get(o.key) || 0));
        const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": tx("Absturzrate und negative Rezensionen pro Woche", "Crash rate and negative reviews per week") });
        wk.forEach((o, i) => {
          const nv = neg.get(o.key) || 0, hgt = (H - T - B) * nv / maxNeg, x = L + i * step + (step - bw) / 2;
          svg.append(s("rect", { x, y: H - B - hgt, width: bw, height: hgt, fill: COL.bad, rx: Math.min(4, bw / 2), opacity: .55, "data-tip": tx("Woche ab ", "Week from ") + fmtDay(o.key) + ": " + nv + tx(" negative Rezensionen", " negative reviews") }));
          if (showLabel(i)) svg.append(s("line", { x1: x + bw / 2, x2: x + bw / 2, y1: H - B, y2: H - B + 4, stroke: "var(--line2)" }), s("text", { x: x + bw / 2, y: H - 8, "text-anchor": "middle" }, label(o.key)));
        });
        const pts = wk.filter(o => o.rate !== null).map(o => [L + wk.indexOf(o) * step + step / 2, T + (H - T - B) * (1 - o.rate / maxRate), o]);
        if (pts.length > 1) svg.append(s("polyline", { points: pts.map(p => p[0] + "," + p[1]).join(" "), fill: "none", stroke: "var(--accent)", "stroke-width": 2.5, "stroke-linejoin": "round" }));
        pts.forEach(p => svg.append(s("circle", { cx: p[0], cy: p[1], r: 4, fill: "var(--solid)", stroke: "var(--accent)", "stroke-width": 2, "data-tip": tx("Woche ab ", "Week from ") + fmtDay(p[2].key) + ": " + fmt(p[2].rate) + " (" + pct(p[2].rate) + tx(") Abstürze je 1000 Sitzungen", ") crashes per 1,000 sessions") })));
        put(box, h("h3", { style: "margin-top:1.4rem" }, tx("Wochenverlauf: Absturzrate und negative Rezensionen (1–2 ★)", "Weekly trend: crash rate and negative reviews (1–2 ★)")), svg,
          h("div", { class: "legend" }, h("span", {}, h("i", { style: "background:var(--accent);border-radius:50%" }), tx("Abstürze je 1000 Sitzungen (Skala 0–", "Crashes per 1,000 sessions (scale 0–") + fmt(maxRate, 1) + ")"), h("span", {}, h("i", { style: "background:var(--bad)" }), tx("negative Rezensionen (Skala 0–", "negative reviews (scale 0–") + maxNeg + ")")),
          h("div", { class: "note" }, tx("Zeitliche Übereinstimmung ist kein Beleg für eine Ursache. Wenige Wochen/Rezensionen = kaum belastbar.", "Coincidence in time is no proof of cause. Few weeks or reviews = not reliable.")));
      } else {
        put(box, h("h3", { style: "margin-top:1.4rem" }, tx("Wochenverlauf: Absturzrate und negative Rezensionen (1–2 ★)", "Weekly trend: crash rate and negative reviews (1–2 ★)")),
          h("div", { class: "warn" }, tx("Für diese Auswahl und diesen Zeitraum liegen " + (wk.length ? "nur Daten für eine Woche" : "keine Stabilitätsdaten") + " vor. Das Diagramm wird erst angezeigt, sobald mindestens zwei Wochen mit Abstürzen und Sitzungen vorhanden sind (Abruf: ./ratings.sh stability).", (wk.length ? "Only one week of data" : "No stability data") + " for this selection and period. The chart appears once at least two weeks with crashes and sessions exist (fetch: ./ratings.sh stability).")));
      }
      if (!target) sortTables(box, "stab");
    }
    renderStability = () => { draw(); if (stabilityPrintable()) reportButtons("stab", PRINTERS.stability); else removeReportButtons("stab"); };
    buildStability = () => { const d = h("div", { class: "pr-stab" }); draw(d); return d; };
    stabilityPrintable = () => state.f.platform !== "google" && S.some(inScope);
  })();


