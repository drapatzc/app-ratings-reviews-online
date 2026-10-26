  // Reiter „Wettbewerber“: eigene Apple-Apps und die Wettbewerber des gewählten Kunden nebeneinander (Tabelle, KI-Vergleich,
  // Steckbrief). Erscheint nur mit DATA.hasCompetitors (Wunsch des Nutzers, 25.10.2026); folgt dem Kunden- und Plattformfilter,
  // nicht der App-Auswahl, damit der Vergleich immer vollständig ist. Quelle der Wettbewerber: öffentlicher Apple-Feed (apple_public.py).
  function renderRivals() {
    const sec = $("wettbewerber"), box = $("rivout");
    if (!sec || !box) return;
    box.replaceChildren();
    if (!DATA.hasCompetitors) { sec.hidden = true; return; }
    sec.hidden = false;
    if (state.f.platform && state.f.platform !== "apple") { put(box, h("div", { class: "muted" }, tx("Wettbewerber gibt es nur für Apple (Google bietet keine öffentliche Quelle). Plattformfilter auf „Alle“ oder Apple stellen.", "Competitors exist for Apple only (Google offers no public source). Set the platform filter to “All” or Apple."))); return; }
    const apps = DATA.apps.filter(a => a.platform === "apple" && inSel(state.f.customerId, a.customerId));
    const own = apps.filter(a => !a.competitor), rivals = apps.filter(a => a.competitor);
    if (!rivals.length) { put(box, noData()); return; }
    const d90 = daysBefore(asOfDate, 90), multi = new Set(apps.map(a => a.customerId)).size > 1;
    const storeOf = a => { const snaps = new Map(); for (const x of DATA.ratings) if (x.origin === "store-official" && x.customerId === a.customerId && x.appId === a.appId && x.platform === "apple" && x.total > 0) { const c = snaps.get(x.country); if (!c || x.capturedAt > c.capturedAt) snaps.set(x.country, x); }
      return [...snaps.values()].sort((x, y) => y.total - x.total)[0] || null; };
    const rowOf = a => { const key = appKeyOf(a), rs = reviews.filter(r => appKeyOf(r) === key && r.platform === "apple" && (r.createdAt || "") >= d90), st = stats(rs), store = storeOf(a);
      const amp = (DATA.ampel || {})[key + "/apple"] || { level: 0, reasons: [] };
      return { a, key, st, store, amp, version: (a.profile && a.profile.version) || (store && store.appVersion) || null, vendor: a.vendor || null }; };
    const rows = own.map(rowOf).concat(rivals.map(rowOf));
    const head = ["", "App", multi ? tx("Kunde", "Customer") : null, tx("Hersteller", "Vendor"), tx("Store ★", "Store ★"), tx("Bewertungen gesamt", "Ratings total"), tx("Rezensionen (90 T.)", "Reviews (90 d)"), tx("Ø ★ (90 T.)", "Avg ★ (90 d)"), tx("Anteil 1–2 ★", "Share 1–2 ★"), "Version", tx("Warum", "Why")].filter(x => x !== null);
    const tr = r => h("tr", {}, h("td", { class: r.a.competitor ? "riv" : "own" }, dot(r.amp.level)),
      h("td", { class: "nw" }, h("b", {}, r.a.appName), rivalMark(r.a)), multi ? h("td", {}, r.a.customerName) : null,
      h("td", {}, r.vendor || (r.a.competitor ? "–" : tx("eigene App", "own app"))),
      r.store ? h("td", { class: "num", "data-tip": r.store.country + ": " + fmtInt(r.store.total) + tx(" Bewertungen", " ratings") }, fmt(r.store.average, 1)) : h("td", { class: "num muted" }, "–"),
      h("td", { class: "num" }, r.store ? fmtInt(r.store.total) : "–"), h("td", { class: "num" }, fmtInt(r.st.rated)),
      h("td", { class: "num" }, r.st.rated ? fmt(r.st.avg, 2) : "–"), h("td", { class: "num" }, r.st.negShare === null ? "–" : fmt(100 * r.st.negShare, 0) + " %"),
      h("td", { class: "num" }, r.version || "–"), h("td", { class: "why" }, r.amp.reasons.map(reasonText).join(" · ") || "–"));
    put(box, h("h3", { class: "sub3" }, tx("Eigene Apps und Wettbewerber im Vergleich", "Own apps and competitors compared")),
      h("div", { class: "tablewrap", style: "max-height:none" }, h("table", { class: "rivaltbl" }, h("thead", {}, h("tr", {}, head.map(t => h("th", {}, t)))), h("tbody", {}, rows.map(tr)))),
      h("div", { class: "note" }, tx("Eigene Apps (violetter Rand) aus App Store Connect, Wettbewerber (grauer Rand) aus dem öffentlichen Apple-Feed: nur die jüngsten 500 Rezensionen je Land, keine Entwicklerantworten, keine Abstürze und Downloads. Ampel nach denselben Regeln wie im Überblick; ohne Absturzdaten greifen bei Wettbewerbern nur die Rezensions- und Store-Regeln. Store ★ = offizielle Note im Land mit den meisten Bewertungen. 90 Tage ab Datenstand, unabhängig vom Zeitraum im Filter.",
        "Own apps (purple edge) from App Store Connect, competitors (grey edge) from Apple’s public feed: only the newest 500 reviews per country, no developer replies, no crashes or downloads. Traffic light by the same rules as in the overview; without crash data only the review and store rules apply to competitors. Store ★ = official rating in the country with the most ratings. 90 days from the data date, regardless of the period in the filter.")));
    // KI: was Nutzer loben und bemängeln, eigene Apps und Wettbewerber nebeneinander (nur mit Analysen und Funktion „summary“)
    const cards = rows.map(r => { const doc = aiDocOf(r.a), sm = doc && doc.summary; if (!sm || !sm.text || !featOn("summary")) return null;
      return h("div", { class: "rivalcard" }, h("h4", {}, r.a.appName, rivalMark(r.a), " ", kiMark()),
        sm.praise ? h("p", {}, h("b", {}, tx("Lob: ", "Praise: ")), sm.praise) : null, sm.criticism ? h("p", {}, h("b", {}, tx("Kritik: ", "Criticism: ")), sm.criticism) : null,
        h("p", { class: "muted" }, sm.text), h("p", { class: "note", style: "margin:0" }, (doc.provider || "?") + " · " + (doc.model || "?") + (sm.generatedAt ? " · " + fmtDate(sm.generatedAt) : ""))); }).filter(Boolean);
    if (cards.length) put(box, h("h3", { class: "sub3", style: "margin-top:1.4rem" }, tx("Was die Nutzer sagen (KI)", "What users say (AI)")), h("div", { class: "rivalgrid" }, cards));
    // Steckbrief je Wettbewerber aus dem iTunes Lookup, als Overlay (Dialog #rivaldlg): ein Knopf je App mit Name und Kennzeichen
    function openProfile(a) {
      const p = a.profile, d = $("rivaldlg");
      const row = (label, value) => value ? h("p", {}, h("b", {}, label), value) : null;
      d.replaceChildren(
        h("div", { class: "dhead" }, h("div", { class: "row", style: "justify-content:space-between" }, h("span", { class: "muted" }, tx("Steckbrief aus dem App Store", "Profile from the App Store")),
            h("button", { class: "iconbtn", type: "button", "aria-label": tx("Schließen", "Close"), onclick: () => d.close() }, "×")),
          h("h2", { style: "font-size:1.5rem;margin:.6rem 0 .3rem" }, a.appName, rivalMark(a)),
          h("div", { class: "muted" }, [p.sellerName, p.genre].filter(Boolean).join(" · "))),
        h("div", { class: "dbody" }, row(tx("Name im Store: ", "Store name: "), p.trackName), row(tx("Hersteller: ", "Vendor: "), p.sellerName), row("Genre: ", p.genre),
          row("Version: ", p.version ? p.version + (p.releasedAt ? tx(" vom ", " of ") + fmtDay(p.releasedAt) : "") : null),
          p.storeUrl ? h("p", {}, h("a", { href: p.storeUrl, target: "_blank", rel: "noopener noreferrer" }, p.storeUrl)) : null,
          p.releaseNotes ? h("div", { style: "margin-top:.8rem" }, h("h3", {}, tx("Neu in dieser Version", "What’s new in this version")), h("div", { class: "quote", style: "white-space:pre-line" }, p.releaseNotes)) : null,
          p.description ? h("div", { style: "margin-top:.8rem" }, h("h3", {}, tx("Beschreibung", "Description")), h("div", { class: "quote", style: "white-space:pre-line" }, p.description)) : null,
          h("p", { class: "note" }, tx("Erfasst am ", "Captured at ") + fmtDate(p.capturedAt) + tx(" über den öffentlichen iTunes Lookup.", " via the public iTunes Lookup."))));
      if (d.showModal && !d.open) d.showModal(); else d.setAttribute("open", "");
    }
    const sheets = rivals.filter(a => a.profile).map(a => h("button", { type: "button", class: "btn", onclick: () => openProfile(a) }, a.appName, rivalMark(a)));
    if (sheets.length) put(box, h("h3", { class: "sub3", style: "margin-top:1.4rem" }, tx("Steckbriefe", "Profiles")),
      h("div", { class: "note", style: "margin-top:0" }, tx("Klick öffnet den Steckbrief aus dem App Store als Fenster.", "Click opens the App Store profile as a window.")), h("div", { class: "rivallist" }, sheets));
    sortTables(box, "rivals");
  }
  if ($("rivaldlg").addEventListener) $("rivaldlg").addEventListener("click", e => { if (e.target === $("rivaldlg") && $("rivaldlg").close) $("rivaldlg").close(); });
