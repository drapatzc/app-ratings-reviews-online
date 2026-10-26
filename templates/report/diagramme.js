  // Diagrammkarte (CHARTS), Store-Kennzahlen und Versionsleiste.
  // ---- Diagramme: eine Karte mit Auswahlbox; je Store ein Bild, Apple und Google nebeneinander ----
  // Die Stores kommen aus dem Plattform-Filter; ohne Filter alle Stores, für die Apps in der Auswahl konfiguriert sind.
  // Jedes Diagramm zeichnet mit draw(k, rs, W) ein Bild für Store k; na(k) nennt den Grund, wenn es das Bild dort nicht gibt.
  const STAB_NA = tx("Für Google-Apps werden noch keine Absturz- und Sitzungsdaten abgerufen.", "Crash and session data is not yet fetched for Google apps.");
  const GOOGLE_ONLY = tx("Apple liefert zu Rezensionen keine App-Version, kein Betriebssystem und kein Gerät.", "Apple provides no app version, operating system or device with reviews.");
  function niceMax(v) { const p = 10 ** Math.floor(Math.log10(v)), f = v / p; return [1, 1.5, 2, 3, 4, 5, 6, 8, 10].find(m => f <= m) * p; }
  const chartLegend = items => h("div", { class: "legend" }, items.map(([c, l, round]) => h("span", {}, h("i", { style: "background:" + c + (round ? ";border-radius:50%" : "") }), l)));
  const noData = () => h("div", { class: "muted" }, tx("Keine Daten für diese Auswahl.", "No data for this selection."));
  // Säulen (gestapelt) und Linien auf gemeinsamer Skala; Linien mit right: true nutzen die rechte Skala 0 … rightMax.
  function columnsSvg({ labels, bars = [], lines = [], rightMax, rightFmt, leftFmt = fmtInt, W, H = 230, label, lane }) {
    const L = 40, R = rightMax ? 40 : 10, T = 12, B = 24, n = labels.length, step = (W - L - R) / n, bw = Math.max(3, Math.min(28, step * .62));
    const tot = labels.map((_, i) => bars.reduce((a, b) => a + (b.values[i] || 0), 0));
    const max = niceMax(Math.max(1e-9, ...tot, ...lines.filter(l => !l.right).flatMap(l => l.values.filter(v => v !== null))));
    const y = v => T + (H - T - B) * (1 - v / max), yr = v => T + (H - T - B) * (1 - v / rightMax);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": label });
    [0, .5, 1].forEach(k => {
      svg.append(s("line", { x1: L, x2: W - R, y1: y(max * k), y2: y(max * k), stroke: "var(--line)", "stroke-dasharray": k ? "3 4" : "" }), s("text", { x: L - 6, y: y(max * k) + 3, "text-anchor": "end" }, leftFmt(max * k)));
      if (rightMax) svg.append(s("text", { x: W - R + 6, y: yr(rightMax * k) + 3 }, rightFmt(rightMax * k)));
    });
    const every = Math.max(1, Math.ceil(n / Math.floor((W - L - R) / 42)));
    labels.forEach((lab, i) => {
      const x = L + i * step + (step - bw) / 2; let acc = 0;
      bars.forEach(b => { const v = b.values[i]; if (!v) return; svg.append(s("rect", { x, y: y(acc + v), width: bw, height: y(acc) - y(acc + v), fill: b.color, rx: Math.min(3, bw / 2), "data-tip": lab + ": " + b.name + " " + (b.fmt || leftFmt)(v) })); acc += v; });
      if (i % every === 0) svg.append(s("text", { x: L + i * step + step / 2, y: H - 7, "text-anchor": "middle" }, lab));
    });
    lines.forEach(l => {
      const yy = l.right ? yr : y, pts = l.values.map((v, i) => v === null ? null : [L + i * step + step / 2, yy(v), i]).filter(Boolean);
      if (pts.length > 1) svg.append(s("polyline", { points: pts.map(p => p[0] + "," + p[1]).join(" "), fill: "none", stroke: l.color, "stroke-width": 2.5, "stroke-linejoin": "round" }));
      pts.forEach(p => svg.append(s("circle", { cx: p[0], cy: p[1], r: 3.5, fill: "var(--solid)", stroke: l.color, "stroke-width": 2, "data-tip": labels[p[2]] + ": " + l.name + " " + l.fmt(l.values[p[2]]) })));
    });
    if (lane) return [svg, addLane(svg, { W, H, L, R, step, bw, top: T, bottom: H - B, buckets: lane.buckets, kind: lane.kind }, lane.k)];
    return svg;
  }
  // Waagerechte Balkenliste im Stil des Berichts; rows: { label, value, text, color, onclick (optional, macht die Zeile klickbar) }
  function barList(rows) {
    const max = Math.max(1, ...rows.map(r => r.value));
    return h("div", { class: "bars" + (rows.every(r => String(r.label).length <= 6) ? " short" : "") }, rows.map(r => {
      const fill = h("div", { class: "fill" }); fill.style.width = (100 * r.value / max) + "%"; if (r.color) fill.style.background = r.color;
      const attrs = { class: "bar" + (r.onclick ? " click" : "") + (r.active ? " active" : ""), "data-tip": r.label + ": " + (r.text || r.value) + (r.tip ? "\n" + r.tip : "") };
      if (r.onclick) { attrs.onclick = r.onclick; attrs.role = "button"; attrs.tabindex = "0"; attrs["aria-pressed"] = String(!!r.active); attrs.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); r.onclick(); } }; }
      return h("div", attrs, h("div", { class: "t" }, r.label), h("div", { class: "track" }, fill), h("div", { class: "v" }, r.text || String(r.value)));
    }));
  }
  // Themen: je Thema Anzahl, Ø Sterne und Anteil an den negativen Rezensionen; onPick(id) wählt das Thema nur im Bereich „Themen und Wörter“
  function topicRows(rs) { return TOPICS.map(t => { const list = rs.filter(r => reviewTopics(r).includes(t.id)); return { t, list, st: stats(list) }; }).filter(x => x.list.length).sort((a, b) => b.list.length - a.list.length); }
  // activeId: aktuell gewähltes Thema (Balken wird hervorgehoben, nochmaliger Klick hebt die Auswahl auf)
  function topicBars(rs, onPick, activeId) {
    if (!TOPICS.length) return h("div", { class: "muted" }, tx("Kein Themen-Wörterbuch gefunden (config/themen.json).", "No topic dictionary found (config/themen.json)."));
    const rows = topicRows(rs); if (!rows.length) return noData();
    const negAll = stats(rs).neg;
    return [barList(rows.map(x => ({ label: tx(x.t.de, x.t.en), value: x.list.length, color: avgColor(x.st.avg), onclick: onPick ? () => onPick(x.t.id) : undefined, active: activeId === x.t.id,
      text: x.list.length + " · Ø " + fmt(x.st.avg) + (negAll ? " · " + fmt(100 * x.st.neg / negAll, 0) + tx(" % der negativen", " % of negatives") : "") + (x.list.length < SMALL ? " ⚠" : ""),
      tip: tx("Art: ", "Kind: ") + x.t.kind + (onPick ? (activeId === x.t.id ? tx(" · Klick hebt die Auswahl auf", " · click clears the selection") : tx(" · Klick listet die Rezensionen zu diesem Thema unter den Balken", " · click lists the reviews on this topic below the bars")) : "") }))),
      h("div", { class: "note" }, tx("Eine Rezension kann mehrere Themen treffen. Farbe: Ø Sterne der Rezensionen zum Thema. ⚠ = kleine Stichprobe (< " + SMALL + ").", "A review can match several topics. Colour: avg stars of the reviews on the topic. ⚠ = small sample (< " + SMALL + ")."))];
  }
  // Netto-Saldo je Monat: Säulen nach oben (mehr positive) oder unten (mehr negative), Nulllinie in der Mitte
  function netChart(rs, W, k) {
    const months = [...groupBy(rs.filter(monthKey), monthKey).entries()].sort((a, b) => a[0] < b[0] ? -1 : 1);
    if (!months.length) return noData();
    const data = months.map(([m, l]) => { const st = stats(l); return { m, v: netScore(st), n: st.rated }; });
    const H = 230, L = 44, R = 10, T = 12, B = 24, n = data.length, step = (W - L - R) / n, bw = Math.max(3, Math.min(28, step * .62)), y = v => T + (H - T - B) * (1 - (v + 100) / 200);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": tx("Zufrieden minus unzufrieden pro Monat", "Happy minus unhappy per month") });
    [100, 50, 0, -50, -100].forEach(v => svg.append(s("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: v === 0 ? "var(--muted)" : "var(--line)", "stroke-dasharray": v ? "3 4" : "" }), s("text", { x: L - 6, y: y(v) + 3, "text-anchor": "end" }, (v > 0 ? "+" : "") + v)));
    const every = Math.max(1, Math.ceil(n / Math.floor((W - L - R) / 42)));
    data.forEach((d, i) => { const x = L + i * step + (step - bw) / 2;
      if (d.v !== null) svg.append(s("rect", { x, y: Math.min(y(0), y(d.v)), width: bw, height: Math.max(1, Math.abs(y(0) - y(d.v))), fill: d.n < 5 ? "var(--line2)" : d.v >= 0 ? COL.good : COL.bad, rx: Math.min(3, bw / 2),
        "data-tip": fmtMonth(d.m) + ": " + tx("zufrieden minus unzufrieden ", "happy minus unhappy ") + (d.v > 0 ? "+" : "") + fmt(d.v, 0) + " · " + d.n + tx(" Rezensionen", " reviews") + (d.n < 5 ? " ⚠" : "") }));
      if (i % every === 0) svg.append(s("text", { x: L + i * step + step / 2, y: H - 7, "text-anchor": "middle" }, fmtMonthShort(d.m))); });
    return [svg, addLane(svg, { W, H, L, R, step, bw, top: T, bottom: H - B, buckets: data.map(d => d.m + "-01"), kind: "month" }, k),
      chartLegend([[COL.good, tx("mehr positive als negative", "more positive than negative")], [COL.bad, tx("mehr negative als positive", "more negative than positive")], ["var(--line2)", tx("unter 5 Rezensionen im Monat", "fewer than 5 reviews in the month")]])];
  }
  const avgColor = a => a === null ? undefined : a >= 4 ? COL.good : a >= 3 ? COL.mid : COL.bad;
  function groupBars(rs, keyFn, limit) {
    const g = [...groupBy(rs, keyFn).entries()].map(([k, list]) => ({ k, list, st: stats(list) })).sort((a, b) => b.list.length - a.list.length).slice(0, limit);
    if (!g.length) return noData();
    return [barList(g.map(x => ({ label: x.k === NONE ? tx("(unbekannt)", "(unknown)") : x.k, value: x.list.length, text: x.list.length + " · Ø " + fmt(x.st.avg) + (x.list.length < SMALL ? " ⚠" : ""), color: avgColor(x.st.avg) }))),
      h("div", { class: "note" }, tx("⚠ = kleine Stichprobe (< " + SMALL + "). Farbe: Ø Sterne.", "⚠ = small sample (< " + SMALL + "). Colour: avg stars."))];
  }
  function trendChart(rs, W, k) {
    const months = [...groupBy(rs.filter(monthKey), monthKey).entries()].sort((a, b) => a[0] < b[0] ? -1 : 1);
    if (!months.length) return noData();
    const data = months.map(([m, list]) => { const st = stats(list); return { m, pos: st.pos, neg: st.neg, mid: st.rated - st.pos - st.neg, avg: st.avg }; });
    const rev = tx(" Rezensionen", " reviews");
    return [columnsSvg({ W, label: tx("Entwicklung im Zeitverlauf", "Trend over time"), labels: data.map(d => fmtMonthShort(d.m)), lane: { k, kind: "month", buckets: data.map(d => d.m + "-01") },
      bars: [[tx("negativ", "negative"), COL.bad, "neg"], ["neutral", COL.mid, "mid"], [tx("positiv", "positive"), COL.good, "pos"]].map(([name, color, k]) => ({ name, color, values: data.map(d => d[k]), fmt: v => fmtInt(v) + rev })),
      lines: [{ name: tx("Ø Sterne", "avg stars"), color: "var(--accent)", values: data.map(d => d.avg), right: true, fmt: v => fmt(v) + " ★" }], rightMax: 5, rightFmt: v => fmt(v, 0) + " ★" }),
      chartLegend([[COL.good, tx("positiv (4–5)", "positive (4–5)")], [COL.mid, tx("neutral (3)", "neutral (3)")], [COL.bad, tx("negativ (1–2)", "negative (1–2)")], ["var(--accent)", tx("Ø Sterne", "avg stars"), 1]])];
  }
  // Stabilitätsdaten der Apps in der Auswahl, beschränkt auf den Zeitraum aus dem Filter
  function stabSelection() {
    const from = state.f.from || "", to = state.f.to || "", inP = r => r[0] >= from && (!to || r[0] <= to);
    const sel = (DATA.stability || []).filter(x => x.platform === "apple" && inScope(x));
    return { sel, cr: sel.flatMap(x => x.crashes).filter(inP), se: sel.flatMap(x => x.sessions).filter(inP) };
  }
  function portfolioChart(k, rs, W) {
    const apps = DATA.apps.filter(a => a.platform === k && inScope(a)), { sel } = stabSelection();
    const pf = portfolio(apps, rs, sel, state.f.from, state.f.to), placed = pf.filter(o => o.zone), missing = pf.filter(o => !o.zone);
    const oneCustomer = new Set(apps.map(a => a.customerId)).size === 1, name = o => oneCustomer ? o.appName : o.customerName + " · " + o.appName;
    const miss = missing.length ? h("div", { class: "note" }, tx("Nicht eingezeichnet (keine Rezensionen oder keine Sitzungen im Zeitraum): ", "Not shown (no reviews or no sessions in the period): ") + missing.map(name).join(", ")) : null;
    if (!placed.length) return [h("div", { class: "muted" }, tx("Für diese Auswahl gibt es keine App mit Rezensionen und Stabilitätsdaten.", "No app in this selection has both reviews and stability data.")), miss];
    const H = 300, L = 40, R = 14, T = 22, B = 34, xMax = niceMax(Math.max(ZONE.rate * 2, ...placed.map(o => o.rate)));
    const yMin = Math.min(3, Math.floor(Math.min(...placed.map(o => o.avg)))), x = v => L + (W - L - R) * Math.min(v, xMax) / xMax, y = v => T + (H - T - B) * (1 - (v - yMin) / (5 - yMin));
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": tx("Alle Apps: Sterne gegen Abstürze", "All apps: stars against crashes") });
    svg.append(s("rect", { x: L, y: y(5), width: x(ZONE.rate) - L, height: y(ZONE.stars) - y(5), fill: "color-mix(in srgb,var(--good) 9%,transparent)" }),
      s("rect", { x: x(ZONE.rate), y: y(ZONE.stars), width: x(xMax) - x(ZONE.rate), height: y(yMin) - y(ZONE.stars), fill: "color-mix(in srgb,var(--bad) 9%,transparent)" }));
    for (let v = yMin; v <= 5; v++) svg.append(s("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "var(--line)", "stroke-dasharray": "3 4" }), s("text", { x: L - 6, y: y(v) + 3, "text-anchor": "end" }, v + " ★"));
    svg.append(s("line", { x1: L, x2: W - R, y1: y(ZONE.stars), y2: y(ZONE.stars), stroke: "var(--line2)" }), s("line", { x1: x(ZONE.rate), x2: x(ZONE.rate), y1: y(5), y2: y(yMin), stroke: "var(--line2)" }));
    const cap = (cx, cy, anchor, text, col) => svg.append(s("text", { x: cx, y: cy, "text-anchor": anchor, style: "fill:" + col + ";font-weight:600" }, text));
    cap(L + 6, T - 8, "start", tx("läuft gut", "doing well"), "var(--good-t)"); cap(W - R, T - 8, "end", tx("gute Sterne, viele Abstürze", "good stars, many crashes"), "var(--muted)");
    cap(L + 6, y(yMin) - 6, "start", tx("wenig Abstürze, schwache Sterne", "few crashes, weak stars"), "var(--muted)"); cap(W - R - 4, y(yMin) - 6, "end", tx("kümmern", "needs attention"), "var(--bad-t)");
    [0, .5, 1].forEach(q => svg.append(s("text", { x: x(xMax * q), y: H - 17, "text-anchor": q === 1 ? "end" : q ? "middle" : "start" }, fmt(xMax * q, 1))));
    svg.append(s("text", { x: W - R, y: H - 2, "text-anchor": "end" }, tx("Abstürze je 1000 Sitzungen →", "Crashes per 1,000 sessions →")));
    const maxS = Math.max(1, ...placed.map(o => o.sessions)), rad = o => 5 + (W < 450 ? 12 : 17) * Math.sqrt(o.sessions / maxS);
    placed.slice().sort((a, b) => b.sessions - a.sessions).forEach(o => {
      const c = COL[o.zone];
      svg.append(s("circle", { cx: x(o.rate), cy: y(o.avg), r: rad(o), fill: c, "fill-opacity": o.small ? .12 : .45, stroke: c, "stroke-width": 1.5, "stroke-dasharray": o.small ? "3 2" : "",
        "data-tip": name(o) + "\n" + fmt(o.avg) + " ★ " + tx("aus ", "from ") + fmtInt(o.rated) + tx(" Rezensionen · ", " reviews · ") + fmt(o.rate) + tx(" Abstürze je 1000 Sitzungen · ", " crashes per 1,000 sessions · ") + fmtInt(o.sessions) + tx(" Sitzungen", " sessions") + (o.small ? tx(" · ⚠ kleine Stichprobe", " · ⚠ small sample") : "") }));
    });
    const used = [];
    placed.filter(o => o.zone === "bad").sort((a, b) => a.avg - b.avg).forEach(o => {
      const cx = x(o.rate), left = cx > W * .6; let ty = y(o.avg) + 3;
      while (used.some(u => Math.abs(u - ty) < 12)) ty += 12;
      used.push(ty);
      svg.append(s("text", { x: left ? cx - rad(o) - 4 : cx + rad(o) + 4, y: ty, "text-anchor": left ? "end" : "start", style: "fill:var(--fg)" }, name(o)));
    });
    return [svg, chartLegend([[COL.good, tx("läuft gut", "doing well"), 1], [COL.mid, tx("beobachten", "watch"), 1], [COL.bad, tx("kümmern", "needs attention"), 1]]),
      h("div", { class: "note" }, tx("Felder: ab " + ZONE.stars + " ★ und unter " + ZONE.rate + " Abstürzen je 1000 Sitzungen = läuft gut. Blasse, gestrichelte Kreise: kleine Stichprobe (unter " + ZONE.minReviews + " Rezensionen oder " + ZONE.minSessions + " Sitzungen).",
        "Zones: from " + ZONE.stars + " ★ and below " + ZONE.rate + " crashes per 1,000 sessions = doing well. Pale dashed circles: small sample (under " + ZONE.minReviews + " reviews or " + ZONE.minSessions + " sessions).")), miss];
  }
  function weeklyStab(rs, W, withStars, k) {
    const { cr, se } = stabSelection(), wk = stabilityBy(cr, se, r => weekStart(r[0])).sort((a, b) => a.key < b.key ? -1 : 1);
    if (wk.length < 2) return h("div", { class: "muted" }, tx("Für diese Auswahl und diesen Zeitraum liegen weniger als zwei Wochen Stabilitätsdaten vor (Abruf: ./ratings.sh stability).", "Less than two weeks of stability data for this selection and period (fetch: ./ratings.sh stability)."));
    const labels = wk.map(o => o.key.slice(8, 10) + "." + o.key.slice(5, 7)), wl = tx("Woche ab ", "Week from ");
    const lane = { k, kind: "week", buckets: wk.map(o => o.key) };
    if (!withStars) return [columnsSvg({ W, label: tx("Sitzungen pro Woche", "Sessions per week"), labels, lane, bars: [{ name: tx("Sitzungen", "sessions"), color: "var(--accent)", values: wk.map(o => o.sessions) }] }),
      h("div", { class: "note" }, tx("Beschriftung = Wochenbeginn (Montag).", "Label = start of week (Monday)."))];
    const byW = groupBy(rs.filter(r => r.createdAt), r => weekStart(r.createdAt.slice(0, 10)));
    return [columnsSvg({ W, label: tx("Abstürze und Bewertung", "Crashes and rating"), labels, lane, leftFmt: v => fmt(v, 1),
      bars: [{ name: tx("Abstürze je 1000 Sitzungen", "crashes per 1,000 sessions"), color: COL.bad, values: wk.map(o => o.rate || 0), fmt: v => fmt(v) }],
      lines: [{ name: tx("Ø Sterne", "avg stars"), color: "var(--accent)", values: wk.map(o => { const l = byW.get(o.key); return l ? stats(l).avg : null; }), right: true, fmt: v => fmt(v) + " ★" }], rightMax: 5, rightFmt: v => fmt(v, 0) + " ★" }),
      chartLegend([[COL.bad, tx("Abstürze je 1000 Sitzungen", "Crashes per 1,000 sessions")], ["var(--accent)", tx("Ø Sterne der Rezensionen dieser Woche", "avg stars of that week's reviews"), 1]]),
      h("div", { class: "note" }, wl + tx("= Beschriftung. Zeitliche Übereinstimmung ist kein Beleg für eine Ursache.", "= label. Coincidence in time is no proof of cause."))];
  }
  function rolloutChart(W) {
    const { sel, se } = stabSelection();
    if (sel.length !== 1) return h("div", { class: "chna" }, h("b", {}, tx("Bitte im Filter eine einzelne App wählen", "Please select a single app in the filter")), tx("Versionsnummern verschiedener Apps lassen sich nicht zusammenzählen.", "Version numbers of different apps cannot be added up."));
    const weeks = [...groupBy(se, r => weekStart(r[0])).entries()].sort((a, b) => a[0] < b[0] ? -1 : 1);
    if (weeks.length < 2) return h("div", { class: "muted" }, tx("Weniger als zwei Wochen Sitzungsdaten.", "Less than two weeks of session data."));
    const last = weeks[weeks.length - 1][1], tot = new Map();
    for (const r of last) tot.set(r[1], (tot.get(r[1]) || 0) + r[4]);
    const top = [...tot.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(e => e[0]), other = tx("ältere/andere", "older/other");
    const keys = top.concat([other]), cols = ["var(--accent)", "color-mix(in srgb,var(--accent) 55%,var(--solid))", "color-mix(in srgb,var(--accent) 25%,var(--solid))", "var(--line2)"];
    const share = weeks.map(([, rows]) => { const sum = rows.reduce((a, r) => a + r[4], 0) || 1, m = new Map(); for (const r of rows) { const k = top.includes(r[1]) ? r[1] : other; m.set(k, (m.get(k) || 0) + r[4]); } return keys.map(k => (m.get(k) || 0) / sum); });
    const H = 220, L = 40, T = 10, B = 24, n = weeks.length, step = (W - L - 10) / (n - 1), yy = v => T + (H - T - B) * (1 - v), xx = i => L + i * step;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": tx("Anteil der Sitzungen je App-Version", "Share of sessions per app version") });
    [0, .5, 1].forEach(q => svg.append(s("text", { x: L - 6, y: yy(q) + 3, "text-anchor": "end" }, (q * 100) + " %")));
    keys.slice().reverse().forEach((k, jr) => {
      const j = keys.length - 1 - jr, top_ = share.map((sh, i) => [xx(i), yy(sh.slice(j).reduce((a, b) => a + b, 0))]), bot = share.map((sh, i) => [xx(i), yy(sh.slice(j + 1).reduce((a, b) => a + b, 0))]).reverse();
      svg.append(s("polygon", { points: top_.concat(bot).map(p => p.join(",")).join(" "), fill: cols[j], stroke: "var(--surface)", "stroke-width": 1, "data-tip": (k === other ? k : tx("Version ", "Version ") + k) + ": " + fmt(100 * share[n - 1][j], 0) + tx(" % in der letzten Woche", " % in the last week") }));
    });
    const every = Math.max(1, Math.ceil(n / Math.floor((W - L) / 46)));
    weeks.forEach(([w], i) => { if (i % every === 0) svg.append(s("text", { x: xx(i), y: H - 7, "text-anchor": "middle" }, w.slice(8, 10) + "." + w.slice(5, 7))); });
    return [svg, chartLegend(keys.map((k, j) => [cols[j], k === other ? k : tx("Version ", "Version ") + k]))];
  }
  // ---- Store-Kennzahlen (Apple Analytics: Downloads, Installationen/Löschungen, Store-Aufrufe), Zeilen-Arrays:
  // downloads [Datum, Typ, Quelle, Land, Gerät, Anzahl], installs [Datum, Ereignis, Land, Gerät, Anzahl], engagement [Datum, Ereignis, Quelle, Anzahl]
  const STORE_NA = tx("Für Google-Apps werden Downloads und Store-Aufrufe noch nicht abgerufen.", "Downloads and store views are not yet fetched for Google apps.");
  const DL_TYPES = { "First-time download": tx("Erstinstallation", "First-time download"), "Redownload": tx("erneut geladen", "Redownload"), "Restore": tx("Wiederherstellung", "Restore") };
  const SOURCES = { "App Store search": tx("App-Store-Suche", "App Store search"), "App Store browse": tx("Stöbern im Store", "App Store browse"), "App referrer": tx("Verweis aus einer App", "App referrer"),
    "Web referrer": tx("Verweis von einer Webseite", "Web referrer"), "Unavailable": tx("unbekannt", "unknown") };
  const isUpdate = t => t === "Auto-update" || t === "Manual update";
  function storeSel() {
    const from = state.f.from || "", to = state.f.to || "", inP = r => r[0] >= from && (!to || r[0] <= to);
    const sel = (DATA.storeMetrics || []).filter(x => x.platform === "apple" && inScope(x));
    return { sel, dl: sel.flatMap(x => x.downloads).filter(inP), ins: sel.flatMap(x => x.installs).filter(inP), eng: sel.flatMap(x => x.engagement).filter(inP) };
  }
  const storeEmpty = () => h("div", { class: "muted" }, tx("Für diese Auswahl liegen keine Store-Kennzahlen vor (Abruf: ./ratings.sh store).", "No store figures for this selection (fetch: ./ratings.sh store)."));
  const sumBy = (rows, keyFn, valIdx) => { const m = new Map(); for (const r of rows) { const k = keyFn(r); m.set(k, (m.get(k) || 0) + r[valIdx]); } return m; };
  const weekLabel = w => w.slice(8, 10) + "." + w.slice(5, 7);
  // Hinweis auf angeschnittene Randwochen: erster und letzter Datentag der gezeigten Zeilen
  const edgeNote = rows => { const d = rows.map(r => r[0]).sort(); return tx(" Daten vom " + fmtDay(d[0]) + " bis " + fmtDay(d[d.length - 1]) + "; erste und letzte Woche können unvollständig sein.", " Data from " + fmtDay(d[0]) + " to " + fmtDay(d[d.length - 1]) + "; the first and last week may be incomplete."); };
  let regionNames = null; try { regionNames = new Intl.DisplayNames([locale()], { type: "region" }); } catch (e) { /* ältere Browser: Ländercode anzeigen */ }
  const country = code => { try { return (regionNames && code && regionNames.of(code)) || code || tx("(unbekannt)", "(unknown)"); } catch (e) { return code; } };
  function downloadsChart(W, k) {
    const { dl } = storeSel(); if (!dl.length) return storeEmpty();
    const weeks = [...new Set(dl.map(r => weekStart(r[0])))].sort(), types = Object.keys(DL_TYPES), cols = ["var(--accent)", "color-mix(in srgb,var(--accent) 50%,var(--solid))", "var(--line2)"];
    const by = sumBy(dl, r => weekStart(r[0]) + "|" + (isUpdate(r[1]) ? "update" : r[1]), 5), get = (w, t) => by.get(w + "|" + t) || 0;
    const upd = weeks.map(w => get(w, "update"));
    return [columnsSvg({ W, label: tx("Downloads pro Woche", "Downloads per week"), labels: weeks.map(weekLabel), lane: { k, kind: "week", buckets: weeks },
      bars: types.map((t, j) => ({ name: DL_TYPES[t], color: cols[j], values: weeks.map(w => get(w, t)) })),
      lines: [{ name: tx("Updates", "updates"), color: COL.mid, values: upd, right: true, fmt: fmtInt }], rightMax: niceMax(Math.max(1, ...upd)), rightFmt: fmtInt }),
      chartLegend(types.map((t, j) => [cols[j], DL_TYPES[t]]).concat([[COL.mid, tx("Updates (rechte Skala)", "Updates (right scale)"), 1]])),
      h("div", { class: "note" }, tx("Beschriftung = Wochenbeginn (Montag). Wiederherstellung = App kommt beim Einrichten eines Geräts aus einem Backup zurück.", "Label = start of week (Monday). Restore = app returns from a backup when a device is set up.") + edgeNote(dl))];
  }
  function installsChart(W) {
    const { ins } = storeSel(); if (!ins.length) return storeEmpty();
    const weeks = [...new Set(ins.map(r => weekStart(r[0])))].sort(), by = sumBy(ins, r => weekStart(r[0]) + "|" + r[1], 4);
    const up = weeks.map(w => Math.max(0, by.get(w + "|Install") || 0)), dn = weeks.map(w => Math.max(0, by.get(w + "|Delete") || 0));
    const H = 240, L = 44, T = 12, B = 24, n = weeks.length, step = (W - L - 10) / n, bw = Math.max(3, Math.min(28, step * .55));
    const max = niceMax(Math.max(1, ...up, ...dn)), mid = T + (H - T - B) / 2, sc = (H - T - B) / 2 / max;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": tx("Installationen und Löschungen pro Woche", "Installs and deletions per week") });
    svg.append(s("line", { x1: L, x2: W - 10, y1: mid, y2: mid, stroke: "var(--line2)" }), s("text", { x: L - 6, y: mid - max * sc + 3, "text-anchor": "end" }, "+" + fmtInt(max)), s("text", { x: L - 6, y: mid + 3, "text-anchor": "end" }, "0"), s("text", { x: L - 6, y: mid + max * sc + 3, "text-anchor": "end" }, "−" + fmtInt(max)));
    const every = Math.max(1, Math.ceil(n / Math.floor((W - L) / 42))), wl = tx("Woche ab ", "Week from ");
    weeks.forEach((w, i) => { const x = L + i * step + (step - bw) / 2;
      svg.append(s("rect", { x, y: mid - up[i] * sc, width: bw, height: up[i] * sc, fill: COL.good, rx: 2, "data-tip": wl + weekLabel(w) + ": " + fmtInt(up[i]) + tx(" Installationen", " installs") }),
        s("rect", { x, y: mid, width: bw, height: dn[i] * sc, fill: COL.bad, rx: 2, "data-tip": wl + weekLabel(w) + ": " + fmtInt(dn[i]) + tx(" Löschungen", " deletions") }));
      if (i % every === 0) svg.append(s("text", { x: x + bw / 2, y: H - 7, "text-anchor": "middle" }, weekLabel(w))); });
    const ti = up.reduce((a, b) => a + b, 0), td = dn.reduce((a, b) => a + b, 0);
    const laneNote = addLane(svg, { W, H, L, R: 10, step, bw, top: T, bottom: H - B, buckets: weeks, kind: "week" }, "apple");
    return [svg, laneNote, chartLegend([[COL.good, tx("Installationen", "Installs")], [COL.bad, tx("Löschungen", "Deletions")]]),
      h("div", { class: "note" }, tx("Im Zeitraum: " + fmtInt(ti) + " Installationen, " + fmtInt(td) + " Löschungen. Installationen zählen auch erneute Downloads und Wiederherstellungen.", "In the period: " + fmtInt(ti) + " installs, " + fmtInt(td) + " deletions. Installs include redownloads and restores.") + edgeNote(ins))];
  }
  function countryChart() {
    const { dl } = storeSel(), first = dl.filter(r => r[1] === "First-time download"); if (!first.length) return storeEmpty();
    const top = [...sumBy(first, r => r[3], 5).entries()].filter(e => e[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, 12);
    return [barList(top.map(([c, v]) => ({ label: country(c), value: v, text: fmtInt(v) }))), h("div", { class: "note" }, tx("Erstinstallationen im Zeitraum, Top 12.", "First-time downloads in the period, top 12."))];
  }
  function sourceChart() {
    const { dl } = storeSel(), first = dl.filter(r => r[1] === "First-time download"); if (!first.length) return storeEmpty();
    const m = [...sumBy(first, r => r[2], 5).entries()].filter(e => e[1] > 0).sort((a, b) => b[1] - a[1]), tot = m.reduce((a, e) => a + e[1], 0) || 1;
    return [barList(m.map(([k, v]) => ({ label: SOURCES[k] || k, value: v, text: fmt(100 * v / tot, 0) + " % · " + fmtInt(v) }))), h("div", { class: "note" }, tx("Anteil der Erstinstallationen im Zeitraum.", "Share of first-time downloads in the period."))];
  }
  function funnelChart() {
    const { dl, eng } = storeSel(); if (!dl.length && !eng.length) return storeEmpty();
    const ev = sumBy(eng, r => r[1], 3), first = dl.filter(r => r[1] === "First-time download").reduce((a, r) => a + r[5], 0);
    const steps = [[tx("Im Store gesehen (Impressionen)", "Seen in the store (impressions)"), ev.get("Impression") || 0], [tx("Produktseite aufgerufen", "Product page viewed"), ev.get("Page view") || 0], [tx("Erstmals geladen", "Downloaded for the first time"), first]];
    return [barList(steps.map(([l, v], i) => ({ label: l, value: Math.max(0, v), text: fmtInt(v) + (i && steps[i - 1][1] > 0 ? " · " + fmt(100 * v / steps[i - 1][1], 1) + " %" : "") }))),
      h("div", { class: "note" }, tx("Prozent = Anteil der vorherigen Stufe. Downloads kommen auch ohne Produktseite zustande (z. B. direkt aus der Suche), daher ist das ein grober Anhaltspunkt.", "Percent = share of the previous step. Downloads also happen without the product page (e.g. straight from search), so this is a rough guide."))];
  }
  // ---- Versionsleiste: Veröffentlichungen unter den zeitlichen Diagrammen ----
  // Exakt: releasedAt aus versions.json (iTunes Lookup, nur die jeweils aktuelle Version). Näherung: erster Tag einer Version
  // in den Sitzungsdaten, wenn das nicht der erste Datentag der App ist und die Version in ihrer ersten Woche mindestens
  // 5 % der Sitzungen erreicht (sonst wären es alte Versionen, die nur zufällig später auftauchen).
  const appKeyOf = x => x.customerId + "/" + x.appId, DAYMS = 864e5;
  const addDays = (d, n) => new Date(Date.parse(d + "T00:00:00Z") + n * DAYMS).toISOString().slice(0, 10);
  function releaseList(k) {
    const apps = new Map(DATA.apps.filter(a => a.platform === k && inScope(a)).map(a => [appKeyOf(a), a])), out = new Map();
    for (const v of DATA.versions || []) {
      const a = apps.get(appKeyOf(v));
      if (a && v.platform === k && v.releasedAt && !v.build) out.set(appKeyOf(v) + "|" + v.version, { app: a, version: v.version, date: v.releasedAt.slice(0, 10), exact: true });
    }
    for (const e of DATA.stability || []) {
      const a = apps.get(appKeyOf(e)); if (!a || e.platform !== k || !e.sessions.length) continue;
      const firstDay = e.sessions.reduce((m, r) => r[0] < m ? r[0] : m, "9999"), first = new Map();
      for (const r of e.sessions) if (!first.has(r[1]) || r[0] < first.get(r[1])) first.set(r[1], r[0]);
      for (const [ver, d] of first) {
        if (d <= firstDay || out.has(appKeyOf(e) + "|" + ver)) continue;
        const end = addDays(d, 7), win = e.sessions.filter(r => r[0] >= d && r[0] < end), all = win.reduce((s, r) => s + r[4], 0), mine = win.filter(r => r[1] === ver).reduce((s, r) => s + r[4], 0);
        if (all > 0 && mine / all >= .05) out.set(appKeyOf(e) + "|" + ver, { app: a, version: ver, date: d, exact: false });
      }
    }
    return [...out.values()].sort((x, y) => x.date < y.date ? -1 : x.date > y.date ? 1 : 0);
  }
  // Tooltip je Veröffentlichung: Updates 7 Tage danach, Ø Sterne 30 Tage vorher/nachher, Absturzrate 7 Tage danach
  function releaseTip(r, n) {
    const key = appKeyOf(r.app), d = r.date, d7 = addDays(d, 7), b30 = addDays(d, -30), a30 = addDays(d, 30), parts = [];
    const sm = (DATA.storeMetrics || []).find(x => appKeyOf(x) === key);
    if (sm) parts.push(tx("Updates in den 7 Tagen danach: ", "Updates in the 7 days after: ") + fmtInt(sm.downloads.filter(x => isUpdate(x[1]) && x[0] >= d && x[0] < d7).reduce((s, x) => s + x[5], 0)));
    const rv = reviews.filter(x => appKeyOf(x) === key && x.platform === r.app.platform && x.createdAt), before = stats(rv.filter(x => x.createdAt.slice(0, 10) >= b30 && x.createdAt.slice(0, 10) < d)), after = stats(rv.filter(x => x.createdAt.slice(0, 10) >= d && x.createdAt.slice(0, 10) < a30));
    parts.push(before.rated >= 3 && after.rated >= 3 ? tx("Ø Sterne 30 Tage vorher ", "avg stars 30 days before ") + fmt(before.avg) + " → " + tx("nachher ", "after ") + fmt(after.avg) : tx("zu wenige Rezensionen für einen Sterne-Vergleich", "too few reviews for a star comparison"));
    const st = (DATA.stability || []).find(x => appKeyOf(x) === key);
    if (st) { const o = stabilityBy(st.crashes.filter(x => x[0] >= d && x[0] < d7), st.sessions.filter(x => x[0] >= d && x[0] < d7), () => "x")[0]; if (o && o.rate !== null) parts.push(tx("Abstürze je 1000 Sitzungen in den 7 Tagen danach: ", "crashes per 1,000 sessions in the 7 days after: ") + fmt(o.rate)); }
    return n + " · " + tx("Version ", "Version ") + r.version + " · " + r.app.customerName + " · " + r.app.appName + "\n" +
      (r.exact ? tx("veröffentlicht am ", "released on ") + fmtDay(d) + tx(" (App Store, exakt)", " (App Store, exact)") : tx("erstmals in Nutzung am ", "first in use on ") + fmtDay(d) + tx(" (Näherung aus Sitzungsdaten)", " (approximation from session data)")) + " · " + parts.join(" · ");
  }
  // Zeichnet die Leiste in ein fertiges Diagramm. geo: { W, H, L, R, step, top, bottom, buckets (Startdaten), kind: "week"|"month" }.
  // Liefert eine Notiz mit der Zuordnung Buchstabe → App, wenn mehrere Apps Zeilen bekommen, sonst null.
  function addLane(svg, geo, k) {
    const { W, H, L, R, step, buckets, kind } = geo;
    const len = i => kind === "week" ? 7 : new Date(Date.UTC(+buckets[i].slice(0, 4), +buckets[i].slice(5, 7), 0)).getUTCDate();
    const xOf = d => { let i = -1; for (let j = 0; j < buckets.length; j++) if (buckets[j] <= d) i = j; if (i < 0) return null;
      const f = (Date.parse(d + "T00:00:00Z") - Date.parse(buckets[i] + "T00:00:00Z")) / DAYMS / len(i); return f >= 1 ? null : L + (i + f) * step; };
    const rels = releaseList(k).filter(r => xOf(r.date) !== null), byApp = [...new Set(rels.map(r => appKeyOf(r.app)))];
    const tooMany = byApp.length > 6, rows = tooMany ? 1 : Math.max(1, byApp.length), rowH = 24;
    // Updates je Woche, nur in Wochendiagrammen: Säulen mit derselben Breite und Position wie die Säulen darüber (geo.bw).
    // days zählt die Tage mit Daten je Woche; angeschnittene Randwochen werden blass gezeichnet.
    const bucketOf = d => { let i = -1; for (let j = 0; j < buckets.length; j++) if (buckets[j] <= d) i = j; return i >= 0 && xOf(d) !== null ? i : -1; };
    const sm = k === "apple" && kind === "week" ? (DATA.storeMetrics || []).filter(x => inScope(x)) : [], upd = new Map(), days = new Map();
    for (const x of sm) for (const r of x.downloads) { const i = bucketOf(r[0]); if (i < 0) continue;
      (days.get(i) || days.set(i, new Set()).get(i)).add(r[0]); if (isUpdate(r[1])) upd.set(i, (upd.get(i) || 0) + r[5]); }
    const uH = upd.size ? 34 : 0, laneH = rows * rowH + (uH ? uH + 10 : 0) + 8, top = H + 2;
    svg.setAttribute("viewBox", `0 0 ${W} ${H + laneH + 4}`);
    svg.append(s("rect", { x: L, y: top, width: W - L - R, height: laneH, rx: 6, fill: "color-mix(in srgb,var(--fg) 5%,transparent)" }));
    if (!rels.length) svg.append(s("text", { x: L + 8, y: top + 16 }, tx("Keine Veröffentlichung im gezeigten Zeitraum", "No release in the period shown")));
    else if (tooMany) svg.append(s("text", { x: L + 8, y: top + 16 }, tx("Veröffentlichungen: höchstens sechs Apps im Filter wählen", "Releases: select at most six apps in the filter")));
    else {
      rels.forEach((r, n) => { const x = xOf(r.date), y = top + 4 + rowH / 2 + byApp.indexOf(appKeyOf(r.app)) * rowH;
        svg.insertBefore(s("line", { x1: x, x2: x, y1: geo.top, y2: geo.bottom, stroke: "var(--fg)", "stroke-dasharray": "2 4", opacity: .3 }), svg.firstChild);
        const g = s("g", { "data-tip": releaseTip(r, n + 1), style: "cursor:pointer" });
        g.append(s("circle", { cx: x, cy: y, r: 8.5, fill: r.exact ? "var(--fg)" : "var(--solid)", stroke: "var(--fg)", "stroke-width": 1.8 }),
          s("text", { x, y: y + 3.2, "text-anchor": "middle", style: "font-size:9px;font-weight:700;fill:" + (r.exact ? "var(--solid)" : "var(--fg)") }, String(n + 1)));
        svg.append(g); });
      if (byApp.length > 1) byApp.forEach((a, j) => svg.append(s("text", { x: L - 6, y: top + 4 + rowH / 2 + j * rowH + 3, "text-anchor": "end", style: "font-weight:600" }, String.fromCharCode(65 + j))));
    }
    if (uH) {
      const uTop = top + rows * rowH + 10, uMax = Math.max(1, ...upd.values()), bw = geo.bw || step * .6;
      svg.append(s("text", { x: L - 6, y: uTop + uH - 2, "text-anchor": "end" }, tx("Upd.", "Upd.")));
      for (const [i, v] of upd) { const hh = uH * Math.max(0, v) / uMax, n = days.get(i).size, part = n < 7;
        svg.append(s("rect", { x: L + i * step + (step - bw) / 2, y: uTop + uH - hh, width: bw, height: hh, rx: Math.min(3, bw / 2), opacity: part ? .45 : 1, fill: "color-mix(in srgb,var(--accent) 45%,var(--solid))",
          "data-tip": tx("Woche ab ", "Week from ") + fmtDay(buckets[i]) + "\n" + fmtInt(v) + tx(" Updates", " updates") + (part ? tx(" (nur " + n + " von 7 Tagen mit Daten)", " (only " + n + " of 7 days with data)") : "") })); }
    }
    const notes = [];
    if (rels.length && !tooMany && byApp.length > 1) notes.push(byApp.map((a, j) => String.fromCharCode(65 + j) + " = " + rels.find(r => appKeyOf(r.app) === a).app.appName).join(" · "));
    notes.push(tx("Leiste: ● Veröffentlichung exakt, ○ Näherung aus Sitzungsdaten" + (uH ? ", Säulen = Updates je Woche (blass = Woche nur teilweise mit Daten)" : "") + ". Maus über einen Kreis zeigt Details.", "Strip: ● release exact, ○ approximation from session data" + (uH ? ", bars = updates per week (pale = week only partly covered)" : "") + ". Hover a circle for details."));
    return h("div", { class: "note" }, notes.join(" "));
  }
  // Wochenübersicht: Sitzungen, Abstürze und Downloads (ohne Updates) als drei Säulenreihen mit eigener Skala und
  // gemeinsamer Wochenachse; eine gemeinsame Skala ginge nicht (Sitzungen sind um Größenordnungen höher als Abstürze).
  function weeklyOverview(W, k) {
    const { cr, se } = stabSelection(), { dl } = storeSel();
    const weeks = [...new Set(cr.concat(se).map(r => weekStart(r[0])).concat(dl.map(r => weekStart(r[0]))))].sort();
    if (weeks.length < 2) return h("div", { class: "muted" }, tx("Für diese Auswahl liegen weniger als zwei Wochen Daten vor (Abruf: ./ratings.sh stability und store).", "Less than two weeks of data for this selection (fetch: ./ratings.sh stability and store)."));
    const sum = (rows, vi, keep) => { const v = new Map(), d = new Map(); for (const r of rows) { if (keep && !keep(r)) continue; const w = weekStart(r[0]); v.set(w, (v.get(w) || 0) + r[vi]); (d.get(w) || d.set(w, new Set()).get(w)).add(r[0]); } return { v, d }; };
    const S1 = sum(se, 4), S2 = sum(cr, 4), S3 = sum(dl, 5, r => !isUpdate(r[1]));
    // Tage ohne Absturz haben keine Absturzzeile: Abdeckung der Abstürze = Tage mit Sitzungsdaten
    S2.d = S1.d; for (const w of S2.v.keys()) if (!S2.d.has(w)) S2.d.set(w, new Set());
    for (const w of S1.v.keys()) if (!S2.v.has(w)) S2.v.set(w, 0);
    const series = [[tx("Sitzungen", "Sessions"), S1, "var(--accent)"], [tx("Abstürze", "Crashes"), S2, COL.bad], [tx("Downloads (ohne Updates)", "Downloads (excl. updates)"), S3, "color-mix(in srgb,var(--accent) 50%,var(--solid))"]];
    const L = 44, R = 10, T = 8, B = 24, rowH = 78, gap = 22, n = weeks.length, step = (W - L - R) / n, bw = Math.max(3, Math.min(28, step * .62)), H = T + series.length * (rowH + gap) - gap + B;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": tx("Wochenübersicht: Sitzungen, Abstürze, Downloads", "Weekly overview: sessions, crashes, downloads") });
    const tipOf = w => { const s1 = S1.v.get(w), s2 = S2.v.get(w), s3 = S3.v.get(w), rate = s1 > 0 && s2 !== undefined ? 1000 * s2 / s1 : null;
      const part = [S1, S2, S3].some(x => x.d.has(w) && x.d.get(w).size < 7);
      return tx("Woche ab ", "Week from ") + fmtDay(w) + "\n" + [s1 === undefined ? null : fmtInt(s1) + tx(" Sitzungen", " sessions"), s2 === undefined ? null : fmtInt(s2) + tx(" Abstürze", " crashes") + (rate === null ? "" : " (" + fmt(rate) + tx(" je 1000 Sitzungen)", " per 1,000 sessions)")),
        s3 === undefined ? null : fmtInt(s3) + tx(" Downloads", " downloads")].filter(Boolean).join(" · ") + (part ? tx(" · Woche nur teilweise mit Daten", " · week only partly covered") : ""); };
    series.forEach(([name, S, col], j) => {
      const top = T + j * (rowH + gap), max = niceMax(Math.max(1, ...S.v.values())), y = v => top + rowH * (1 - Math.max(0, v) / max);
      svg.append(s("text", { x: L, y: top + 9, style: "font-weight:600;fill:var(--fg)" }, name), s("text", { x: L - 6, y: top + 12, "text-anchor": "end" }, fmtInt(max)),
        s("text", { x: L - 6, y: top + rowH + 3, "text-anchor": "end" }, "0"), s("line", { x1: L, x2: W - R, y1: top + rowH, y2: top + rowH, stroke: "var(--line)" }));
      weeks.forEach((w, i) => { if (!S.v.has(w)) return; const v = S.v.get(w), hh = top + rowH - y(v);
        svg.append(s("rect", { x: L + i * step + (step - bw) / 2, y: y(v), width: bw, height: hh, rx: Math.min(3, bw / 2), fill: col, opacity: S.d.get(w).size < 7 ? .45 : 1, "data-tip": tipOf(w) })); });
    });
    const every = Math.max(1, Math.ceil(n / Math.floor((W - L - R) / 42)));
    weeks.forEach((w, i) => { if (i % every === 0) svg.append(s("text", { x: L + i * step + step / 2, y: H - 7, "text-anchor": "middle" }, weekLabel(w))); });
    const note = addLane(svg, { W, H, L, R, step, bw, top: T, bottom: T + series.length * (rowH + gap) - gap, buckets: weeks, kind: "week" }, k);
    return [svg, note, h("div", { class: "note" }, tx("Jede Reihe hat ihre eigene Skala (links). Blasse Säulen: Woche nur teilweise mit Daten. Beschriftung = Wochenbeginn (Montag).", "Each row has its own scale (left). Pale bars: week only partly covered. Label = start of week (Monday)."))];
  }
  const CHARTS = [
    { g: tx("Überblick", "Overview"), id: "portfolio", title: tx("Alle Apps auf einen Blick", "All apps at a glance"), sub: tx("Wo steht jede App im gewählten Zeitraum? Jeder Kreis eine App: Ø Sterne der Rezensionen gegen Abstürze je 1000 Sitzungen, Kreisgröße = Sitzungen", "Where does each app stand in the selected period? One circle per app: avg stars of the reviews against crashes per 1,000 sessions, circle size = sessions"),
      why: tx("Ein Bild für das ganze Portfolio. Oben links stehen die Apps, um die man sich nicht kümmern muss, unten rechts die Sorgenkinder, sie sind direkt beschriftet. Maus über einen Kreis (oder antippen) zeigt Kunde, App und Werte. Das ist die Lage über den gewählten Zeitraum, nicht die Warnung von heute: Die Ampel im Überblick schaut auf die letzten 7 und 30 Tage und kann dieselbe App anders einstufen.", "One picture for the whole portfolio. Top left: apps that need no attention; bottom right: problem apps, labelled directly. Hover (or tap) a circle for customer, app and values. This is the position over the selected period, not today’s warning: the traffic light on the overview looks at the last 7 and 30 days and can rate the same app differently."),
      na: k => k === "google" ? STAB_NA : null, draw: (k, rs, W) => portfolioChart(k, rs, W) },
    { g: tx("Bewertungen", "Ratings"), id: "trend", title: tx("Entwicklung im Zeitverlauf", "Trend over time"), sub: tx("Rezensionen pro Monat, Linie = Ø Sterne", "Reviews per month, line = average stars"),
      why: tx("Zeigt, wie sich Menge und Stimmung der Rezensionen entwickeln.", "Shows how the number and mood of reviews develop."), draw: (k, rs, W) => trendChart(rs, W, k) },
    { g: tx("Bewertungen", "Ratings"), id: "stars", title: tx("Sterne-Verteilung", "Star distribution"), sub: tx("Anzahl je Sternebewertung", "Count per star rating"),
      why: tx("Zeigt, ob die Kritik von wenigen sehr Unzufriedenen kommt oder breit verteilt ist.", "Shows whether criticism comes from a few very unhappy users or is spread widely."),
      draw: (k, rs) => { const st = stats(rs); return st.rated ? barList([5, 4, 3, 2, 1].map(n => ({ label: n + " ★", value: st.dist[n], text: fmtInt(st.dist[n]), color: ratingColor(n) }))) : noData(); } },
    { g: tx("Bewertungen", "Ratings"), id: "apps", title: tx("Rezensionen pro App", "Reviews per app"), sub: tx("Top 15 nach Anzahl, Farbe = Ø Sterne", "Top 15 by count, colour = avg stars"),
      why: tx("Zeigt, welche Apps die meisten Rückmeldungen bekommen und wie gut sie abschneiden.", "Shows which apps get the most feedback and how well they do."), draw: (k, rs) => groupBars(rs, r => r.appName, 15) },
    { g: tx("Bewertungen", "Ratings"), id: "netscore", title: tx("Zufrieden minus unzufrieden pro Monat", "Happy minus unhappy per month"), sub: tx("Anteil 4–5 ★ minus Anteil 1–2 ★ in Prozentpunkten (−100 bis +100)", "Share of 4–5 ★ minus share of 1–2 ★ in percentage points (−100 to +100)"),
      why: tx("Eine Zahl wie beim NPS: über Null überwiegt Lob, unter Null Kritik. Weniger anfällig für Ausreißer als der Durchschnitt, weil fast nur Begeisterte und Verärgerte schreiben.", "One figure like the NPS: above zero praise prevails, below zero criticism. Less sensitive to outliers than the average, because mostly the delighted and the annoyed write."), draw: (k, rs, W) => netChart(rs, W, k) },
    { g: tx("Bewertungen", "Ratings"), id: "topics", title: tx("Themen der Rezensionen", "Review topics"), sub: tx("Treffer je Thema aus festen Wortlisten, Farbe = Ø Sterne", "Matches per topic from fixed word lists, colour = avg stars"),
      why: tx("Zeigt, worüber Nutzer schreiben, ohne jede Rezension zu lesen. Dieselben Zahlen stehen im Reiter Rezensionen unter „Themen und Wörter“; dort lassen sich per Klick auf ein Thema die Rezensionen dazu lesen. Die Wortlisten (deutsche und englische Begriffe, dazu Grundbegriffe in sechs weiteren Sprachen) stehen in config/themen.json und lassen sich anpassen.", "Shows what users write about without reading every review. The same figures appear on the Reviews tab under “Topics and words”, where clicking a topic lists its reviews. The word lists (German and English terms plus basic terms in six more languages) live in config/themen.json and can be edited."), draw: (k, rs) => topicBars(rs) },
    { g: tx("Bewertungen", "Ratings"), id: "replies", title: tx("Antworten auf Rezensionen", "Replies to reviews"), sub: tx("Pro Monat: mit und ohne Entwicklerantwort", "Per month: with and without developer reply"),
      why: tx("Zeigt dem Kunden, dass Rückmeldungen ernst genommen werden.", "Shows the customer that feedback is taken seriously."),
      draw: (k, rs, W) => { const months = [...groupBy(rs.filter(monthKey), monthKey).entries()].sort((a, b) => a[0] < b[0] ? -1 : 1); if (!months.length) return noData();
        const rv = tx(" Rezensionen", " reviews");
        return [columnsSvg({ W, label: tx("Antworten auf Rezensionen", "Replies to reviews"), labels: months.map(m => fmtMonthShort(m[0])), lane: { k, kind: "month", buckets: months.map(m => m[0] + "-01") }, bars: [{ name: tx("beantwortet", "replied"), color: COL.good, values: months.map(([, l]) => l.filter(hasReply).length), fmt: v => fmtInt(v) + rv }, { name: tx("ohne Antwort", "no reply"), color: "var(--line2)", values: months.map(([, l]) => l.filter(r => !hasReply(r)).length), fmt: v => fmtInt(v) + rv }] }),
          chartLegend([[COL.good, tx("beantwortet", "replied")], ["var(--line2)", tx("ohne Antwort", "no reply")]])]; } },
    { g: tx("Bewertungen", "Ratings"), id: "version", title: tx("Rezensionen nach App-Version", "Reviews by app version"), sub: tx("Top 12, Farbe = Ø Sterne", "Top 12, colour = avg stars"),
      why: tx("Zeigt, ob eine bestimmte Version auffällig schlecht bewertet wird.", "Shows whether a particular version is rated noticeably worse."), na: k => k === "apple" ? GOOGLE_ONLY : null, draw: (k, rs) => groupBars(rs, r => fieldValue(r, "appVersion"), 12) },
    { g: tx("Bewertungen", "Ratings"), id: "os", title: tx("Rezensionen nach Betriebssystem", "Reviews by operating system"), sub: tx("Top 12, Farbe = Ø Sterne", "Top 12, colour = avg stars"),
      why: tx("Zeigt, ob Probleme an einer Android-Version hängen.", "Shows whether problems are tied to an Android version."), na: k => k === "apple" ? GOOGLE_ONLY : null, draw: (k, rs) => groupBars(rs, r => fieldValue(r, "osLabel"), 12) },
    { g: tx("Bewertungen", "Ratings"), id: "device", title: tx("Rezensionen nach Gerät", "Reviews by device"), sub: tx("Top 12, Farbe = Ø Sterne", "Top 12, colour = avg stars"),
      why: tx("Zeigt, ob Probleme an bestimmten Geräten hängen.", "Shows whether problems are tied to certain devices."), na: k => k === "apple" ? GOOGLE_ONLY : null, draw: (k, rs) => groupBars(rs, r => fieldValue(r, "device"), 12) },
    { g: tx("Downloads und Store", "Downloads and store"), id: "downloads", title: tx("Downloads pro Woche", "Downloads per week"), sub: tx("Erstinstallationen, erneute Downloads und Wiederherstellungen; Linie = Updates", "First-time downloads, redownloads and restores; line = updates"),
      why: tx("Zeigt, ob die Apps wachsen und wie viele Nutzer Updates bekommen.", "Shows whether the apps grow and how many users receive updates."), na: k => k === "google" ? STORE_NA : null, draw: (k, rs, W) => downloadsChart(W, k) },
    { g: tx("Downloads und Store", "Downloads and store"), id: "installs", title: tx("Installationen und Löschungen", "Installs and deletions"), sub: tx("Pro Woche, oben installiert, unten gelöscht", "Per week, installs above, deletions below"),
      why: tx("Zeigt, ob Nutzer die Apps behalten. Viele Löschungen nach einem Update sind ein Warnsignal.", "Shows whether users keep the apps. Many deletions after an update are a warning sign."), na: k => k === "google" ? STORE_NA : null, draw: (k, rs, W) => installsChart(W) },
    { g: tx("Downloads und Store", "Downloads and store"), id: "countries", title: tx("Downloads nach Land", "Downloads by country"), sub: tx("Erstinstallationen im Zeitraum", "First-time downloads in the period"),
      why: tx("Zeigt, in welchen Ländern sich Übersetzungen und Marketing lohnen.", "Shows in which countries translations and marketing pay off."), na: k => k === "google" ? STORE_NA : null, draw: () => countryChart() },
    { g: tx("Downloads und Store", "Downloads and store"), id: "sources", title: tx("Woher kommen die Downloads?", "Where do downloads come from?"), sub: tx("Anteil der Erstinstallationen nach Quelle", "Share of first-time downloads by source"),
      why: tx("Zeigt, ob Nutzer die App über die Suche finden, beim Stöbern oder über Verweise.", "Shows whether users find the app via search, browsing or referrals."), na: k => k === "google" ? STORE_NA : null, draw: () => sourceChart() },
    { g: tx("Downloads und Store", "Downloads and store"), id: "funnel", title: tx("Vom Store-Eintrag zum Download", "From store listing to download"), sub: tx("Impressionen, Seitenaufrufe und Erstinstallationen im Zeitraum", "Impressions, page views and first-time downloads in the period"),
      why: tx("Zeigt, wie viele Menschen die App im Store sehen und wie viele sie laden. Gut, um über Screenshots und Store-Texte zu sprechen.", "Shows how many people see the app in the store and how many download it. Useful for talking about screenshots and store texts."), na: k => k === "google" ? STORE_NA : null, draw: () => funnelChart() },
    { g: tx("Stabilität und Nutzung", "Stability and usage"), id: "crashes", title: tx("Abstürze und Bewertung", "Crashes and rating"), sub: tx("Pro Woche: Abstürze je 1000 Sitzungen, Linie = Ø Sterne", "Per week: crashes per 1,000 sessions, line = average stars"),
      why: tx("Macht sichtbar, ob ein fehlerhaftes Update die Bewertungen drückt.", "Shows whether a faulty update pushes ratings down."), na: k => k === "google" ? STAB_NA : null, draw: (k, rs, W) => weeklyStab(rs, W, true, k) },
    { g: tx("Stabilität und Nutzung", "Stability and usage"), id: "sessions", title: tx("Sitzungen pro Woche", "Sessions per week"), sub: tx("Wie oft die Apps geöffnet werden", "How often the apps are opened"),
      why: tx("Zeigt echte Nutzung statt nur Bewertungen.", "Shows real usage rather than just ratings."), na: k => k === "google" ? STAB_NA : null, draw: (k, rs, W) => weeklyStab(rs, W, false, k) },
    { g: tx("Stabilität und Nutzung", "Stability and usage"), id: "weekly", title: tx("Wochenübersicht: Sitzungen, Abstürze, Downloads", "Weekly overview: sessions, crashes, downloads"), sub: tx("Drei Säulenreihen mit gemeinsamer Wochenachse, jede mit eigener Skala", "Three bar rows on a shared week axis, each with its own scale"),
      why: tx("Zeigt auf einen Blick, ob Nutzung, Abstürze und Downloads zusammen steigen oder fallen, etwa nach einem Update. Maus über eine Säule zeigt alle drei Werte der Woche.", "Shows at a glance whether usage, crashes and downloads rise or fall together, e.g. after an update. Hover a bar for all three values of the week."),
      na: k => k === "google" ? STAB_NA : null, draw: (k, rs, W) => weeklyOverview(W, k) },
    { g: tx("Stabilität und Nutzung", "Stability and usage"), id: "rollout", title: tx("Wie schnell kommen Updates an?", "How fast do updates arrive?"), sub: tx("Anteil der Sitzungen je App-Version, pro Woche", "Share of sessions per app version, per week"),
      why: tx("Zeigt, wie lange alte Versionen noch genutzt werden.", "Shows how long old versions stay in use."), na: k => k === "google" ? STAB_NA : null, draw: (k, rs, W) => rolloutChart(W) },
  ];
  let chartIdx = 0;
  try { const i = CHARTS.findIndex(c => c.id === localStorage.getItem("chart")); if (i >= 0) chartIdx = i; } catch (e) {}
  { const m = /\bchart=([a-z]+)/.exec(flags), i = m ? CHARTS.findIndex(c => c.id === m[1]) : -1; if (i >= 0) chartIdx = i; }  // index.html?chart=netscore
  function chartStores() {
    if (state.f.platform) return [state.f.platform];
    const have = new Set(DATA.apps.filter(inScope).map(a => a.platform));
    return ["apple", "google"].filter(p => have.has(p));
  }
  function goChart(i) { chartIdx = (i + CHARTS.length) % CHARTS.length; try { localStorage.setItem("chart", CHARTS[chartIdx].id); } catch (e) {} renderCharts(); }
  function chartView(big) {
    const c = CHARTS[chartIdx], ks = chartStores(), two = ks.length > 1, W = big ? (two ? 600 : 1180) : (two ? 540 : 1000); // Zeichenbreite ≈ Bildschirmbreite, damit Schrift nicht aufgebläht wird
    const sel = h("select", { id: big ? "chartselbig" : "chartsel", "aria-label": tx("Diagramm wählen", "Choose chart") },
      [...new Set(CHARTS.map(x => x.g))].map(g => h("optgroup", { label: g }, CHARTS.map((x, i) => x.g === g ? h("option", { value: String(i) }, x.title) : null))));
    sel.value = String(chartIdx);
    sel.addEventListener("change", () => goChart(Number(sel.value)));
    const nav = (label, text, f) => h("button", { type: "button", class: "chnav", title: label, "aria-label": label, onclick: f }, text);
    const panels = ks.map(k => { const reason = c.na ? c.na(k) : null;
      return h("div", { class: "panel" }, two ? h("h3", { style: "margin:0" }, plat(k)) : null,
        reason ? h("div", { class: "chna" }, h("b", {}, tx("Für ", "Not available for ") + platName(k) + tx(" nicht verfügbar", "")), reason) : c.draw(k, current.filter(r => r.platform === k), W)); });
    return h("div", {},
      h("div", { class: "chbar" }, h("h2", {}, tx("Diagramme", "Charts"), big ? null : infoBtn("diagramme")),
        h("div", { class: "grow" }, nav(tx("Vorheriges Diagramm", "Previous chart"), "‹", () => goChart(chartIdx - 1)), sel, nav(tx("Nächstes Diagramm", "Next chart"), "›", () => goChart(chartIdx + 1))),
        h("span", { class: "chcount" }, (chartIdx + 1) + " / " + CHARTS.length),
        big ? null : reportButtons(null, PRINTERS.charts), big ? nav(tx("Schließen", "Close"), "×", () => $("chartdlg").close()) : nav(tx("Diagramm groß anzeigen", "Show chart large"), "⤢", openChart), big ? null : colBtn("diagramme")),
      h("p", { class: "chsub" }, c.sub),
      ks.length ? h("div", { class: "panels" }, panels) : h("div", { class: "muted" }, tx("Keine App in der Auswahl.", "No app in the selection.")),
      h("p", { class: "chwhy" }, h("b", {}, tx("Wozu: ", "Why: ")), c.why));
  }
  // Diagramm-Bericht zum Drucken (Wunsch des Nutzers): zehn Diagramme in fester Reihenfolge, Plattformen untereinander. Ist eine
  // Plattform nicht darstellbar (c.na, z. B. keine Stabilitätsdaten für Google), erscheint nur die andere mit dem Hinweis
  // „Nur für iOS“ bzw. „Nur für Android“; sind beide nicht darstellbar, fehlt das Diagramm ganz.
  const PRINT_CHARTS = ["portfolio", "trend", "stars", "apps", "netscore", "downloads", "countries", "crashes", "sessions", "weekly"];
  function buildChartsReport(opts) {
    const ks = chartStores(), out = [];
    for (const id of PRINT_CHARTS) {
      const c = CHARTS.find(x => x.id === id); if (!c) continue;
      const ok = ks.filter(k => !(c.na && c.na(k)));
      if (!ok.length) continue;
      const only = ks.length > 1 && ok.length === 1 ? (ok[0] === "apple" ? tx("Nur für iOS", "iOS only") : tx("Nur für Android", "Android only")) : null;
      out.push(h("div", { class: "pr-fig" }, h("h2", {}, c.title, only ? h("span", { class: "pr-only" }, only) : null), h("p", { class: "chsub" }, c.sub),
        ok.map(k => h("div", { class: "panel" }, ok.length > 1 ? h("h3", {}, plat(k)) : null, c.draw(k, current.filter(r => r.platform === k), 680))),
        h("p", { class: "chwhy" }, h("b", {}, tx("Wozu: ", "Why: ")), c.why)));
    }
    return [opts && opts.all ? null : h("div", { class: "pr-head" }, h("div", { class: "pr-k" }, tx("Diagramme", "Charts")), h("h1", {}, tx("Diagramme zur Auswahl", "Charts for the selection"))),
      out.length ? out : h("p", { class: "muted" }, tx("Keine App in der Auswahl.", "No app in the selection.")),
      h("div", { class: "pr-foot" }, tx("Alle Diagramme folgen dem Filter oben. Datenstand ", "All charts follow the filter above. Data as of ") + fmtDate(DATA.dataAsOf || "") + ".")];
  }
  function renderCharts() {
    $("charts").replaceChildren(chartView(false));
    const d = $("chartdlg");
    if (d.open) { const f = document.activeElement && document.activeElement.id; d.replaceChildren(chartView(true), tip); const el = f && $(f); if (el && el.focus) el.focus(); }
  }
  function openChart() { const d = $("chartdlg"); d.replaceChildren(chartView(true), tip); if (d.showModal) d.showModal(); else d.setAttribute("open", ""); }
  $("chartdlg").addEventListener("click", e => { if (e.target === $("chartdlg")) $("chartdlg").close(); });
  $("chartdlg").addEventListener("close", () => { tip.className = ""; document.body.append(tip); });
  // Pfeiltasten blättern, solange die Diagrammkarte oder das große Fenster den Fokus hat (nicht in der Auswahlbox)
  document.addEventListener("keydown", e => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const t = e.target; if (!t || !t.closest || t.tagName === "SELECT" || !(t.closest("#diagramme") || t.closest("#chartdlg"))) return;
    e.preventDefault(); goChart(chartIdx + (e.key === "ArrowLeft" ? -1 : 1));
  });

