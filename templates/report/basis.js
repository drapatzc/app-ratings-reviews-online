  // Grundgerüst im Bericht-IIFE: Hilfsfunktionen (h, put, fmt), Zustand, Theme, Sprache, Tooltip, Grafikbausteine.
  if (!DATA) return;
  const $ = id => document.getElementById(id);
  const reduce = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) || /static/.test((location.search || "") + (location.hash || ""));
  // Fügt Kinder ein und überspringt null/undefined/false; das native append() würde sie als Text „null“ anzeigen
  const put = (el, ...kids) => el.append(...kids.flat(Infinity).filter(k => k !== null && k !== undefined && k !== false));
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
    }
    for (const kid of kids.flat(Infinity)) if (kid !== null && kid !== undefined) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return e;
  }
  const SVG = "http://www.w3.org/2000/svg";
  function s(tag, attrs, text) { const e = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); if (text !== undefined) e.textContent = text; return e; }
  const locale = () => LANG === "de" ? "de-DE" : "en-GB";
  const fmt = (n, d = 2) => n === null || n === undefined ? "–" : n.toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d });
  const fmtInt = n => n.toLocaleString(locale());
  // Datum und Uhrzeit für den DACH-Raum: „21.10.2026“ bzw. „21.10.2026, 14:33 Uhr“ in der Ortszeit des Browsers (gespeichert
  // ist UTC). Englisch bleibt beim ISO-Schema ohne Sekunden. Reine Tagesangaben (JJJJ-MM-TT) werden nicht umgerechnet.
  const pad2 = n => String(n).padStart(2, "0");
  const fmtDay = d => !d ? "–" : LANG === "de" ? d.slice(8, 10) + "." + d.slice(5, 7) + "." + d.slice(0, 4) : d.slice(0, 10);
  const fmtMonth = m => LANG === "de" ? m.slice(5, 7) + "." + m.slice(0, 4) : m;
  const fmtMonthShort = m => LANG === "de" ? m.slice(5, 7) + "." + m.slice(2, 4) : m.slice(2);
  const fmtDate = v => { if (!v) return "–"; if (v.length <= 10) return fmtDay(v);
    const t = Date.parse(v); if (isNaN(t)) return v.replace("T", " ").replace("Z", "");
    const d = new Date(t), hm = pad2(d.getHours()) + ":" + pad2(d.getMinutes());
    return LANG === "de" ? pad2(d.getDate()) + "." + pad2(d.getMonth() + 1) + "." + d.getFullYear() + ", " + hm + " Uhr"
      : d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) + " " + hm; };
  // Sortierung wird nur für diese Browser-Sitzung gemerkt (sessionStorage; ohne Zugriff funktioniert alles weiter).
  const SS = {
    get(k) { try { return JSON.parse(sessionStorage.getItem("arr:" + k)); } catch (e) { return null; } },
    set(k, v) { try { sessionStorage.setItem("arr:" + k, JSON.stringify(v)); } catch (e) { /* ignorieren */ } }
  };
  // Macht eine fertig aufgebaute Tabelle (thead, tbody) per Klick auf die Spaltenköpfe auf-/absteigend sortierbar.
  function sortable(tbl, key) {
    const thead = tbl.children[0], tbody = tbl.children[1];
    if (!thead || !tbody || !thead.children[0]) return;
    const ths = Array.from(thead.children[0].children), rows = Array.from(tbody.children);
    const cell = (tr, i) => { const c = tr.children[i]; return c ? String(c.textContent || "").trim() : ""; };
    // Datum als ISO (JJJJ-MM-TT …) oder deutsch (TT.MM.JJJJ[, HH:MM Uhr]) → vergleichbarer Schlüssel JJJJ-MM-TT HH:MM
    const dateKey = v => { let m = /^(\d{4}-\d{2}-\d{2})/.exec(v); if (m) return v.replace("T", " ");
      m = /^(\d{2})\.(\d{2})\.(\d{4})(?:, (\d{2}:\d{2}))?/.exec(v); return m ? m[3] + "-" + m[2] + "-" + m[1] + " " + (m[4] || "") : null; };
    const isDate = v => dateKey(v) !== null;
    const num = v => { const m = /^-?\d[\d.,]*/.exec(v); if (!m) return null; return parseFloat(LANG === "de" ? m[0].replace(/\./g, "").replace(",", ".") : m[0].replace(/,/g, "")); };
    const empty = v => v === "" || v === "–";
    const cmp = (a, b) => { if (isDate(a) && isDate(b)) { const p = dateKey(a), q = dateKey(b); return p < q ? -1 : p > q ? 1 : 0; } const x = num(a), y = num(b); if (x !== null && y !== null) return x - y; return a.localeCompare(b, LANG, { numeric: true }); };
    let cur = SS.get("sort:" + key);
    function apply(i, dir) {
      const sorted = rows.slice().sort((r1, r2) => { const a = cell(r1, i), b = cell(r2, i); if (empty(a) || empty(b)) return empty(a) && empty(b) ? 0 : empty(a) ? 1 : -1; return dir * cmp(a, b); });
      tbody.replaceChildren(...sorted);
      ths.forEach((th, j) => { if (j === i) th.setAttribute("aria-sort", dir > 0 ? "ascending" : "descending"); else th.removeAttribute("aria-sort"); });
    }
    ths.forEach((th, i) => {
      th.setAttribute("data-sortable", "1"); th.setAttribute("tabindex", "0");
      const go = () => { const dir = cur && cur.i === i ? -cur.dir : 1; cur = { i, dir }; SS.set("sort:" + key, cur); apply(i, dir); };
      th.addEventListener("click", go); th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
    if (cur && cur.i < ths.length && (cur.dir === 1 || cur.dir === -1)) apply(cur.i, cur.dir);
  }
  function sortTables(root, prefix) { root.querySelectorAll("table").forEach((t, n) => sortable(t, prefix + n)); }
  const state = { f: {}, sort: SS.get("sort:rez") || { key: "createdAt", dir: -1 }, page: 0, pageSize: 25 };
  const SMALL = 30;
  const COL = { good: "var(--good)", mid: "var(--mid)", bad: "var(--bad)" };
  const platName = p => p === "apple" ? "Apple" : "Google";
  let uid = 0;

  // ---- Theme ----
  try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
  const flags = (location.search || "") + (location.hash || "");
  // ---- Sprache: DE/EN oben rechts; Wahl im localStorage ("lang"), Wechsel lädt die Seite neu ----
  let LANG = "de"; try { LANG = localStorage.getItem("lang") || LANG; } catch (e) {}
  if (/\blang=en\b/.test(flags)) LANG = "en"; if (/\blang=de\b/.test(flags)) LANG = "de";
  if (LANG !== "en") LANG = "de";
  document.documentElement.lang = LANG;
  const tx = (de, en) => LANG === "de" ? de : en;
  document.querySelectorAll("#langs button").forEach(b => {
    b.setAttribute("aria-pressed", String(b.dataset.lang === LANG));
    b.addEventListener("click", () => { if (b.dataset.lang === LANG) return; try { localStorage.setItem("lang", b.dataset.lang); } catch (e) {} location.reload(); });
  });
  for (const [id, de, en] of [["theme", "Farbschema wechseln", "Switch light/dark"], ["tabs", "Bereiche", "Sections"], ["modeseg", "Datenquelle", "Data source"], ["hero-score", "Gesamtbewertung", "Overall rating"], ["kpis", "Kennzahlen", "Key figures"], ["detail", "Details zur Rezension", "Review details"], ["chartdlg", "Diagramm vergrößert", "Enlarged chart"]])
    $(id).setAttribute("aria-label", tx(de, en));
  $("theme").setAttribute("title", tx("Hell / Dunkel", "Light / dark"));
  if (/dark/.test(flags)) document.documentElement.dataset.theme = "dark";
  if (/light/.test(flags)) document.documentElement.dataset.theme = "light";
  if (!document.documentElement.dataset.theme && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) document.documentElement.dataset.theme = "dark";
  $("theme").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (e) {}
  });

  // ---- Tooltip, Balken ----
  const tip = $("tip");
  if (document.addEventListener) {
    // Erste Zeile fett, wenn data-tip einen Zeilenumbruch enthält; auf Touch-Geräten erscheint der Tooltip beim Antippen.
    const place = e => { tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 270) + "px"; tip.style.top = (e.clientY + 16) + "px"; };
    const showTip = e => {
      const t = e.target && e.target.closest ? e.target.closest("[data-tip]") : null;
      if (!t) { tip.className = ""; return; }
      const [first, ...rest] = t.getAttribute("data-tip").split("\n");
      if (rest.length) tip.replaceChildren(h("b", {}, first), rest.join(" ")); else tip.textContent = first;
      tip.className = "on";
    };
    document.addEventListener("mouseover", showTip);
    document.addEventListener("pointerdown", e => { if (e.pointerType && e.pointerType !== "mouse") { showTip(e); place(e); } });
    document.addEventListener("mousemove", e => { if (tip.className === "on") place(e); });
  }
  function grow(el, pct) { // Balken kurz einlaufen lassen (aus bei „Bewegung reduzieren“ oder ?static)
    if (reduce || typeof requestAnimationFrame === "undefined") { el.style.width = pct + "%"; return; }
    requestAnimationFrame(() => requestAnimationFrame(() => { el.style.width = pct + "%"; }));
  }

  TOPICS = (DATA.topics && DATA.topics.topics) || [];
  // KI-Ergebnisse je Rezension (DATA.ai, src/ai_analysis.py) als flache Felder, damit Filter, Sortierung und CSV sie wie andere Felder sehen
  const aiOf = new Map(), aiDraftOf = new Map();
  for (const doc of DATA.ai || []) { for (const [id, x] of Object.entries(doc.reviews || {})) aiOf.set(id, x); for (const [id, x] of Object.entries(doc.drafts || {})) aiDraftOf.set(id, x); }
  const reviews = DATA.reviews.map(r => { const ai = aiOf.get(r.id) || null; return Object.assign({ osLabel: fieldValue(r, "osLabel") === NONE ? null : fieldValue(r, "osLabel"), topics: tagTopics(r),
    aiSentiment: ai ? ai.sentiment : null, aiUrgency: ai ? ai.urgency : null, aiIssue: ai ? ai.issue : null, aiThemes: ai ? ai.themes || [] : [], aiMismatch: !!(ai && ai.mismatch), aiChurn: !!(ai && ai.churn), aiVersion: ai ? ai.version : null, aiDraft: aiDraftOf.get(r.id) || null }, r); });
  $("asof").textContent = tx("Datenstand ", "Data as of ") + fmtDate(DATA.dataAsOf);
  const sc = DATA.scope || {};
  if (sc.customer || sc.app || sc.platform) $("asof").textContent += tx(" · Auswahl: ", " · Selection: ") + [sc.appName || sc.app, sc.platform ? platName(sc.platform) : null, !sc.app ? sc.customer : null].filter(Boolean).join(" · ");
  (function lead() { // Kurzzeile: Apps, Kunden, Stores; die Zahl der Rezensionen steht im Reiter „Rezensionen“
    const own = DATA.apps.filter(a => !a.competitor), nRivals = new Set(DATA.apps.filter(a => a.competitor).map(a => a.customerId + "/" + a.appId)).size;
    const nApps = new Set(own.map(a => a.customerId + "/" + a.appId)).size, nCust = new Set(DATA.apps.map(a => a.customerId)).size, stores = [...new Set(own.map(a => a.platform))].sort().map(p => p === "apple" ? "App Store" : "Google Play");
    $("lead").textContent = nApps + (nApps === 1 ? " App · " : " Apps · ") + nCust + tx(nCust === 1 ? " Kunde · " : " Kunden · ", nCust === 1 ? " customer · " : " customers · ") + (stores.join(tx(" und ", " and ")) || "–")
      + (nRivals ? " · " + nRivals + tx(" Wettbewerber", nRivals === 1 ? " competitor" : " competitors") : "") + tx(" · offline, ohne Server, ohne Tracking", " · offline, no server, no tracking");
  })();

  // ---- Grafikbausteine ----
  function starsSvg(value, size) {
    const svg = s("svg", { viewBox: `0 0 ${size * 5 + 12} ${size}`, width: size * 5 + 12, height: size, role: "img", "aria-label": value === null ? tx("keine Bewertung", "no rating") : fmt(value) + tx(" von 5 Sternen", " out of 5 stars") });
    const defs = s("defs", {});
    for (let i = 0; i < 5; i++) {
      const id = "sg" + (++uid), frac = value === null ? 0 : Math.max(0, Math.min(1, value - i));
      const g = s("linearGradient", { id, x1: 0, x2: 1, y1: 0, y2: 0 });
      g.append(s("stop", { offset: frac, "stop-color": "#ffb02e" }), s("stop", { offset: frac, "stop-color": "currentColor", "stop-opacity": .18 }));
      defs.append(g);
      const star = s("path", { d: "M12 2.4l2.9 6.2 6.7.8-5 4.6 1.4 6.7L12 17.4 6 20.7l1.4-6.7-5-4.6 6.7-.8z", fill: `url(#${id})`, transform: `translate(${i * (size + 3)} 0) scale(${size / 24})` });
      svg.append(star);
    }
    svg.insertBefore(defs, svg.firstChild || null);
    return svg;
  }
  function ratingColor(n) { return n >= 4 ? COL.good : n === 3 ? COL.mid : COL.bad; }
  function distBars(st, big) {
    return h("div", { class: "bars short" }, [5, 4, 3, 2, 1].map(n => {
      const fill = h("div", { class: "fill" }); fill.style.background = ratingColor(n);
      grow(fill, st.rated ? 100 * st.dist[n] / st.rated : 0);
      return h("div", { class: "bar" + (big ? " big2" : ""), "data-tip": n + " ★: " + st.dist[n] + " (" + (st.rated ? fmt(100 * st.dist[n] / st.rated, 1) : "0") + " %)" },
        h("div", { class: "t" }, n + " ★"), h("div", { class: "track" }, fill), h("div", { class: "v" }, fmtInt(st.dist[n])));
    }));
  }
  function donut(st) {
    const R = 54, C = 2 * Math.PI * R, mid = st.rated - st.pos - st.neg;
    const svg = s("svg", { viewBox: "0 0 140 140", width: 170, height: 170, role: "img", "aria-label": tx("Anteil positiv, neutral, negativ", "Share positive, neutral, negative") });
    svg.append(s("circle", { cx: 70, cy: 70, r: R, fill: "none", stroke: "var(--line)", "stroke-width": 16 }));
    let acc = 0;
    [[st.pos, COL.good, tx("positiv (4–5 ★)", "positive (4–5 ★)")], [mid, COL.mid, tx("neutral (3 ★)", "neutral (3 ★)")], [st.neg, COL.bad, tx("negativ (1–2 ★)", "negative (1–2 ★)")]].forEach(([n, col, lab]) => {
      if (!n || !st.rated) return;
      const len = C * n / st.rated, gap = Math.min(3, len * 0.1);
      const c = s("circle", { cx: 70, cy: 70, r: R, fill: "none", stroke: col, "stroke-width": 16, "stroke-linecap": "round",
        "stroke-dasharray": `${Math.max(0, len - gap)} ${C - Math.max(0, len - gap)}`, "stroke-dashoffset": -acc, transform: "rotate(-90 70 70)", "data-tip": lab + ": " + n });
      svg.append(c); acc += len;
    });
    return svg;
  }

