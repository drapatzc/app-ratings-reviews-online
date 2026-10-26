  // Filterkarte: Steuerelemente, Mehrfachauswahl Kunde/App, „Erweitert“, Kärtchen.
  // ---- Filter-Steuerelemente ----
  const filterDefs = [
    ["customerId", tx("Kunde", "Customer"), r => r.customerId, id => (DATA.apps.find(a => a.customerId === id) || {}).customerName || id],
    ["appKey", "App", r => r.customerId + "/" + r.appId, k => { const a = DATA.apps.find(x => x.customerId + "/" + x.appId === k); return a ? a.appName : k; }],
    ["platform", tx("Plattform", "Platform"), r => r.platform, platName],
    ["language", tx("Sprache", "Language"), r => fieldValue(r, "language"), v => v],
    ["country", tx("Land", "Country"), r => fieldValue(r, "country"), v => v],
    ["appVersion", tx("App-Version", "App version"), r => fieldValue(r, "appVersion"), v => v],
    ["osLabel", tx("Betriebssystem", "Operating system"), r => fieldValue(r, "osLabel"), v => v],
    ["device", tx("Gerätemodell", "Device model"), r => fieldValue(r, "device"), v => v],
  ];
  // Filter in zwei Gruppen: Grundfilter (immer sichtbar, ohne Überschrift) und „Erweitert“ (aufklappbar). Zugeklappt zeigt der Knopf die Zahl
  // gesetzter erweiterter Filter; die Kärtchen darunter nennen weiterhin alle gesetzten Filter.
  const BASIC = ["customerId", "appKey", "platform", "period", "q"];
  const fbox = $("filters"), advBox = $("filtersadv"), controls = [];
  const place = (key, el) => (BASIC.includes(key) ? fbox : advBox).append(el);
  function register(label, active, clear, items, key) { controls.push({ label, active, clear, items, key, adv: !!key && !BASIC.includes(key) }); }
  function onChange() { state.page = 0; render(); }
  function selectFilter(key, label, options) {
    const sel = h("select", { id: "f_" + key }, h("option", { value: "" }, tx("Alle", "All")), options.map(([v, l]) => h("option", { value: v }, v === NONE ? tx("(unbekannt)", "(unknown)") : l)));
    sel.addEventListener("change", () => { state.f[key] = sel.value; onChange(); });
    place(key, h("label", {}, label, sel));
    register(label, () => { if (!sel.value) return ""; const o = options.find(x => String(x[0]) === sel.value); return o ? (o[0] === NONE ? tx("(unbekannt)", "(unknown)") : o[1]) : sel.value; }, () => { sel.value = ""; state.f[key] = ""; }, null, key);
    return sel;
  }
  // Kunde und App: Mehrfachauswahl (Liste mit Häkchen), Optionen aus allen konfigurierten Apps, nicht nur aus Rezensionen.
  // Die Auswahl bleibt im localStorage („filterSel“), damit sie für Präsentationen erhalten bleibt.
  const MULTI = ["customerId", "appKey"], mselBoxes = [];
  const saveSel = () => { try { localStorage.setItem("filterSel", JSON.stringify({ customerId: state.f.customerId || [], appKey: state.f.appKey || [] })); } catch (e) {} };
  function multiFilter(key, label, options, unit) {
    const name = v => (options.find(o => o[0] === v) || [v, v])[1], sel = () => state.f[key] || [];
    const sum = h("summary", { class: "mselbtn" }), box = h("details", { class: "msel", id: "f_" + key }), list = h("div", { class: "msellist", role: "group", "aria-label": label });
    const rows = options.map(([v, l]) => { const cb = h("input", { type: "checkbox", value: v });
      cb.addEventListener("change", () => update(cb.checked ? sel().concat([v]) : sel().filter(x => x !== v))); return { v, l, cb, row: h("label", { class: "mselrow" }, cb, l) }; });
    function paint() { const s = sel(); rows.forEach(r => { r.cb.checked = s.includes(r.v); }); sum.textContent = !s.length ? tx("Alle", "All") : s.length === 1 ? name(s[0]) : s.length + " " + unit; }
    function update(next) { state.f[key] = next; saveSel(); paint(); onChange(); }
    const all = h("button", { type: "button", class: "btn", onclick: () => update([]) }, tx("Alle (Auswahl aufheben)", "All (clear selection)"));
    const search = options.length > 8 ? h("input", { type: "search", placeholder: tx("Suchen …", "Search …"), "aria-label": label + tx(" durchsuchen", " search") }) : null;
    if (search) search.addEventListener("input", () => { const q = search.value.trim().toLowerCase(); rows.forEach(r => { r.row.style.display = !q || r.l.toLowerCase().includes(q) ? "" : "none"; }); });
    list.append(h("div", { class: "row", style: "gap:.4rem;margin-bottom:.3rem" }, all, search), ...rows.map(r => r.row));
    put(box, sum, list); mselBoxes.push(box);
    place(key, h("div", { class: "mlabel" }, h("span", {}, label), box));
    register(label, () => "", () => { state.f[key] = []; paint(); }, () => sel().map(v => ({ text: name(v), remove: () => update(sel().filter(x => x !== v)) })), key);
    return paint;
  }
  const appsByKey = new Map(DATA.apps.map(a => [a.customerId + "/" + a.appId, a])), custIds = [...new Set(DATA.apps.map(a => a.customerId))];
  const custOptions = custIds.map(id => [id, (DATA.apps.find(a => a.customerId === id) || {}).customerName || id]).sort((a, b) => a[1].localeCompare(b[1], LANG));
  // Wettbewerber stehen mit Präfix in der Liste; sie zählen nur, wenn sie hier ausdrücklich gewählt werden (core.js rivalHidden)
  const appOptions = [...appsByKey.entries()].map(([k, a]) => [k, (a.competitor ? tx("Wettbewerber: ", "Competitor: ") : "") + (custIds.length > 1 ? a.appName + " · " + a.customerName : a.appName)]).sort((a, b) => a[1].localeCompare(b[1], LANG, { numeric: true }));
  try { const v = JSON.parse(localStorage.getItem("filterSel") || "null"); if (v) {
    state.f.customerId = (v.customerId || []).filter(id => custIds.includes(id)); state.f.appKey = (v.appKey || []).filter(k => appsByKey.has(k)); } } catch (e) {}
  const paintMulti = [multiFilter("customerId", tx("Kunde", "Customer"), custOptions, tx("Kunden", "customers")), multiFilter("appKey", "App", appOptions, "Apps")];
  paintMulti.forEach(p => p());
  // Eine einzelne App wählen (Klick auf eine Zeile der Ampeltabelle im Überblick)
  function selectApp(key) { state.f.appKey = [key]; state.f.customerId = []; saveSel(); paintMulti.forEach(p => p()); onChange(); }
  if (document.addEventListener) {
    document.addEventListener("click", e => mselBoxes.forEach(b => { if (b.open && b.contains && !b.contains(e.target)) b.open = false; }));
    document.addEventListener("keydown", e => { if (e.key === "Escape") mselBoxes.forEach(b => { b.open = false; }); });
  }
  for (const [key, label, getter, labeler] of filterDefs) {
    if (MULTI.includes(key)) continue;
    const values = [...new Set(reviews.map(getter))].sort((a, b) => a === NONE ? 1 : b === NONE ? -1 : String(labeler(a)).localeCompare(String(labeler(b)), LANG, { numeric: true }));
    selectFilter(key, label, values.map(v => [v, labeler(v)]));
  }
  // Thema (aus config/themen.json); wirkt wie jeder Filter auf alle Reiter. Der Klick auf einen Themenbalken setzt ihn nicht.
  if (TOPICS.length) selectFilter("topic", tx("Thema", "Topic"), TOPICS.map(t => [t.id, tx(t.de, t.en)]));
  // Stimmung und Dringlichkeit der KI (nur, wenn Analysen vorliegen); Beschriftungen wie in ki.js
  if (DATA.ai && DATA.ai.length) {
    selectFilter("aiSentiment", tx("Stimmung (KI)", "Sentiment (AI)"), [["begeistert", tx("Begeistert", "Delighted")], ["zufrieden", tx("Zufrieden", "Satisfied")], ["wunsch", tx("Wunsch / Vorschlag", "Wish / suggestion")], ["veraergert", tx("Verärgert", "Annoyed")], ["resigniert", tx("Resigniert (droht Wechsel)", "Resigned (threatens to leave)")], ["unklar", tx("Unklar", "Unclear")]]);
    selectFilter("aiUrgency", tx("Dringlichkeit (KI)", "Urgency (AI)"), [["hoch", tx("hoch", "high")], ["mittel", tx("mittel", "medium")], ["niedrig", tx("niedrig", "low")]]);
  }
  for (const [key, label] of [["ratingMin", tx("Sterne von", "Stars from")], ["ratingMax", tx("Sterne bis", "Stars to")]]) {
    const sel = selectFilter(key, label, [1, 2, 3, 4, 5].map(n => [n, n + " ★"]));
    sel.addEventListener("change", () => { state.f[key] = Number(sel.value) || ""; });
  }
  const asOfDate = (DATA.dataAsOf || new Date().toISOString()).slice(0, 10);
  function daysBefore(d, n) { const t = new Date(d + "T00:00:00Z"); t.setUTCDate(t.getUTCDate() - n); return t.toISOString().slice(0, 10); }
  const period = h("select", { id: "f_period" }, [["", tx("Gesamter Zeitraum", "Entire period")], ["30", tx("Letzte 30 Tage", "Last 30 days")], ["90", tx("Letzte 90 Tage", "Last 90 days")], ["365", tx("Letzte 365 Tage", "Last 365 days")], ["custom", tx("Benutzerdefiniert", "Custom")]].map(([v, l]) => h("option", { value: v }, l)));
  const from = h("input", { type: "date", id: "f_from" }), to = h("input", { type: "date", id: "f_to" });
  period.addEventListener("change", () => {
    if (period.value === "") { state.f.from = state.f.to = ""; from.value = to.value = ""; }
    else if (period.value !== "custom") { state.f.from = daysBefore(asOfDate, Number(period.value)); state.f.to = ""; from.value = state.f.from; to.value = ""; }
    onChange();
  });
  from.addEventListener("change", () => { state.f.from = from.value; period.value = "custom"; onChange(); });
  to.addEventListener("change", () => { state.f.to = to.value; period.value = "custom"; onChange(); });
  place("period", h("label", {}, tx("Zeitraum", "Period"), period));
  register(tx("Zeitraum", "Period"), () => (state.f.from || state.f.to) ? (state.f.from ? fmtDay(state.f.from) : "…") + tx(" bis ", " to ") + (state.f.to ? fmtDay(state.f.to) : tx("heute", "today")) : "", () => { state.f.from = state.f.to = ""; from.value = to.value = period.value = ""; }, null, "period");
  const reply = h("select", { id: "f_reply" }, [["all", tx("Alle", "All")], ["with", tx("Mit Entwicklerantwort", "With developer reply")], ["without", tx("Ohne Entwicklerantwort", "Without developer reply")]].map(([v, l]) => h("option", { value: v }, l)));
  reply.addEventListener("change", () => { state.f.reply = reply.value; onChange(); });
  register(tx("Antwort", "Reply"), () => reply.value === "with" ? tx("mit Antwort", "with reply") : reply.value === "without" ? tx("ohne Antwort", "without reply") : "", () => { reply.value = "all"; state.f.reply = "all"; }, null, "reply");
  const textOnly = h("input", { type: "checkbox", id: "f_text" });
  textOnly.addEventListener("change", () => { state.f.textOnly = textOnly.checked; onChange(); });
  register(tx("Text", "Text"), () => textOnly.checked ? tx("nur mit Text", "with text only") : "", () => { textOnly.checked = false; state.f.textOnly = false; }, null, "textOnly");
  const q = h("input", { type: "search", id: "f_q", placeholder: tx("Suchen …", "Search …") });
  let timer = null;
  q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.f.q = q.value.trim(); onChange(); }, 200); });
  register(tx("Suche", "Search"), () => q.value.trim() ? (LANG === "de" ? "„" + q.value.trim() + "“" : "“" + q.value.trim() + "”") : "", () => { q.value = ""; state.f.q = ""; }, null, "q");
  place("reply", h("label", {}, tx("Entwicklerantwort", "Developer reply"), reply)); place("from", h("label", {}, tx("Von", "From"), from));
  place("to", h("label", {}, tx("Bis", "To"), to)); place("textOnly", h("label", {}, tx("Nur mit Text", "Text only"), textOnly));
  place("q", h("label", {}, tx("Freitextsuche", "Full-text search"), q));
  // Von/Bis stehen unter „Erweitert“: als gesetzt zählen sie nur bei „Benutzerdefiniert“, sonst gehört das Datum zum Zeitraum
  register(tx("Von/Bis", "From/to"), () => "", () => {}, null, "from");
  controls[controls.length - 1].count = () => period.value === "custom" && (state.f.from || state.f.to) ? 1 : 0;
  let advOpen = false; try { advOpen = localStorage.getItem("filterAdv") === "1"; } catch (e) {}
  function setAdv(open) { advOpen = open; advBox.hidden = !open; $("advbtn").setAttribute("aria-expanded", String(open)); $("advcaret").textContent = open ? "▾" : "▸";
    try { localStorage.setItem("filterAdv", open ? "1" : "0"); } catch (e) {} }
  $("advbtn").addEventListener("click", () => setAdv(!advOpen));
  period.addEventListener("change", () => { if (period.value === "custom" && !advOpen) setAdv(true); });
  setAdv(advOpen);
  function paintAdv() {
    const n = controls.filter(c => c.adv).reduce((s, c) => s + (c.count ? c.count() : c.items ? c.items().length : c.active() ? 1 : 0), 0);
    const b = $("advcount"); b.hidden = !n; b.textContent = String(n);
    $("advbtn").className = "advbtn" + (n ? " has" : "");
    $("advbtn").setAttribute("title", n ? tx(n + " erweiterte Filter gesetzt", n + " advanced filters set") : tx("Weitere Filter einblenden", "Show more filters"));
  }
  function renderChips() {
    paintAdv();
    const chips = $("chips"); chips.replaceChildren();
    const chip = (text, label, remove) => h("span", { class: "chip" }, text, h("button", { type: "button", "aria-label": label + tx(" entfernen", " remove"), onclick: remove }, "×"));
    controls.forEach(c => { if (c.items) { c.items().forEach(it => chips.append(chip(c.label + ": " + it.text, it.text, it.remove))); return; }
      const v = c.active(); if (v) chips.append(h("span", { class: "chip" }, c.label + ": " + v, h("button", { type: "button", "aria-label": c.label + tx(" entfernen", " remove"), onclick: () => { c.clear(); onChange(); } }, "×"))); });
  }
  // Eingestellter Filter als Liste für die Druckberichte (Wunsch des Nutzers: Randparameter jeder Auswertung ganz oben).
  // Kunde, App, Plattform und Zeitraum stehen immer da (ohne Auswahl „alle“ bzw. „gesamter Zeitraum“), alle anderen nur, wenn gesetzt.
  function filterSummary() {
    const always = { customerId: tx("alle", "all"), appKey: tx("alle", "all"), platform: tx("alle", "all"), period: tx("gesamter Zeitraum", "entire period") };
    const order = ["customerId", "appKey", "platform", "period", "q"], rank = c => { const i = order.indexOf(c.key); return i < 0 ? order.length : i; };
    const out = [];
    for (const c of controls.slice().sort((a, b) => rank(a) - rank(b))) {
      const v = c.items ? c.items().map(i => i.text).join(", ") : c.active();
      if (v) out.push({ label: c.label, value: v }); else if (c.key in always) out.push({ label: c.label, value: always[c.key] });
    }
    return out;
  }
  const resetFilters = () => { controls.forEach(c => c.clear()); state.f = {}; saveSel(); onChange(); };
  $("reset").addEventListener("click", resetFilters);
  // „Zurücksetzen“ (Wunsch des Nutzers, 25.10.2026): nach Sicherheitsabfrage Filter leeren und alle gespeicherten KI-Fragen löschen.
  // Löschen auf der Platte geht nur über den laufenden Fragedienst (deleteQuestion in ki.js); sonst bleibt eine Meldung stehen.
  $("resetall").addEventListener("click", () => confirmDialog(tx("Wollen Sie alle Eingaben löschen?", "Do you want to delete all entries?"),
    tx("Der Filter wird geleert und alle gespeicherten KI-Anfragen werden gelöscht.", "The filter is cleared and all stored AI questions are deleted."), () => {
      resetFilters();
      const qs = (DATA.aiQuestions || []).slice();
      if (!qs.length) return;
      if (typeof svcState === "undefined" || svcState !== "up") { svcError = tx("Die gespeicherten KI-Anfragen konnten nicht gelöscht werden: Der Fragedienst läuft nicht. Löschen: ./ratings.sh ai-serve starten und erneut zurücksetzen, oder ./ratings.sh ai-questions --delete NR.", "The stored AI questions could not be deleted: the question service is not running. Delete: start ./ratings.sh ai-serve and reset again, or ./ratings.sh ai-questions --delete NR."); renderKiQuestions(); return; }
      let i = 0; const next = err => { if (err) { svcError = err; renderKiQuestions(); return; } if (i >= qs.length) { svcError = null; renderKiQuestions(); return; } deleteQuestion(qs[i++], next); };
      next(null);
    }));

