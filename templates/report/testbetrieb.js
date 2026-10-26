  // Testbetrieb (TestFlight, Google-Testspuren) mit eigenem Filter.
  // ---- Testbetrieb (Umschalter #modeseg im Kopf schaltet body[data-mode=test]) ----
  (function testflight() {
    const TF = DATA.testflight || [], GT = DATA.googleTesting || [], box = $("tfout"), fbox = $("tffilters");
    const pct = r => fmt(r / 10, 2) + " %";
    const customerName = id => (DATA.apps.find(a => a.customerId === id) || {}).customerName || id;
    const aBuilds = [], aCrashes = [];
    TF.forEach(x => {
      const byId = new Map(x.builds.map(b => [b.id, b])), base = { customerId: x.customerId, appId: x.appId, appName: x.appName, appKey: x.customerId + "/" + x.appId };
      x.builds.forEach(b => aBuilds.push(Object.assign({}, base, b, b.usage || {}, { hasUsage: !!b.usage })));
      x.crashes.forEach(c => { const b = byId.get(c.buildId) || {}; aCrashes.push(Object.assign({}, base, c, { version: b.version || null, build: b.build || null })); });
    });
    const gApps = GT.map(x => Object.assign({}, x, { appKey: x.customerId + "/" + x.appId }));
    const trackOf = (x, code) => x.tracks.filter(t => t.releases.some(r => r.versionCodes.includes(code))).map(t => t.track);
    const F = {}, controls = [];
    const uniq = (rows, f) => [...new Set(rows.map(f).filter(v => v !== null && v !== undefined && v !== ""))];
    const byText = (a, b) => String(a[1]).localeCompare(String(b[1]), LANG, { numeric: true });
    function select(key, label, options, id) {
      const sel = h("select", { id: id || "tf_" + key }, h("option", { value: "" }, tx("Alle", "All")), options.map(([v, l]) => h("option", { value: v }, l)));
      sel.addEventListener("change", () => { F[key] = sel.value; draw(); });
      fbox.append(h("label", {}, label, sel));
      controls.push({ label, active: () => { const o = options.find(x => String(x[0]) === sel.value); return o ? o[1] : ""; }, clear: () => { sel.value = ""; F[key] = ""; } });
      return sel;
    }
    const allApps = [...new Map(aBuilds.concat(aCrashes).concat(gApps).map(x => [x.appKey, x.appName])).entries()].sort(byText);
    select("customerId", tx("Kunde", "Customer"), uniq(aBuilds.concat(gApps), x => x.customerId).map(id => [id, customerName(id)]).sort(byText));
    select("appKey", "App", allApps, "tfApp");
    select("platform", tx("Plattform", "Platform"), [aBuilds.length || aCrashes.length ? ["apple", "Apple (TestFlight)"] : null, gApps.length ? ["google", "Google Play"] : null].filter(Boolean));
    select("version", "Version (Apple)", uniq(aBuilds, b => b.version).sort((a, b) => b.localeCompare(a, LANG, { numeric: true })).map(v => [v, v]));
    select("status", tx("Build-Status (Apple)", "Build status (Apple)"), [["active", tx("Aktiv", "Active")], ["expired", tx("Abgelaufen", "Expired")]]);
    select("track", tx("Spur (Google)", "Track (Google)"), uniq(gApps.flatMap(x => x.tracks), t => t.track).map(t => [t, t]));
    select("versionCode", tx("Versionscode (Google)", "Version code (Google)"), uniq(gApps.flatMap(x => x.crashRates), r => r.versionCode).sort((a, b) => Number(b) - Number(a)).map(v => [v, v]));
    if (aCrashes.length) {
      select("os", tx("Betriebssystem", "Operating system"), uniq(aCrashes, c => c.osVersion).map(v => [v, v]).sort(byText));
      select("device", tx("Gerätemodell", "Device model"), uniq(aCrashes, c => c.device).map(v => [v, v]).sort(byText));
    }
    for (const [key, label] of [["from", tx("Von", "From")], ["to", tx("Bis", "To")]]) {
      const inp = h("input", { type: "date", id: "tf_" + key });
      inp.addEventListener("change", () => { F[key] = inp.value; draw(); });
      fbox.append(h("label", {}, label, inp));
      controls.push({ label, active: () => inp.value, clear: () => { inp.value = ""; F[key] = ""; } });
    }
    $("tfreset").addEventListener("click", () => { controls.forEach(c => c.clear()); draw(); });
    const inRange = d => (!F.from || d >= F.from) && (!F.to || d <= F.to + "T23:59:59Z");
    const common = x => (!F.customerId || x.customerId === F.customerId) && (!F.appKey || x.appKey === F.appKey);
    const fb = b => common(b) && (!F.version || b.version === F.version) && (!F.status || (F.status === "expired") === !!b.expired) && inRange(b.uploadedAt || "");
    const fc = c => common(c) && (!F.version || c.version === F.version) && (!F.os || c.osVersion === F.os) && (!F.device || c.device === F.device) && inRange(c.createdAt || "");

    // setMode (Umschalter im Kopf) ruft diesen Haken auf: Kopfzeile tauschen, Testansicht zeichnen
    onMode = function (mode) {
      const lead = $("lead"); if (lead.dataset.prod === undefined) lead.dataset.prod = lead.textContent;
      lead.textContent = mode === "test" ? tx(fmtInt(aBuilds.length) + " TestFlight-Builds und " + fmtInt(aCrashes.length) + " Absturzmeldungen aus " + TF.length + " Apple-Apps, " + GT.length + " Google-Apps mit Testspuren – offline, ohne Server, ohne Tracking.", fmtInt(aBuilds.length) + " TestFlight builds and " + fmtInt(aCrashes.length) + " crash reports from " + TF.length + " Apple apps, " + GT.length + " Google apps with test tracks – offline, no server, no tracking.") : lead.dataset.prod;
      if (mode === "test") draw();
    };
    const sum = (rows, k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
    const rate = (c, n) => n > 0 ? 1000 * c / n : null;
    const rateEl = r => r === null ? h("span", { class: "muted" }, "–") : h("span", { class: "pill " + (r >= 10 ? "r1" : r >= 3 ? "r3" : "r5") }, fmt(r) + " (" + pct(r) + ")");
    function table(title, heads, rows) {
      return h("div", { style: "margin-top:1.2rem" }, h("h3", {}, title), h("div", { class: "tablewrap", style: "max-height:none" }, h("table", {}, h("thead", {}, h("tr", {}, heads.map(t => h("th", {}, t)))), h("tbody", {}, rows))));
    }
    const empty = (cols, text) => [h("tr", {}, h("td", { colspan: String(cols), class: "muted" }, text))];
    function draw() {
      box.replaceChildren();
      const chips = $("tfchips"); chips.replaceChildren();
      controls.forEach(c => { const v = c.active(); if (v) chips.append(h("span", { class: "chip" }, c.label + ": " + v, h("button", { type: "button", "aria-label": c.label + tx(" entfernen", " remove"), onclick: () => { c.clear(); draw(); } }, "×"))); });
      if (!TF.length && !GT.length) { $("tfcount").textContent = ""; put(box, h("div", { class: "warn" }, tx("Keine Testdaten vorhanden. Abruf: ./ratings.sh testdata", "No test data. Fetch: ./ratings.sh testdata"))); return; }
      const showA = !F.platform || F.platform === "apple", showG = !F.platform || F.platform === "google";
      const builds = showA ? aBuilds.filter(fb) : [], crashes = showA ? aCrashes.filter(fc) : [];
      const gSel = showG ? gApps.filter(common) : [];
      $("tfcount").textContent = fmtInt(builds.length) + tx(" von ", " of ") + fmtInt(aBuilds.length) + " Builds · " + fmtInt(crashes.length) + tx(" von ", " of ") + fmtInt(aCrashes.length) + tx(" Absturzmeldungen", " crash reports") + (gApps.length ? " · " + gSel.length + tx(" Google-Apps", " Google apps") : "") + tx(" entsprechen den Filtern", " match the filters");
      if (builds.length || crashes.length || (showA && aBuilds.length)) {
        const inst = sum(builds, "installCount"), ses = sum(builds, "sessionCount"), cr = sum(builds, "crashCount");
        const r = rate(cr, ses);
        put(box, h("div", { class: "grid kpis", style: "margin-top:1rem" }, [[fmtInt(builds.length), "Builds"], [fmtInt(builds.filter(b => !b.expired).length), tx("davon aktiv", "of which active")], [fmtInt(inst), tx("Installationen", "Installs")], [fmtInt(ses), tx("Sitzungen", "Sessions")], [fmtInt(cr), tx("Abstürze", "Crashes")],
          [r === null ? "–" : fmt(r), tx("Abstürze je 1000 Sitzungen", "Crashes per 1,000 sessions") + (r === null ? "" : " (" + pct(r) + ")")], [fmtInt(sum(builds, "feedbackCount")), "Feedback"]].map(([v, l]) =>
          h("div", { class: "card kpi" }, h("b", { class: "num", style: "font-size:" + (v.length > 14 ? "1.05rem" : "1.8rem") }, v), h("span", {}, l)))));
        const apps = new Map();
        builds.forEach(b => { const o = apps.get(b.appKey) || { name: b.appName, n: 0, active: 0, i: 0, s: 0, c: 0 }; o.n++; if (!b.expired) o.active++; o.i += b.installCount || 0; o.s += b.sessionCount || 0; o.c += b.crashCount || 0; apps.set(b.appKey, o); });
        put(box, table(tx("Apple TestFlight nach App", "Apple TestFlight by app"), ["App", "Builds", tx("davon aktiv", "of which active"), tx("Installationen", "Installs"), tx("Sitzungen", "Sessions"), tx("Abstürze", "Crashes"), tx("je 1000 Sitzungen", "per 1,000 sessions")],
          [...apps.values()].sort((a, b) => b.s - a.s).map(o => h("tr", {}, h("td", {}, h("b", {}, o.name)), h("td", { class: "num" }, fmtInt(o.n)), h("td", { class: "num" }, fmtInt(o.active)), h("td", { class: "num" }, fmtInt(o.i)), h("td", { class: "num" }, fmtInt(o.s)), h("td", { class: "num" }, fmtInt(o.c)), h("td", {}, rateEl(rate(o.c, o.s)))))));
        const byVer = builds.slice().sort((a, b) => (b.uploadedAt || "").localeCompare(a.uploadedAt || "")).slice(0, 40);
        put(box, table(tx("Apple TestFlight nach Version und Build (neueste zuerst, höchstens 40)", "Apple TestFlight by version and build (newest first, at most 40)"), ["App", "Version", "Build", tx("Hochgeladen", "Uploaded"), tx("Läuft ab", "Expires"), tx("Installationen", "Installs"), tx("Sitzungen", "Sessions"), tx("Abstürze", "Crashes"), tx("je 1000 Sitzungen", "per 1,000 sessions")],
          byVer.length ? byVer.map(b => h("tr", {}, h("td", {}, b.appName), h("td", {}, b.version || "–"), h("td", {}, b.build || "–"), h("td", { class: "num" }, fmtDate(b.uploadedAt)),
            h("td", { class: "num" }, b.expired ? tx("abgelaufen", "expired") : fmtDate(b.expiresAt)), h("td", { class: "num" }, b.hasUsage ? fmtInt(b.installCount) : "–"), h("td", { class: "num" }, b.hasUsage ? fmtInt(b.sessionCount) : "–"),
            h("td", { class: "num" }, b.hasUsage ? fmtInt(b.crashCount) : "–"), h("td", {}, b.hasUsage ? rateEl(rate(b.crashCount, b.sessionCount)) : "–"))) : empty(9, tx("Keine Builds für diese Filter.", "No builds match these filters."))));
        const count = keyFn => { const m = new Map(); crashes.forEach(c => { const k = keyFn(c) || tx("(unbekannt)", "(unknown)"); m.set(k, (m.get(k) || 0) + 1); }); return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15); };
        if (crashes.length) {
          for (const [title, head, fn] of [[tx("Absturzmeldungen nach Version", "Crash reports by version"), "Version", c => c.version], [tx("Absturzmeldungen nach Betriebssystem", "Crash reports by operating system"), tx("Betriebssystem", "Operating system"), c => c.osVersion], [tx("Absturzmeldungen nach Gerät", "Crash reports by device"), tx("Gerät", "Device"), c => c.device]])
            put(box, table(title, [head, tx("Meldungen", "Reports")], count(fn).map(([k, n]) => h("tr", {}, h("td", {}, k), h("td", { class: "num" }, fmtInt(n))))));
        } else put(box, h("div", { class: "warn" }, tx("Keine einzelnen Absturzmeldungen von Testern für diese Filter. Aufteilung nach Betriebssystem und Gerät ist nur damit möglich; die Zahlen oben je Build liefert Apple ohne diese Aufteilung.", "No individual tester crash reports match these filters. Breakdown by operating system and device needs them; the per-build figures above come from Apple without this breakdown.")));
        put(box, h("div", { class: "note" }, tx("Nutzungszahlen je Build gelten für den von Apple gemeldeten Zeitraum (rund ein Jahr), nicht je Tag; Zeitraumfilter wirken auf Upload-Datum und Meldedatum. Keine Tester-Namen, E-Mail-Adressen oder Absturzprotokolle gespeichert.", "Usage figures per build cover the period reported by Apple (about a year), not per day; period filters apply to upload date and report date. No tester names, e-mail addresses or crash logs are stored.")));
      }
      if (gSel.length) {
        put(box, h("h3", { style: "margin-top:1.6rem" }, "Google Play"), h("div", { class: "warn" }, tx("Google-Testdaten sind noch nicht gegen die echte API geprüft. Absturzraten sind Anteile der Nutzer und nicht mit Apple vergleichbar; Google trennt sie nicht nach Test und Produktion, die Spur ergibt sich über den Versionscode.", "Google test data has not yet been verified against the real API. Crash rates are shares of users and not comparable with Apple; Google does not separate test and production, the track is derived from the version code.")));
        const trackRows = gSel.flatMap(x => x.tracks.filter(t => !F.track || t.track === F.track).flatMap(t => t.releases.filter(r => !F.versionCode || r.versionCodes.includes(F.versionCode)).map(r => h("tr", {}, h("td", {}, h("b", {}, x.appName)), h("td", {}, t.track || "–"), h("td", {}, r.name || "–"), h("td", {}, r.status || "–"), h("td", {}, r.versionCodes.join(", ") || "–"), h("td", { class: "num" }, r.userFraction === null || r.userFraction === undefined ? "–" : fmt(r.userFraction * 100, 0) + " %")))));
        put(box, table(tx("Google Play: Testspuren und Releases", "Google Play: test tracks and releases"), ["App", tx("Spur", "Track"), "Release", "Status", tx("Versionscodes", "Version codes"), tx("Anteil", "Share")], trackRows.length ? trackRows : empty(6, tx("Keine Spuren für diese Filter.", "No tracks match these filters."))));
        const rateRows = [];
        for (const x of gSel) {
          const by = new Map();
          for (const r of x.crashRates) {
            if (F.versionCode && r.versionCode !== F.versionCode) continue;
            if (F.track && !trackOf(x, r.versionCode).includes(F.track)) continue;
            if (!inRange(r.date)) continue;
            const o = by.get(r.versionCode) || { w: 0, c: 0, p: 0, max: 0, days: 0 }; const w = r.distinctUsers || 1; o.w += w; o.c += (r.crashRate || 0) * w; o.p += (r.userPerceivedCrashRate || 0) * w; o.max = Math.max(o.max, r.distinctUsers || 0); o.days++; by.set(r.versionCode, o);
          }
          for (const [code, o] of by) rateRows.push({ app: x.appName, code, track: trackOf(x, code).join(", ") || "–", crash: 100 * o.c / o.w, perceived: 100 * o.p / o.w, users: o.max, days: o.days });
        }
        rateRows.sort((a, b) => Number(b.code) - Number(a.code));
        put(box, table(tx("Google Play: Absturzrate je Versionscode (gewichtet nach Nutzern)", "Google Play: crash rate per version code (weighted by users)"), ["App", tx("Versionscode", "Version code"), tx("Spur", "Track"), tx("Absturzrate", "Crash rate"), tx("nutzerwahrgenommen", "user-perceived"), tx("Nutzer (max. pro Tag)", "Users (max. per day)"), tx("Tage mit Daten", "Days with data")],
          rateRows.length ? rateRows.map(o => h("tr", {}, h("td", {}, h("b", {}, o.app)), h("td", {}, o.code), h("td", {}, o.track), h("td", { class: "num" }, fmt(o.crash) + " %"), h("td", { class: "num" }, fmt(o.perceived) + " %"), h("td", { class: "num" }, fmtInt(o.users)), h("td", { class: "num" }, fmtInt(o.days)))) : empty(7, tx("Keine Absturzraten für diese Filter.", "No crash rates match these filters."))));
      }
      sortTables(box, "tf");
    }
  })();

