  // KI-Bausteine für die Fachbereiche (Entscheidung des Nutzers 24.10.2026: kein eigener Reiter „KI-Analyse“, die KI-Texte
  // stehen dort, wo die Frage beantwortet wird): Zusammenfassung je App und Maßnahmenliste im Überblick, Spalten in
  // „Apps im Vergleich“, Wirkungskontrolle bei „Was ein Update verändert hat“, Themen und Wünsche unter „Themen und Wörter“,
  // Stimmungsleiste und Kennzahlen im Reiter Rezensionen, Antwortentwürfe bei „Antworten des Supports“. Eigenen Reiter hat
  // nur „Fragen an die Daten“ („KI-Anfragen“). Zahlen stammen aus den gespeicherten Daten, Texte von der KI
  // (DATA.ai je App, Felder aus src/ai_analysis.py); jede KI-Aussage trägt die Marke „KI“ und nennt Anbieter, Modell, Datum.
  const SENTIMENT = [["begeistert", "Begeistert", "Delighted", "r5"], ["zufrieden", "Zufrieden", "Satisfied", "r4"],
    ["wunsch", "Wunsch / Vorschlag", "Wish / suggestion", "r3"], ["veraergert", "Verärgert", "Annoyed", "r2"],
    ["resigniert", "Resigniert (droht Wechsel)", "Resigned (threatens to leave)", "r1"], ["unklar", "Unklar", "Unclear", ""]];
  const URGENCY = [["hoch", "hoch", "high", "r"], ["mittel", "mittel", "medium", "y"], ["niedrig", "niedrig", "low", "g"]];
  const ASSESS = { produkt: ["Produktproblem", "Product problem", "r"], update: ["Update-Problem", "Update problem", "y"],
    anbieter: ["Anbieter / Service", "Provider / service", "y"], keine: ["Keine nennenswerte Kritik", "No notable criticism", "g"],
    unklar: ["Unklar", "Unclear", "n"] };
  // Zuständigkeit einer Maßnahme (src/ai_analysis.py OWNERS) und erwartete Wirkung (EFFECTS)
  const OWNER = { entwicklung: ["Entwicklung", "Development"], support: ["Support", "Support"], anbieter: ["Anbieter", "Provider"],
    store: ["Store-Auftritt", "Store listing"], produkt: ["Produkt", "Product"] };
  const EFFECT = { hoch: ["Wirkung hoch", "high impact", "r5"], mittel: ["Wirkung mittel", "medium impact", "r3"], niedrig: ["Wirkung niedrig", "low impact", ""] };
  const sentLabel = key => { const s = SENTIMENT.find(x => x[0] === key); return s ? tx(s[1], s[2]) : key || "–"; };
  const sentPill = key => { const s = SENTIMENT.find(x => x[0] === key); return h("span", { class: "pill " + (s ? s[3] : "") }, sentLabel(key)); };
  const assessPill = key => { const a = ASSESS[key] || ASSESS.unklar; return h("span", { class: "row", style: "gap:.35rem" }, h("i", { class: "dot " + a[2] }), tx(a[0], a[1])); };
  const kiMark = () => h("span", { class: "kimark", title: tx("Text eines Sprachmodells, kein Messwert", "Text from a language model, not a measurement") }, "KI");
  const kiSource = (doc, at) => h("div", { class: "note" }, tx("KI: ", "AI: ") + (doc.provider || "?") + " · " + (doc.model || "?") + (at ? tx(" · erzeugt ", " · generated ") + fmtDate(at) : ""));
  // aiOn: Anbieter aktiv oder Analysen vorhanden; featOn: Funktion in ai.features nicht abgeschaltet
  const aiOn = () => !!DATA.aiEnabled;
  const featOn = name => aiOn() && !(DATA.aiFeatures && DATA.aiFeatures[name] === false);
  const aiDocs = () => (DATA.ai || []).filter(inScope);
  const aiDocOf = a => (DATA.ai || []).find(x => x.customerId === a.customerId && x.appId === a.appId && x.platform === a.platform) || null;
  const noAi = () => h("div", { class: "muted" }, tx("Noch keine KI-Analyse für diese Auswahl. Starten mit ./ratings.sh analyze (Menü: KI-Analyse).", "No AI analysis yet for this selection. Run ./ratings.sh analyze (menu: AI analysis)."));
  const reviewById = new Map(reviews.map(r => [r.id, r]));
  const openReview = id => { const r = reviewById.get(id); if (r) showDetail(r); };
  const quoteRow = q => h("div", { class: "quote kiquote click", tabindex: "0", onclick: () => openReview(q.reviewId), onkeydown: e => { if (e.key === "Enter") openReview(q.reviewId); } },
    "„" + q.text + "“", h("div", { class: "note", style: "margin-top:.3rem" }, (q.rating ? "★ " + q.rating + " · " : "") + fmtDate(q.createdAt) + (q.appName ? " · " + q.appName : "")));
  const normIssue = t => String(t || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const isBad = r => r.aiSentiment === "veraergert" || r.aiSentiment === "resigniert" || r.aiUrgency === "hoch" || (r.rating >= 1 && r.rating <= 2);
  const sameApp = (r, a) => r.customerId === a.customerId && r.appId === a.appId && r.platform === a.platform;
  // Entwürfe als erledigt markieren: nur im Browser (localStorage „aiDone“), damit die Liste abgearbeitet werden kann
  let aiDone = []; try { aiDone = JSON.parse(localStorage.getItem("aiDone") || "[]"); } catch (e) {}
  const saveDone = () => { try { localStorage.setItem("aiDone", JSON.stringify(aiDone)); } catch (e) {} };
  function copyBtn(text) {
    const b = h("button", { type: "button", class: "btn" }, tx("Kopieren", "Copy"));
    b.addEventListener("click", () => { const ok = () => { b.textContent = tx("Kopiert ✓", "Copied ✓"); setTimeout(() => { b.textContent = tx("Kopieren", "Copy"); }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, () => { window.prompt(tx("Text zum Kopieren:", "Text to copy:"), text); });
      else window.prompt(tx("Text zum Kopieren:", "Text to copy:"), text); });
    return b;
  }

  // ---- Überblick: Zusammenfassung je App (Inhalt des KI-Overlays „Was sagen die Nutzer?“) ----
  function kiSummaryCell(a) {
    if (!featOn("summary")) return null;
    const doc = aiDocOf(a), s = doc && doc.summary; if (!s || !s.text) return null;
    return h("div", { class: "kisum" },
      h("p", {}, s.text),
      h("div", { class: "kifacts" }, h("div", {}, h("b", {}, tx("Lob: ", "Praise: ")), s.praise || "–"), h("div", {}, h("b", {}, tx("Kritik: ", "Criticism: ")), s.criticism || "–"),
        h("div", { class: "row", style: "gap:.4rem" }, h("b", {}, tx("Einschätzung: ", "Assessment: ")), assessPill(s.assessment), s.assessmentReason ? h("span", { class: "muted" }, "– " + s.assessmentReason) : null)),
      (s.quotes || []).length ? h("div", { class: "kiquotes" }, (s.quotes || []).slice(0, 3).map(quoteRow)) : null,
      h("div", { class: "note" }, tx("Grundlage: ", "Based on: ") + fmtInt((s.basedOn || []).length) + tx(" jüngste Rezensionen", " most recent reviews")), kiSource(doc, s.generatedAt));
  }

  // ---- Überblick: „Das sollten wir tun“. Höchstens fünf Punkte aus Ampel (ohne KI), offenen negativen Rezensionen, Maßnahmen und
  // Häufungen der KI, Abwanderungsdrohungen; jeder mit Beleg und Sprung in den Bereich. Reihenfolge: rot vor gelb, KI-Maßnahmen
  // nach erwarteter Wirkung, zuletzt Hinweise. rows = overviewRows() aus auswertungen.js.
  function actionItems(rows) {
    const items = [], go = (tab, id, more) => () => { if (more) { secState.more = true; saveSecs(); } setTab(tab); const t = $(id); if (t && t.scrollIntoView) t.scrollIntoView({ block: "start" }); };
    for (const r of rows.filter(x => x.level === 2)) items.push({ lvl: 2, rank: 0, text: appLabel(r.a) + tx(": jetzt ansehen", ": look now"), why: r.why.join(" · "), go: () => selectApp(r.key) });
    if (featOn("measures")) {
      const ms = DATA.apps.filter(inScope).flatMap(a => { const d = aiDocOf(a); return ((d && d.summary && d.summary.measures) || []).map(m => Object.assign({ a, doc: d }, m)); })
        .sort((x, y) => ["hoch", "mittel", "niedrig"].indexOf(x.effect) - ["hoch", "mittel", "niedrig"].indexOf(y.effect) || (y.reviewCount || 0) - (x.reviewCount || 0));
      for (const m of ms.slice(0, 4)) items.push({ lvl: m.effect === "hoch" ? 2 : 1, rank: 1, ki: true, text: m.title, owner: m.owner, effect: m.effect,
        why: appLabel(m.a) + (m.negShare !== null && m.negShare !== undefined ? tx(" · betrifft " + m.negShare + " % der negativen Rezensionen (" + fmtInt(m.reviewCount) + ")", " · affects " + m.negShare + " % of negative reviews (" + fmtInt(m.reviewCount) + ")") : "") + (m.reason ? " · " + m.reason : ""),
        go: m.reviewIds && m.reviewIds.length ? () => openReview(m.reviewIds[0]) : () => selectApp(appKeyOf(m.a)) });
    }
    if (featOn("summary")) {
      const urgent = DATA.apps.filter(inScope).flatMap(a => { const d = aiDocOf(a); return ((d && d.summary && d.summary.urgent) || []).filter(u => u.count >= 2).map(u => Object.assign({ a }, u)); }).sort((x, y) => y.count - x.count);
      for (const u of urgent.slice(0, 2)) items.push({ lvl: u.count >= 3 ? 2 : 1, rank: 2, ki: true, text: u.title, why: appLabel(u.a) + " · " + fmtInt(u.count) + tx(" Rezensionen", " reviews") + (u.sinceVersion ? tx(" · seit Version ", " · since version ") + u.sinceVersion : ""),
        go: u.reviewIds && u.reviewIds.length ? () => openReview(u.reviewIds[0]) : () => selectApp(appKeyOf(u.a)) });
    }
    const openNeg = rows.reduce((n, r) => n + r.openNeg.length, 0);
    if (openNeg) items.push({ lvl: 1, rank: 3, text: tx("Offene negative Rezensionen beantworten", "Reply to open negative reviews"), why: fmtInt(openNeg) + tx(" × 1–2 ★ ohne Antwort in 30 Tagen", " × 1–2 ★ without reply in 30 days") + (featOn("replyDrafts") && aiDocs().length ? tx(" · Entwürfe unter „Antworten des Supports“", " · drafts under “Support replies”") : ""), go: go("rez", "antworten") });
    for (const r of rows.filter(x => x.level === 1 && !x.why.every(w => /Antwort|reply/.test(w)))) items.push({ lvl: 1, rank: 4, text: appLabel(r.a) + tx(": ansehen", ": look"), why: r.why.join(" · "), go: () => selectApp(r.key) });
    if (featOn("sentiment")) {
      const d90 = daysBefore(asOfDate, 90), an = reviews.filter(r => inScope(r) && r.aiSentiment && (r.createdAt || "") >= d90), churn = an.filter(r => r.aiChurn), glad = an.filter(r => r.aiSentiment === "begeistert");
      if (churn.length >= 2) items.push({ lvl: 1, rank: 5, ki: true, text: tx("Abwanderung ernst nehmen", "Take churn seriously"), why: fmtInt(churn.length) + tx(" Rezensionen in 90 Tagen drohen mit Wechsel oder Löschen", " reviews in 90 days threaten to leave or delete"), go: () => openReview(churn[0].id) });
      // Bewertungsaufforderung: viele Begeisterte sind der direkteste Hebel auf die Store-Note; die Aufforderung ist Sache der App, nicht des Skripts
      if (an.length >= 10 && glad.length / an.length >= .3) items.push({ lvl: 0, rank: 6, ki: true, text: tx("Bewertungsaufforderung in der App prüfen", "Check the in-app rating prompt"), why: fmtInt(glad.length) + tx(" von " + fmtInt(an.length) + " analysierten Rezensionen in 90 Tagen sind begeistert; wer zufrieden ist, bewertet selten ungefragt", " of " + fmtInt(an.length) + " analysed reviews in 90 days are delighted; happy users rarely rate unprompted"), go: () => openReview(glad[0].id) });
    }
    return items.sort((x, y) => y.lvl - x.lvl || x.rank - y.rank).slice(0, 5);
  }
  function actionList(rows) {
    const items = actionItems(rows);
    if (!items.length) return null;
    return h("div", { class: "actions" }, h("h3", { class: "sub3" }, tx("Das sollten wir tun", "What we should do"), h("span", { class: "muted", style: "font-weight:400" }, tx(" · höchstens fünf Punkte, Klick führt zum Beleg", " · at most five points, click leads to the evidence"))),
      h("ol", { class: "actlist" }, items.map(it => h("li", { class: "click", tabindex: "0", onclick: it.go, onkeydown: e => { if (e.key === "Enter") it.go(); } }, dot(it.lvl),
        h("div", {}, h("b", {}, it.text, it.ki ? kiMark() : null, it.owner ? h("span", { class: "pill owner" }, tx(OWNER[it.owner][0], OWNER[it.owner][1])) : null, it.effect && EFFECT[it.effect][2] ? h("span", { class: "pill " + EFFECT[it.effect][2] }, tx(EFFECT[it.effect][0], EFFECT[it.effect][1])) : null), h("span", {}, it.why))))),
      items.some(it => it.ki) ? h("div", { class: "note" }, tx("Punkte mit Marke „KI“ sind Vorschläge eines Sprachmodells aus Zählungen zu den Rezensionen; Anteile und Anzahlen rechnet der Bericht aus den Daten.", "Items marked “AI” are suggestions from a language model based on counts about the reviews; shares and counts are calculated by the report from the data.")) : null);
  }

  // ---- Reiter Rezensionen: Kennzahlen-Kacheln und Stimmungsleiste (gefilterte Rezensionen) ----
  function kiTiles(rs) {
    if (!featOn("sentiment") || !aiDocs().length) return [];
    const an = rs.filter(r => r.aiSentiment);
    return [kpTile(an.filter(r => r.aiUrgency === "hoch").length, tx("dringend (KI)", "urgent (AI)"), tx("Dringlichkeit hoch laut KI, von " + fmtInt(an.length) + " analysierten", "urgency high according to the AI, of " + fmtInt(an.length) + " analysed")),
      kpTile(an.filter(r => r.aiMismatch).length, tx("Sterne täuschen (KI)", "stars mislead (AI)"), tx("Text widerspricht den Sternen", "text contradicts the stars")),
      kpTile(an.filter(r => r.aiChurn).length, tx("drohen zu wechseln (KI)", "threaten to leave (AI)"), tx("Wechsel oder Löschen angekündigt", "leaving or deleting announced"))];
  }
  function renderKiStrip(rs) {
    const box = $("kistrip"); if (!box.replaceChildren) return; box.replaceChildren();
    if (!featOn("sentiment") || !aiDocs().length) return;
    const an = rs.filter(r => r.aiSentiment);
    if (!an.length) { put(box, h("div", { class: "note", style: "margin:0 0 .6rem" }, tx("Keine analysierten Rezensionen für diese Filter.", "No analysed reviews match these filters."), " ", kiMark())); return; }
    const by = groupBy(an, r => r.aiSentiment), cur = state.f.aiSentiment || "";
    const set = key => { state.f.aiSentiment = cur === key ? "" : key; const sel = $("f_aiSentiment"); if (sel) sel.value = state.f.aiSentiment; render(); };
    put(box, h("div", { class: "kistrip" }, h("span", { class: "lbl" }, tx("Stimmung", "Sentiment"), kiMark()),
      SENTIMENT.filter(s => by.has(s[0])).map(s => h("button", { type: "button", class: "secbtn", "aria-pressed": String(cur === s[0]), onclick: () => set(s[0]) }, h("span", { class: "pill " + s[3] }, tx(s[1], s[2])), " ", fmtInt(by.get(s[0]).length))),
      h("span", { class: "muted", style: "margin-left:auto" }, fmtInt(an.filter(r => r.aiMismatch).length) + tx(" × Sterne täuschen · ", " × stars mislead · ") + fmtInt(an.filter(r => r.aiChurn).length) + tx(" × drohen zu wechseln", " × threaten to leave"))));
  }

  // ---- Themen und Wörter: frei erkannte Themen, Vorschläge für themen.json, meistgewünschte Funktionen ----
  // Jeder dieser drei Blöcke erscheint als Knopf (nur mit KI) und öffnet sein Overlay (#kidlg); so bleibt der Bereich kurz.
  const known = () => new Set(TOPICS.flatMap(t => [t.id, t.de, t.en].filter(Boolean).map(x => x.toLowerCase())));
  function kiThemeSuggestions() {
    const sugg = new Map(), kn = known();
    if (!featOn("themes")) return sugg;
    for (const d of aiDocs()) for (const s of ((d.summary || {}).themeSuggestions || [])) { const k = s.de.toLowerCase(); if (kn.has(k)) continue; const o = sugg.get(k) || { de: s.de, en: s.en, terms: new Set(), count: 0, apps: new Set() }; o.count += s.count || 0; (s.terms || []).forEach(t => o.terms.add(t)); o.apps.add(d.appName); sugg.set(k, o); }
    return sugg;
  }
  function kiThemesBlock() {
    if (!featOn("themes")) return null;
    const rs = current.filter(r => r.aiThemes && r.aiThemes.length), docs = aiDocs();
    if (!rs.length && !docs.length) return null;
    const out = h("div", { class: "kiblock" });
    const kn = known();
    const m = new Map();
    for (const r of rs) for (const t of r.aiThemes) { const k = t.toLowerCase(); const o = m.get(k) || { name: t, n: 0, neg: 0, sum: 0, rated: 0 }; o.n++; if (r.rating <= 2) o.neg++; if (r.rating) { o.sum += r.rating; o.rated++; } m.set(k, o); }
    const rows = [...m.values()].sort((a, b) => b.n - a.n).slice(0, 25);
    if (rows.length) put(out, h("div", { class: "tablewrap", style: "max-height:320px" }, h("table", {}, h("thead", {}, h("tr", {}, [tx("Thema (KI)", "Topic (AI)"), tx("Rezensionen", "Reviews"), tx("davon negativ", "of which negative"), tx("Ø ★", "Avg ★"), tx("In themen.json?", "In themen.json?")].map(t => h("th", {}, t)))),
      h("tbody", {}, rows.map(o => h("tr", {}, h("td", {}, o.name), h("td", { class: "num" }, fmtInt(o.n)), h("td", { class: "num" }, fmtInt(o.neg)), h("td", { class: "num" }, o.rated ? fmt(o.sum / o.rated, 1) : "–"),
        h("td", {}, kn.has(o.name.toLowerCase()) ? tx("ja", "yes") : h("span", { class: "muted" }, tx("nein", "no")))))))),
      h("div", { class: "note" }, tx("Schlagwörter je Rezension; gleiche Schreibweisen zusammengefasst, ähnliche („Login“, „Anmeldung“) nicht.", "Keywords per review; identical spellings merged, similar ones (“login”, “sign-in”) not.")));
    else put(out, h("div", { class: "muted" }, tx("Keine KI-Themen für diese Filter.", "No AI topics match these filters.")));
    const d0 = docs[0]; if (d0) put(out, kiSource(d0, (d0.summary || {}).generatedAt));
    return out;
  }
  function kiSuggestionsBlock() {
    const sugg = kiThemeSuggestions(), docs = aiDocs();
    if (!sugg.size) return null;
    const out = h("div", { class: "kiblock" });
    put(out,
      h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, [tx("Thema", "Topic"), tx("Englisch", "English"), tx("Rezensionen", "Reviews"), "Apps", tx("Suchbegriffe", "Search terms")].map(t => h("th", {}, t)))),
        h("tbody", {}, [...sugg.values()].sort((a, b) => b.count - a.count).map(o => h("tr", {}, h("td", {}, o.de), h("td", {}, o.en), h("td", { class: "num" }, fmtInt(o.count)), h("td", { class: "num" }, fmtInt(o.apps.size)), h("td", { class: "muted" }, [...o.terms].join(", "))))))),
      h("div", { class: "warn" }, tx("Vorschläge kommen erst nach Bestätigung in die Themenliste: ./ratings.sh ai-themes zeigt sie nummeriert, --accept NR übernimmt eines, --ignore NR lehnt es ab (Menü: KI-Analyse → Themenvorschläge). Die regelbasierten Themen oben bleiben die Referenz.", "Suggestions enter the topic list only after confirmation: ./ratings.sh ai-themes lists them numbered, --accept NR adopts one, --ignore NR rejects it (menu: AI analysis → topic suggestions). The rule-based topics above remain the reference.")));
    const d0 = docs[0]; if (d0) put(out, kiSource(d0, (d0.summary || {}).generatedAt));
    return out;
  }
  // Wünsche: Kernaussagen der Rezensionen mit Stimmung „Wunsch“, Anzahl, Trend (letzte 90 Tage gegen die 90 Tage davor), Apps
  function kiWishesBlock() {
    if (!featOn("sentiment") || !aiDocs().length) return null;
    const ws = current.filter(r => r.aiSentiment === "wunsch" && r.aiIssue);
    const out = h("div", { class: "kiblock" });
    if (!ws.length) { put(out, h("div", { class: "muted" }, tx("Keine Rezensionen mit Stimmung „Wunsch“ in dieser Auswahl.", "No reviews with sentiment “wish” in this selection."))); return out; }
    const d90 = daysBefore(asOfDate, 90), d180 = daysBefore(asOfDate, 180), m = new Map();
    for (const r of ws) { const k = normIssue(r.aiIssue); const o = m.get(k) || { issue: r.aiIssue, n: 0, rec: 0, prev: 0, apps: new Set(), ids: [] }; o.n++; const d = (r.createdAt || "").slice(0, 10); if (d >= d90) o.rec++; else if (d >= d180) o.prev++; o.apps.add(r.appName); o.ids.push(r.id); m.set(k, o); }
    const rows = [...m.values()].sort((a, b) => b.n - a.n).slice(0, 10);
    const trend = o => o.rec > o.prev ? h("span", { class: "pill r5" }, "▲ " + o.rec) : o.rec < o.prev ? h("span", { class: "pill r1" }, "▼ " + o.rec) : h("span", { class: "muted" }, "• " + o.rec);
    put(out, h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, [tx("Wunsch (Kernaussage der KI)", "Wish (AI core statement)"), tx("Rezensionen", "Reviews"), tx("letzte 90 Tage", "last 90 days"), "Apps"].map(t => h("th", {}, t)))),
      h("tbody", {}, rows.map(o => h("tr", { class: "click", tabindex: "0", onclick: () => openReview(o.ids[0]), onkeydown: e => { if (e.key === "Enter") openReview(o.ids[0]); } },
        h("td", {}, o.issue), h("td", { class: "num" }, fmtInt(o.n)), h("td", { "data-tip": tx("davor (90 Tage): ", "before (90 days): ") + o.prev }, trend(o)), h("td", { class: "muted" }, [...o.apps].join(", "))))))),
      h("div", { class: "note" }, tx(fmtInt(ws.length) + " Rezensionen mit Stimmung „Wunsch“ in der Auswahl; gleiche Kernaussagen zusammengezählt. ▲/▼: letzte 90 Tage gegenüber den 90 Tagen davor. Klick öffnet eine Rezension dazu.", fmtInt(ws.length) + " reviews with sentiment “wish” in the selection; identical core statements added up. ▲/▼: last 90 days against the 90 days before. Click opens one of the reviews.")));
    return out;
  }

  // Knopfleiste unter „Themen und Wörter“: je ein Knopf pro KI-Block, nur sichtbar, wenn die KI Daten dafür geliefert hat
  function kiTopicButtons() {
    const specs = [[tx("Themen laut KI", "Topics according to the AI"), kiThemesBlock], [tx("Vorschläge für neue Themen in config/themen.json", "Suggestions for new topics in config/themen.json"), kiSuggestionsBlock], [tx("Meistgewünschte Funktionen", "Most requested features"), kiWishesBlock]];
    const btns = specs.filter(sp => sp[1]()).map(sp => h("button", { type: "button", class: "btn", "aria-haspopup": "dialog", onclick: () => openKiDialog(sp[0], null, () => sp[1]()) }, sp[0], " ", kiMark()));
    return btns.length ? h("div", { class: "kistrip", style: "margin-top:1.6rem" }, btns) : null;
  }

  // ---- Was ein Update verändert hat: Wirkungskontrolle je Veröffentlichung. Kernaussagen negativer oder dringender Rezensionen
  // im Fenster danach, die davor fehlten („neu“), und solche von davor, die danach fehlen („verschwunden“); je bis zu drei.
  function kiReleaseCell(before, after) {
    const count = rs => { const m = new Map(); for (const r of rs) if (r.aiIssue && isBad(r)) { const k = normIssue(r.aiIssue); const o = m.get(k) || { issue: r.aiIssue, n: 0, id: r.id }; o.n++; m.set(k, o); } return m; };
    const b = count(before), a = count(after);
    if (!b.size && !a.size) return h("td", { class: "muted" }, "–");
    const top = (m, other) => [...m.entries()].filter(([k]) => !other.has(k)).map(([, o]) => o).sort((x, y) => y.n - x.n).slice(0, 2);
    const fresh = top(a, b), gone = top(b, a);
    // Kompakt: je Liste eine Zeile mit Auslassungspunkten (volle Liste als Tooltip), höchstens zwei Einträge; Klick öffnet die Rezension
    const items = (list, cls) => list.map((o, i) => [i ? " · " : null, h("a", { class: "kiissue " + cls, href: "#", onclick: e => { e.preventDefault(); e.stopPropagation(); openReview(o.id); } }, o.issue + " (" + o.n + ")")]);
    const line = (label, list, cls) => h("div", { class: "clip1", "data-tip": label + list.map(o => o.issue + " (" + o.n + ")").join(" · ") }, h("b", {}, label), items(list, cls));
    return h("td", { class: "kirel" }, fresh.length ? line(tx("neu: ", "new: "), fresh, "neg") : null, gone.length ? line(tx("weg: ", "gone: "), gone, "pos") : null,
      !fresh.length && !gone.length ? h("span", { class: "muted" }, tx("unverändert", "unchanged")) : null);
  }
  const kiReleaseOn = () => featOn("versions") && featOn("sentiment") && aiDocs().length > 0;
  // Vergleich nach Version: Beschwerden, die nur in der neuesten Version vorkommen (Version aus KI, Rezension oder Store-Datum)
  function kiVersionNote(rels) {
    if (!kiReleaseOn()) return null;
    const byVer = new Map();
    for (const r of current) { if (!r.aiIssue || !isBad(r)) continue; const v = r.aiVersion || versionOfReview(r, rels.get(r.customerId + "/" + r.appId + "/" + r.platform) || []); if (!v) continue;
      const o = byVer.get(v) || { v, issues: new Map() }; o.issues.set(normIssue(r.aiIssue), { issue: r.aiIssue, n: ((o.issues.get(normIssue(r.aiIssue)) || {}).n || 0) + 1, id: r.id }); byVer.set(v, o); }
    const rows = [...byVer.values()].sort((a, b) => b.v.localeCompare(a.v, "de", { numeric: true }));
    if (rows.length < 2) return null;
    const newest = rows[0], older = new Set(rows.slice(1).flatMap(o => [...o.issues.keys()]));
    const fresh = [...newest.issues.entries()].filter(([k]) => !older.has(k)).map(([, o]) => o).sort((a, b) => b.n - a.n).slice(0, 5);
    if (!fresh.length) return null;
    return h("div", { class: "warn" }, h("b", {}, tx("Nur in Version " + newest.v + ": ", "Only in version " + newest.v + ": ")), fresh.map((o, i) => [i ? " · " : null, h("a", { class: "kiissue neg", href: "#", onclick: e => { e.preventDefault(); openReview(o.id); } }, o.issue + " (" + o.n + ")")]), " ", kiMark(),
      h("div", { class: "note", style: "margin-top:.3rem" }, tx("Kernaussagen negativer oder dringender Rezensionen, die in älteren Versionen fehlen. Version aus dem Rezensionstext, der Rezension (Google) oder bei Apple über das Datum der Store-Version geschätzt.", "Core statements of negative or urgent reviews missing in older versions. Version from the review text, the review (Google) or, for Apple, estimated from the store version date.")));
  }

  // ---- Apps im Vergleich: Spalten verärgert, Hauptlob, Hauptkritik, Einschätzung (nur wenn Zusammenfassungen vorliegen) ----
  const kiCompareOn = facts => featOn("comparison") && facts.some(f => { const d = aiDocOf(f.a); return d && d.summary; });
  const kiCompareHeads = () => [tx("verärgert (KI)", "annoyed (AI)"), tx("Hauptlob (KI)", "Main praise (AI)"), tx("Hauptkritik (KI)", "Main criticism (AI)"), tx("Einschätzung (KI)", "Assessment (AI)")];
  function kiCompareCells(a, win) {
    const d = aiDocOf(a), s = d && d.summary;
    const rs = current.filter(r => sameApp(r, a) && inWin(r.createdAt, win) && r.aiSentiment), bad = rs.filter(r => r.aiSentiment === "veraergert" || r.aiSentiment === "resigniert").length;
    return [h("td", { class: "num", "data-tip": rs.length ? fmtInt(bad) + tx(" von " + fmtInt(rs.length) + " analysierten Rezensionen ", " of " + fmtInt(rs.length) + " analysed reviews ") + win.label : tx("keine analysierten Rezensionen im Zeitraum", "no analysed reviews in the period") }, rs.length ? fmt(100 * bad / rs.length, 0) + " %" : h("span", { class: "muted" }, "–")),
      h("td", { class: "txt" }, s && s.praise ? s.praise : h("span", { class: "muted" }, "–")), h("td", { class: "txt" }, s && s.criticism ? s.criticism : h("span", { class: "muted" }, "–")), h("td", {}, s ? assessPill(s.assessment) : h("span", { class: "muted" }, "–"))];
  }

  // ---- Die wichtigsten Zahlen je App: Anteil Abwanderungsdrohungen im Fenster ----
  const kiChurnOn = () => featOn("sentiment") && aiDocs().length > 0;
  function kiChurnShare(rs) { const an = rs.filter(r => r.aiSentiment); return an.length ? { share: 100 * an.filter(r => r.aiChurn).length / an.length, n: an.filter(r => r.aiChurn).length, of: an.length } : null; }

  // ---- KI-Overlay: Zusammenfassung „Was sagen die Nutzer?“ und Antwortentwurf erscheinen als Fenster über der Seite, nicht mehr
  // eingeblendet in der Tabelle. `build` liefert den Inhalt neu (damit „erledigt“ den Knopf im offenen Fenster aktualisieren kann).
  function openKiDialog(title, sub, build) {
    const d = $("kidlg");
    const render = () => {
      d.replaceChildren(h("div", { class: "dhead" }, h("div", { class: "row", style: "justify-content:space-between;gap:1rem" },
          h("h2", { style: "font-size:1.35rem;margin:0" }, title, " ", kiMark()), h("button", { class: "iconbtn", type: "button", "aria-label": tx("Schließen", "Close"), onclick: () => d.close() }, "×")),
        sub ? h("div", { class: "muted", style: "margin-top:.3rem" }, sub) : null), h("div", { class: "dbody" }, build(render)));
    };
    render();
    if (d.showModal && !d.open) d.showModal(); else d.setAttribute("open", "");
  }
  $("kidlg").addEventListener("click", e => { if (e.target === $("kidlg") && $("kidlg").close) $("kidlg").close(); });

  // ---- Antworten des Supports: Entwurf je offener Rezension (Knopf öffnet das KI-Overlay), Kopieren, erledigt (nur dieser Browser) ----
  const kiDraftOn = () => featOn("replyDrafts") && aiDocs().length > 0;
  function kiDraftCell(r, rerender) {
    if (!r.aiDraft) return h("td", { class: "muted" }, "–");
    const isDone = aiDone.includes(r.id);
    return h("td", { class: "nw" }, h("button", { type: "button", class: "btn", "aria-haspopup": "dialog", onclick: e => { e.stopPropagation(); openKiDialog(tx("Antwortentwurf", "Reply draft"), r.appName + " · " + (r.title || tx("(ohne Titel)", "(no title)")), refresh => kiDraftBody(r, () => { rerender(); refresh(); })); } }, tx("Entwurf", "Draft"), isDone ? " ✓" : ""), " ", kiMark());
  }
  function kiDraftBody(r, rerender) {
    const isDone = aiDone.includes(r.id);
    return h("div", { class: "kidraft" + (isDone ? " done" : "") }, h("div", { class: "row", style: "gap:.4rem;align-items:center" }, h("span", { class: "muted" }, r.aiDraft.text.length + tx(" Zeichen", " characters") + (r.aiDraft.language ? " · " + r.aiDraft.language : ""))),
      h("div", { class: "quote reply" }, r.aiDraft.text),
      h("div", { class: "row", style: "gap:.5rem" }, copyBtn(r.aiDraft.text), h("button", { type: "button", class: "btn", onclick: () => { aiDone = isDone ? aiDone.filter(x => x !== r.id) : aiDone.concat([r.id]); saveDone(); rerender(); } }, isDone ? tx("Wieder öffnen", "Reopen") : tx("Als erledigt markieren", "Mark as done")), h("button", { type: "button", class: "linkbtn", onclick: () => { $("kidlg").close(); showDetail(r); } }, tx("Rezension öffnen", "Open review"))),
      h("div", { class: "note" }, tx("Wird nie gesendet. Antworten geht nur in App Store Connect bzw. der Play Console; [Kontakt] vor dem Senden durch den echten Kontaktweg ersetzen. „Erledigt“ merkt sich nur dieser Browser.", "Never sent. Replies are possible only in App Store Connect or the Play Console; replace [Kontakt] with the real contact channel before sending. “Done” is remembered only in this browser.")));
  }

  // ---- Fragen und Antworten (ki.py ask) und Verbrauch ----
  // Lokaler Fragedienst (ki.py serve): Port und Token stehen nur in einem Bericht, der erzeugt wurde, während er lief.
  // Der Bericht fragt einmal /status; nur bei Antwort erscheint das Eingabefeld. Alles andere bleibt offline.
  const SVC = DATA.aiService && typeof fetch === "function" ? DATA.aiService : null;
  let svcState = SVC ? "unknown" : "none", svcInfo = null, svcError = null, asking = false;
  const svcUrl = path => "http://127.0.0.1:" + SVC.port + path;
  const svcHeaders = () => ({ "Content-Type": "application/json", "X-Ai-Token": SVC.token });
  if (SVC) fetch(svcUrl("/status"), { headers: svcHeaders() }).then(r => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
    .then(info => { svcState = "up"; svcInfo = info; askUp = true; applyTabs(); renderKiQuestions(); }).catch(() => { svcState = "down"; askUp = false; applyTabs(); renderKiQuestions(); });
  // Wartefenster: der Anbieter braucht meist 5 bis 30 Sekunden; das Fenster blockiert die Seite, bis die Antwort da ist
  function showWait(question) {
    const d = $("kiwait"); if (!d.replaceChildren) return;
    d.replaceChildren(h("div", { class: "kispin", "aria-hidden": "true" }), h("div", { style: "font-weight:600;margin-bottom:.3rem" }, tx("Frage läuft …", "Asking …")),
      h("div", { class: "muted", style: "font-size:.9rem" }, tx("Der KI-Anbieter antwortet meist in 5 bis 30 Sekunden.", "The AI provider usually answers within 5 to 30 seconds.")), h("div", { class: "note" }, "„" + question + "“"));
    if (d.showModal && !d.open) d.showModal(); else d.setAttribute("open", "");
  }
  function hideWait() { const d = $("kiwait"); if (d.close && d.open) d.close(); else if (d.removeAttribute) d.removeAttribute("open"); }
  if ($("kiwait").addEventListener) $("kiwait").addEventListener("cancel", e => e.preventDefault());  // Esc schließt nicht, die Anfrage läuft weiter
  function deleteQuestion(q, done) {
    fetch(svcUrl("/delete"), { method: "POST", headers: svcHeaders(), body: JSON.stringify({ askedAt: q.askedAt, question: q.question }) })
      .then(r => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
      .then(() => { DATA.aiQuestions = (DATA.aiQuestions || []).filter(x => !(x.askedAt === q.askedAt && x.question === q.question)); done(null); })
      .catch(() => done(tx("Löschen fehlgeschlagen. Läuft der Fragedienst noch?", "Deleting failed. Is the question service still running?")));
  }
  let showAllQuestions = false;
  const QUESTIONS_SHOWN = 10;
  // Auswahl für den Fragedienst: Kunde/App/Plattform wie bisher, dazu die ganze Filterauswahl des Berichts: Liste der
  // gewählten Apps, Zeitraum, Sterne und die IDs der gerade gefilterten Rezensionen (`current`, damit auch Thema, Suche,
  // Stimmung gelten; höchstens 3000) sowie die Filter-Kärtchen als Beschreibung (Wunsch des Nutzers 24.10.2026)
  const SELECTION_IDS = 3000;
  function askSelection() {
    const sel = state.f, cust = (sel.customerId || []).length === 1 ? sel.customerId[0] : null, app = (sel.appKey || []).length === 1 ? sel.appKey[0] : null;
    const label = controls.flatMap(c => c.items ? c.items().map(it => c.label + ": " + it.text) : (c.active() ? [c.label + ": " + c.active()] : [])).join(" · ");
    return { customer: app ? app.split("/")[0] : cust, app: app ? app.split("/").slice(1).join("/") : null, platform: sel.platform || "all",
      selection: { apps: sel.appKey || [], from: sel.from || null, to: sel.to || null, ratingMin: sel.ratingMin || null, ratingMax: sel.ratingMax || null,
        reviewIds: current.slice(0, SELECTION_IDS).map(r => r.id), label: label.slice(0, 300) || null } };
  }
  function askService(question, done) {
    const body = Object.assign({ question }, askSelection());
    fetch(svcUrl("/ask"), { method: "POST", headers: svcHeaders(), body: JSON.stringify(body) })
      .then(r => r.json().then(data => ({ ok: r.ok, data })))
      .then(({ ok, data }) => { if (ok && data.entry) { (DATA.aiQuestions = DATA.aiQuestions || []).push(data.entry); done(null); } else done((data && data.error) || tx("Unbekannter Fehler.", "Unknown error.")); })
      .catch(() => done(tx("Der Fragedienst antwortet nicht. Läuft ./ratings.sh ai-serve noch?", "The question service does not respond. Is ./ratings.sh ai-serve still running?")));
  }
  function askForm() {
    const input = h("input", { type: "text", id: "kiq", maxlength: "500", placeholder: tx("Frage an die Rezensionen der Auswahl, z. B. „Welche Apps erwähnen das Bonusprogramm?“", "Question to the selected reviews, e.g. “Which apps mention the bonus programme?”"), "aria-label": tx("Frage", "Question") });
    const btn = h("button", { type: "button", class: "btn primary" }, asking ? tx("Frage läuft …", "Asking …") : tx("Fragen", "Ask"));
    const note = h("div", { class: "note" }, svcError ? h("span", { style: "color:var(--bad)" }, svcError) : tx("Lokaler Fragedienst aktiv (", "Local question service active (") + (svcInfo ? svcInfo.provider + " / " + svcInfo.model : "") + tx("). Jede Frage kostet eine Anfrage. Sie bezieht sich auf die gefilterten Rezensionen (" + fmtInt(Math.min(current.length, SELECTION_IDS)) + " nach allen Filtern oben, davon die jüngsten bis zum Budget); die Antwort wird gespeichert.", "). Each question costs one request. It refers to the filtered reviews (" + fmtInt(Math.min(current.length, SELECTION_IDS)) + " after all filters above, of which the most recent up to the budget); the answer is saved."));
    const go = () => { const q = input.value.trim(); if (!q || asking) return; asking = true; svcError = null; btn.disabled = true; btn.textContent = tx("Frage läuft …", "Asking …"); showWait(q);
      askService(q, err => { asking = false; svcError = err; hideWait(); if (!err) input.value = ""; renderKiQuestions(); if (!err) { const field = $("kiq"); if (field && field.focus) field.focus(); } }); };
    btn.addEventListener("click", go); input.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
    if (asking) { btn.disabled = true; input.disabled = true; }
    // Vorgefertigte Fragen (config/fragen.json, DATA.aiPresetQuestions): Overlay mit Liste; Klick trägt die Frage ein und sendet
    // sie sofort (Wunsch des Nutzers 24.10.2026), Abbrechen schließt nur
    const presets = DATA.aiPresetQuestions || [], pick = presets.length ? h("button", { type: "button", class: "btn", onclick: () => presetDialog(q => { input.value = q; go(); }) }, tx("Fragen wählen …", "Choose a question …")) : null;
    if (pick && asking) pick.disabled = true;
    return h("div", { class: "kiask" }, h("div", { class: "row", style: "gap:.5rem;flex-wrap:wrap" }, input, btn, pick), note);
  }
  function presetDialog(onPick) {
    const d = $("kiqdlg"); if (!d.replaceChildren) return;
    const close = () => { if (d.close && d.open) d.close(); else if (d.removeAttribute) d.removeAttribute("open"); };
    d.replaceChildren(h("div", { class: "infohead" }, h("h2", {}, tx("Frage wählen", "Choose a question")), h("button", { class: "iconbtn", type: "button", "aria-label": tx("Abbrechen", "Cancel"), onclick: close }, "×")),
      h("p", { class: "note", style: "margin:0 0 .6rem" }, tx("Aus config/fragen.json. Die Frage wird sofort an den KI-Anbieter geschickt und kostet eine Anfrage; sie bezieht sich auf die Auswahl im Filter.", "From config/fragen.json. The question is sent to the AI provider at once and costs one request; it refers to the selection in the filter.")),
      h("ol", { class: "kipresets" }, (DATA.aiPresetQuestions || []).map(q => { const text = tx(q.de, q.en) || q.de;
        return h("li", {}, h("button", { type: "button", class: "kipreset", onclick: () => { close(); onPick(text); } }, text)); })),
      h("div", { class: "row", style: "justify-content:flex-end;margin-top:.8rem" }, h("button", { type: "button", class: "btn", onclick: close }, tx("Abbrechen", "Cancel"))));
    if (d.showModal && !d.open) d.showModal(); else d.setAttribute("open", "");
  }
  // Eine gespeicherte Frage als reiner Text für Jira, Mail oder Teams: Frage, Antwort, Einordnung, Belege
  const CONF_TEXT = { sicher: ["sichere Aussage", "reliable"], hinweis: ["Hinweis: wenig Belege", "indication: few sources"], unklar: ["unklar", "unclear"] };
  function questionText(q) {
    const c = CONF_TEXT[q.confidence] || CONF_TEXT.unklar, scope = q.scope && q.scope.label ? q.scope.label : [q.scope && q.scope.app, q.scope && q.scope.customer, q.scope && q.scope.platform].filter(Boolean).join(" · ");
    const lines = [q.question, "", q.answer || tx("(keine Antwort)", "(no answer)"), "",
      tx(c[0], c[1]) + " · " + fmtInt(q.reviewCount || 0) + (q.availableCount && q.availableCount > q.reviewCount ? tx(" von ", " of ") + fmtInt(q.availableCount) : "") + tx(" Rezensionen gelesen", " reviews read")
        + (scope ? tx(" · Auswahl: ", " · selection: ") + scope : "") + (q.provider ? " · " + q.provider + (q.model ? "/" + q.model : "") : "") + (q.askedAt ? " · " + fmtDate(q.askedAt) : "") + tx(" · KI-Antwort", " · AI answer")];
    if ((q.quotes || []).length) { lines.push("", tx("Belege:", "Evidence:")); for (const x of q.quotes) lines.push("• „" + x.text + "“ (" + (x.rating ? "★ " + x.rating + " · " : "") + fmtDate(x.createdAt) + (x.appName ? " · " + x.appName : "") + ")"); }
    return lines.join("\n");
  }
  // KI-Anfragen als Druckbericht: jede gespeicherte Frage mit Antwort, Einordnung und Belegen (nur mit KI und vorhandenen Fragen)
  function buildQuestionsReport(opts) {
    const qs = (DATA.aiQuestions || []).slice().reverse();
    return [opts && opts.all ? null : h("div", { class: "pr-head" }, h("div", { class: "pr-k" }, tx("KI-Anfragen", "AI questions")), h("h1", {}, tx("Fragen an die Daten (KI)", "Questions to the data (AI)"))),
      qs.map(q => { const c = CONF_TEXT[q.confidence] || CONF_TEXT.unklar;
        return h("div", { class: "pr-q" }, h("h2", {}, q.question), h("p", {}, q.answer || tx("(keine Antwort)", "(no answer)")),
          h("p", { class: "muted" }, tx(c[0], c[1]) + " · " + fmtInt(q.reviewCount || 0) + tx(" Rezensionen gelesen", " reviews read") + (q.scope && q.scope.label ? tx(" · Auswahl: ", " · selection: ") + q.scope.label : "") + (q.provider ? " · " + q.provider + (q.model ? "/" + q.model : "") : "") + (q.askedAt ? " · " + fmtDate(q.askedAt) : ""), " ", kiMark()),
          (q.quotes || []).length ? h("ul", {}, q.quotes.map(x => h("li", {}, "„" + x.text + "“ (" + (x.rating ? "★ " + x.rating + " · " : "") + fmtDate(x.createdAt) + (x.appName ? " · " + x.appName : "") + ")"))) : null); }),
      h("div", { class: "pr-foot" }, tx("Antworten eines Sprachmodells zu den jeweils gefilterten Rezensionen; Zahlen stammen aus den Daten. Datenstand ", "Answers of a language model to the reviews filtered at the time; figures come from the data. Data as of ") + fmtDate(DATA.dataAsOf || "") + ".")];
  }
  function renderKiQuestions() {
    const box = $("kifrout"); box.replaceChildren();
    const qs = (DATA.aiQuestions || []).slice().reverse();
    const conf = { sicher: ["sichere Aussage", "reliable", "g"], hinweis: ["Hinweis: wenig Belege", "indication: few sources", "y"], unklar: ["unklar", "unclear", "n"] };
    if (svcState === "up") put(box, askForm());
    else if (svcState === "down") put(box, h("div", { class: "warn" }, tx("Der Bericht wurde erzeugt, während der lokale Fragedienst lief; jetzt antwortet er nicht. Neu starten mit ./ratings.sh ai-serve oder den Bericht neu erzeugen.", "The report was generated while the local question service was running; it does not respond now. Restart with ./ratings.sh ai-serve or rebuild the report.")));
    if (!qs.length) put(box, h("div", { class: "muted" }, svcState === "up" ? tx("Noch keine Fragen gestellt.", "No questions asked yet.") : tx("Noch keine Fragen gestellt. Fragen stellt man in der Kommandozeile oder im Menü: ./ratings.sh ask \"Welche Apps erwähnen das Bonusprogramm?\" (nur mit ai.features.questions = true; jede Frage kostet eine Anfrage). Direkt hier geht es, wenn der lokale Fragedienst läuft (./ratings.sh ai-report, Menü Punkt 5).", "No questions asked yet. Ask from the command line or the menu: ./ratings.sh ask \"Which apps mention the bonus programme?\" (only with ai.features.questions = true; each question costs one request). Asking right here works when the local question service is running (./ratings.sh ai-report, menu item 5).")));
    else put(box, h("div", { class: "ovcards", style: "grid-template-columns:1fr" }, qs.slice(0, showAllQuestions ? qs.length : QUESTIONS_SHOWN).map(q => { const c = conf[q.confidence] || conf.unklar;
      return h("div", { class: "ovcard" }, h("div", { class: "row", style: "justify-content:space-between;align-items:flex-start;gap:.6rem" }, h("h3", { style: "flex:1 1 auto" }, h("b", { style: "color:var(--fg)" }, q.question)),
          h("span", { class: "row", style: "gap:.8rem;flex:none" }, copyTextButton(() => questionText(q)),
            svcState === "up" ? h("button", { type: "button", class: "linkbtn", style: "margin-top:0;color:var(--bad)", onclick: () => { if (q._del) return; q._del = true; deleteQuestion(q, err => { svcError = err; renderKiQuestions(); }); } }, tx("Löschen", "Delete")) : null)),
        h("p", {}, q.answer || tx("(keine Antwort)", "(no answer)")),
        h("div", { class: "row", style: "gap:.5rem" }, h("i", { class: "dot " + c[2] }), tx(c[0], c[1]), kiMark(), h("span", { class: "muted" }, fmtInt(q.reviewCount) + (q.availableCount && q.availableCount > q.reviewCount ? tx(" von ", " of ") + fmtInt(q.availableCount) : "") + tx(" Rezensionen gelesen · ", " reviews read · ") + fmtDate(q.askedAt) + " · " + (q.provider || "") + "/" + (q.model || "")
          + (q.scope && q.scope.label ? tx(" · Auswahl: ", " · selection: ") + q.scope.label : q.scope && (q.scope.customer || q.scope.app || q.scope.platform) ? tx(" · Auswahl: ", " · selection: ") + [q.scope.app, q.scope.customer, q.scope.platform].filter(Boolean).join(" · ") : ""))),
        (q.quotes || []).length ? h("div", { class: "kiquotes" }, q.quotes.map(quoteRow)) : null); })),
      qs.length > QUESTIONS_SHOWN ? h("div", { class: "row", style: "margin-top:.6rem" }, h("button", { type: "button", class: "btn", onclick: () => { showAllQuestions = !showAllQuestions; renderKiQuestions(); } },
        showAllQuestions ? tx("Nur die neuesten 10 zeigen", "Show only the latest 10") : tx("Alle " + fmtInt(qs.length) + " Fragen zeigen", "Show all " + fmtInt(qs.length) + " questions"))) : null,
      h("div", { class: "note" }, tx("Neueste zuerst. Gespeichert werden höchstens 100 Fragen, die ältesten fallen weg. Löschen: hier bei laufendem Fragedienst oder ./ratings.sh ai-questions --delete NR.", "Newest first. At most 100 questions are kept, the oldest drop off. Delete: here while the question service runs, or ./ratings.sh ai-questions --delete NR.")));
    if (svcError && svcState === "up" && !asking && !$("kiq")) put(box, h("div", { class: "warn" }, svcError));
    const u = DATA.aiUsage || {}, months = Object.entries(u.months || {}).sort(), last = months[months.length - 1];
    if (last) {
      const cost = typeof last[1].costUsd === "number" ? fmt(last[1].costUsd, 2) + " $" + (last[1].unpricedRequests ? " (+?)" : "") : null;
      put(box, h("div", { class: "note" }, tx("Verbrauch " + fmtMonth(last[0]) + ": ", "Usage " + fmtMonth(last[0]) + ": ") + fmtInt(last[1].requests) + tx(" Anfragen, ", " requests, ") + fmtInt(last[1].inputTokens + last[1].outputTokens) + tx(" Tokens von ", " tokens of ") + fmtInt(u.monthlyTokenLimit || 0) + tx(" (Monatslimit)", " (monthly limit)")
        + (cost ? tx(", geschätzte Kosten " + cost + " (Tokens × Listenpreis, ohne Gewähr)", ", estimated cost " + cost + " (tokens × list price, no guarantee)") : "") + tx(". Je Kasse/App und alle Monate: ./ratings.sh ai-usage.", ". Per app and all months: ./ratings.sh ai-usage.")));
    }
  }

  // Reiter „KI-Anfragen“ (Karte „Fragen an die Daten“): nur mit KI und eingeschalteter Funktion (ai.features.questions)
  function renderKi() { if (featOn("questions")) renderKiQuestions(); }
