// Kernfunktionen ohne DOM (Filter, Kennzahlen, Formeln); Tests führen den Block zwischen <core> und </core> in Node aus.
// <core>
const NONE = "__none__";
const FIELD_FILTERS = ["customerId", "platform", "language", "country", "appVersion", "osLabel", "device"];

function fieldValue(r, f) {
  if (f === "appKey") return r.customerId + "/" + r.appId;
  if (f === "osLabel") { const v = [r.operatingSystem, r.osVersion].filter(Boolean).join(" "); return v || NONE; }
  const v = r[f];
  return (v === null || v === undefined || v === "") ? NONE : String(v);
}
function hasReply(r) { return !!(r.developerReply && r.developerReply.text); }
// Filterwert: leer = alle; Liste = Mehrfachauswahl (Kunde, App; leere Liste = alle); sonst genau dieser Wert
function inSel(sel, v) { return Array.isArray(sel) ? !sel.length || sel.includes(v) : !sel || sel === v; }
// Wettbewerber (r.competitor) zählen nur, wenn sie ausdrücklich im App-Filter gewählt sind; „Alle“ meint die eigenen Apps
function rivalHidden(r, f) { return !!r.competitor && !(Array.isArray(f.appKey) && f.appKey.length); }
function matches(r, f) {
  if (rivalHidden(r, f)) return false;
  for (const k of FIELD_FILTERS) if (!inSel(f[k], fieldValue(r, k))) return false;
  if (!inSel(f.appKey, fieldValue(r, "appKey"))) return false;
  if (f.ratingMin && !(r.rating >= f.ratingMin)) return false;
  if (f.ratingMax && !(r.rating <= f.ratingMax)) return false;
  const d = r.createdAt || "";
  if (f.from && !(d >= f.from)) return false;
  if (f.to && !(d <= f.to + "T23:59:59Z")) return false;
  if (f.reply === "with" && !hasReply(r)) return false;
  if (f.reply === "without" && hasReply(r)) return false;
  if (f.textOnly && !(r.text && r.text.trim())) return false;
  if (f.topic && !reviewTopics(r).includes(f.topic)) return false;
  if (f.aiSentiment && r.aiSentiment !== f.aiSentiment) return false;
  if (f.aiUrgency && r.aiUrgency !== f.aiUrgency) return false;
  if (f.q) {
    const hay = [r.title, r.text, r.developerReply && r.developerReply.text, r.appVersion, r.device, r.appName]
      .filter(Boolean).join("\n").toLowerCase();
    if (!hay.includes(f.q.toLowerCase())) return false;
  }
  return true;
}
function applyFilters(reviews, f, skip) {
  const eff = Object.assign({}, f);
  (skip || []).forEach(k => { eff[k] = ""; });
  return reviews.filter(r => matches(r, eff));
}
function stats(rs) {
  const dist = [0, 0, 0, 0, 0, 0]; let sum = 0, n = 0, noReply = 0;
  for (const r of rs) {
    if (r.rating >= 1 && r.rating <= 5) { dist[r.rating]++; sum += r.rating; n++; }
    if (!hasReply(r)) noReply++;
  }
  return { count: rs.length, rated: n, avg: n ? sum / n : null, dist, pos: dist[4] + dist[5], neg: dist[1] + dist[2],
           noReply, negShare: n ? (dist[1] + dist[2]) / n : null };
}
function groupBy(rs, keyFn) {
  const m = new Map();
  for (const r of rs) { const k = keyFn(r); if (!m.has(k)) m.set(k, []); m.get(k).push(r); }
  return m;
}
function csvCell(v) {
  if (v === null || v === undefined) return "";
  let s = typeof v === "object" ? JSON.stringify(v) : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;       // Schutz vor Formel-Injektion in Tabellenkalkulationen
  return /[",\n\r;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
const CSV_COLUMNS = ["customerId", "appId", "platform", "rating", "title", "text", "createdAt", "updatedAt", "country",
  "language", "appVersion", "buildNumber", "operatingSystem", "osVersion", "device", "developerReply", "id",
  "aiSentiment", "aiUrgency", "aiIssue"];  // KI-Spalten bleiben leer, wenn keine Analyse vorliegt
function toCsv(rs) {
  const lines = [CSV_COLUMNS.join(",")];
  for (const r of rs) lines.push(CSV_COLUMNS.map(c => csvCell(c === "developerReply" ? (r.developerReply && r.developerReply.text) : r[c])).join(","));
  return lines.join("\r\n") + "\r\n";
}
function toJson(rs) { return JSON.stringify(rs.map(r => { const c = Object.assign({}, r); delete c.raw; return c; }), null, 2); }
function monthKey(r) { return r.createdAt ? r.createdAt.slice(0, 7) : null; }
function sortReviews(rs, key, dir) {
  const val = r => key === "reply" ? (hasReply(r) ? 1 : 0) : key === "osLabel" ? fieldValue(r, "osLabel") : r[key];
  return rs.slice().sort((a, b) => {
    const x = val(a), y = val(b);
    if (x === y) return 0;
    if (x === null || x === undefined || x === NONE) return 1;
    if (y === null || y === undefined || y === NONE) return -1;
    return (x < y ? -1 : 1) * dir;
  });
}
function weekStart(d) {
  const t = new Date(d + "T00:00:00Z"); t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7));
  return t.toISOString().slice(0, 10);
}
// Zeilen: crashes [Datum, Version, OS, Gerät, Abstürze, Geräte], sessions [Datum, Version, OS, Gerät, Sitzungen, Dauer]
function stabilityBy(crashRows, sessionRows, keyFn) {
  const m = new Map();
  const get = k => { if (!m.has(k)) m.set(k, { key: k, crashes: 0, sessions: 0, first: null, last: null }); return m.get(k); };
  const touch = (o, d) => { if (!o.first || d < o.first) o.first = d; if (!o.last || d > o.last) o.last = d; };
  for (const r of crashRows) { const o = get(keyFn(r)); o.crashes += r[4]; touch(o, r[0]); }
  for (const r of sessionRows) { const o = get(keyFn(r)); o.sessions += r[4]; touch(o, r[0]); }
  return [...m.values()].map(o => Object.assign(o, { rate: o.sessions > 0 ? 1000 * o.crashes / o.sessions : null, small: o.crashes < 5 }));
}
// „Alle Apps auf einen Blick“: feste Feldgrenzen (4 ★, 2 Abstürze je 1000 Sitzungen), damit eine App nicht das Feld
// wechselt, nur weil sich andere Apps verändern. Unter 5 Rezensionen oder 500 Sitzungen gilt sie als kleine Stichprobe.
const ZONE = { stars: 4, rate: 2, minReviews: 5, minSessions: 500 };
function zoneOf(avg, rate) {
  if (avg === null || rate === null) return null;
  return avg >= ZONE.stars && rate < ZONE.rate ? "good" : avg < ZONE.stars && rate >= ZONE.rate ? "bad" : "mid";
}
// Je App: Ø Sterne aus den übergebenen Rezensionen, Absturzrate aus den Stabilitätsdaten im Zeitraum [from, to].
// Ohne Rezensionen bzw. Sitzungen bleiben avg bzw. rate null (nichts wird geschätzt).
function portfolio(apps, rs, stab, from, to) {
  const key = x => x.customerId + "/" + x.appId + "/" + x.platform, m = new Map(), inP = d => d >= (from || "") && (!to || d <= to);
  for (const a of apps) m.set(key(a), { customerId: a.customerId, customerName: a.customerName, appId: a.appId, appName: a.appName, platform: a.platform, rated: 0, sum: 0, crashes: 0, sessions: 0 });
  for (const r of rs) { const o = m.get(key(r)); if (o && r.rating >= 1 && r.rating <= 5) { o.rated++; o.sum += r.rating; } }
  for (const e of stab) {
    const o = m.get(key(e)); if (!o) continue;
    for (const r of e.crashes) if (inP(r[0])) o.crashes += r[4];
    for (const r of e.sessions) if (inP(r[0])) o.sessions += r[4];
  }
  return [...m.values()].map(o => { const avg = o.rated ? o.sum / o.rated : null, rate = o.sessions > 0 ? 1000 * o.crashes / o.sessions : null;
    return Object.assign(o, { avg, rate, zone: zoneOf(avg, rate), small: o.rated < ZONE.minReviews || o.sessions < ZONE.minSessions }); });
}
// ---- Kennzahlen für Steckbrief, Themen und Wörter: reine Funktionen ohne DOM, von test_report.py über Node geprüft ----
// Bayes-geglätteter Durchschnitt (IMDb-Formel): (C·m + Σ Sterne) / (C + n). m = Vergleichsmittel (Plattform), C Pseudostimmen.
// Wenige Rezensionen rücken damit zum Vergleichsmittel; ab vielen Rezensionen zählt praktisch nur noch der eigene Schnitt.
const BAYES_C = 10;
function bayesAvg(sum, n, m, c = BAYES_C) { if (!n) return null; const prior = m === null || m === undefined ? sum / n : m; return (c * prior + sum) / (c + n); }
// Netto-Saldo wie beim NPS: Anteil 4–5 ★ minus Anteil 1–2 ★ in Prozentpunkten (−100 … +100). Robust gegen die J-Verteilung.
function netScore(st) { return st.rated ? 100 * (st.pos - st.neg) / st.rated : null; }
// Halbe Breite des 95-%-Intervalls um den Durchschnitt (1,96 · s / √n), ab zwei bewerteten Rezensionen
function ciHalf(rs) {
  const v = rs.map(r => r.rating).filter(x => x >= 1 && x <= 5); if (v.length < 2) return null;
  const m = v.reduce((a, b) => a + b, 0) / v.length, sd = Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / (v.length - 1));
  return 1.96 * sd / Math.sqrt(v.length);
}
function daysBeforeIso(d, n) { const t = new Date(d + "T00:00:00Z"); t.setUTCDate(t.getUTCDate() - n); return t.toISOString().slice(0, 10); }
// Themen (config/themen.json): ein Begriff trifft am Wortanfang („anmeld“ trifft „Anmeldung“, aber „träge“ nicht „Beiträge“).
// Bis drei Zeichen zählt nur das ganze Wort („abo“ trifft nicht „about“). „*“ vor dem Begriff: auch mitten im Wort
// (Zusammensetzungen wie „Kommafehler“); „=“ davor: nur das ganze Wort („import“, nicht „importantly“). Ein Treffer innerhalb
// einer Ausschlussphrase des Themas (Feld `nicht`: „keine Fehler“, „ohne Werbung“) zählt nicht. Groß-/Kleinschreibung egal.
let TOPICS = [];
const TERM_RX = new Map();
function termRx(term) {
  if (TERM_RX.has(term)) return TERM_RX.get(term);
  let t = term.trim(), mode = "start";
  if (t.startsWith("*")) { mode = "in"; t = t.slice(1); } else if (t.startsWith("=")) { mode = "word"; t = t.slice(1); } else if (t.length <= 3) mode = "word";
  const esc = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const rx = t ? new RegExp((mode === "in" ? "()" : "(^|[^\\p{L}])") + esc + (mode === "word" ? "(?![\\p{L}])" : ""), "gu") : null;
  TERM_RX.set(term, rx); return rx;
}
// Fundstellen [von, bis) eines Begriffs im Text
function termSpans(hay, term) {
  const rx = termRx(term), out = []; if (!rx) return out;
  rx.lastIndex = 0; let m;
  while ((m = rx.exec(hay))) { const a = m.index + m[1].length; out.push([a, m.index + m[0].length]); if (!m[0]) rx.lastIndex++; }
  return out;
}
function tagTopics(r, topics) {
  const hay = ((r.title || "") + "\n" + (r.text || "")).toLowerCase(); if (!hay.trim()) return [];
  return (topics || TOPICS).filter(t => {
    const ex = (t.nicht || []).flatMap(p => termSpans(hay, "*" + p));
    return t.terms.some(term => termSpans(hay, term).some(([a, b]) => !ex.some(([x, y]) => a >= x && b <= y)));
  }).map(t => t.id);
}
function reviewTopics(r) { return r.topics || tagTopics(r); }
// Wörter einer Rezension für die Wortstatistik: alle Buchstaben (auch é, ñ, kyrillisch), Kleinbuchstaben, ab drei Zeichen, ohne
// Stoppwörter (DE, EN, NL, ES, IT, FR, PT, RU); jedes Wort einmal je Rezension. Dazu Zweiwortbegriffe aus benachbarten Wörtern,
// wenn keines ein Stoppwort ist oder eines eine Verneinung („funktioniert nicht“, „keine antwort“, „no reply“). Gezählt wird der
// Wortstamm (`stem`: gängige Endungen abgeschnitten, so dass update/updates/updated zusammenfallen), gezeigt die häufigste
// Schreibform (`surface`).
const STOP = new Set(("aber alle allem allen aller alles als also am an ander andere anderem anderen anderer anderes andern anders auch auf aus bei bin bis bist da damit dann der den des dem die das dass daß dazu dein deine deinem deinen deiner denn dessen dich dir du dies diese diesem diesen dieser dieses doch dort durch ein eine einem einen einer eines einfach einige einmal er ihn ihm es etwas euch euer eure für gegen gewesen gibt hab habe haben hat hatte hatten hier hin hinter ich mich mir ihr ihre ihrem ihren ihrer im in indem ins ist ja jede daher deshalb dabei darum somit trotzdem wirklich gute guter gutes vielen viele jedem jeden jeder jedes jetzt kann kein keine keinem keinen keiner können könnte leider machen macht man manche mehr mein meine meinem meinen meiner mit muss musste nach nicht nichts noch nun nur ob oder ohne sehr sein seine seinem seinen seiner seit selbst sich sie sind so solche soll sollte sondern sonst über um und uns unser unter viel vom von vor war waren warum was weg weil weiter welche wenn werde werden wie wieder will wir wird wirst wo wollen wollte würde würden zu zum zur zwar zwischen app apps mal schon immer ganz gut dann nun " +
  "nutze nutzen benutze benutzen verwende verwenden bereits seitdem mittlerweile inzwischen jedoch allerdings eigentlich natürlich halt eben bzw ggf sowie wurde wurden worden hätte hätten habt bisher dafür dadurch davon darauf dazu deren derer welcher welches diejenigen jene sowohl bzw " +
  "the and for that this with you your are was were have has had not but they them their its can will just from our out all any more very been being into than then there these those what when where which who why how its too also only over such some most much each other because about after before again against between both did does doing done down during few further here his her him off once own same she should than under until very ver would could get got lot bit getting since still even every now really use using used like one two make makes made way thing things " +
  "doesn don isn didn wasn aren couldn wouldn shouldn hasn haven ive youre theyre weve cant wont " +
  "het een van jij hij zij wij jullie zijn ben bent heb hebt heeft hebben had hadden niet geen wel ook nog maar want dus als dan dat dit die deze hier daar wat wie waar hoe voor met door over naar tot tegen zonder zeer heel erg goed goede veel meer minder alles iets niets kan kun kunnen kon zou zouden wil wilt willen moet moeten mag mogen laat gaat gaan " +
  "los las una unos unas del para que qué como cómo cuando donde cual cuales quien son está están estoy fue fueron ser estar hay han haber ella nosotros ellos ellas nos les este esta estos estas ese esa esos esas eso esto aquí ahí allí también muy más menos mucho mucha muchos muchas poco pero porque aunque todo toda todos todas otro otra otros otras bien mal cada vez veces desde hasta sobre entre puede pueden puedo quiero tiene tienen tengo hace hacer solo sólo " +
  "gli della dei delle dello degli alla alle dal dalla nel nella nei nelle sul sulla per tra fra anche non che chi cui come quando dove perché lui lei noi voi loro mio mia miei mie tuo tua suo sua questo questa questi queste quello quella quelli quelle sono era erano essere hai hanno avere fare molto molta molti molte più meno tutto tutta tutti tutte ogni già ancora sempre solo poi qui qua bene male così " +
  "les une des aux mais donc car pas plus moins très que qui quoi dont est sont été être avoir avons avez ont elle nous vous ils elles mon mes ton tes son ses cet cette ces cela ceci dans sur sous avec sans pour par chez vers comme aussi bien tout toute tous toutes même encore déjà toujours jamais ici peut peux pouvez peuvent faire fait " +
  "uma uns umas dos das por para com sem quem como quando onde mas não sim também muito muita muitos muitas mais menos são foi foram ser estar está estão tem têm ter ele ela nós eles elas meu minha seu sua este esta esse essa isso isto aqui ali ainda sempre todo toda todos todas " +
  "что это как они оно она все всё очень есть был была были нет уже только ещё еще мне меня его её их нас вас так если или для при что-то этот эта эти тоже можно").split(" "));
const NEG = new Set("nicht nie niemals kein keine keinen keinem keiner nichts ohne not never without geen niet nooit nunca jamais jamás sin senza mai pas aucun aucune não nenhum nenhuma нет".split(" "));
const SUFFIXES = ["ungen", "ieren", "iert", "innen", "ung", "end", "ern", "ert", "est", "ing", "en", "er", "es", "em", "ed", "st", "e", "s", "n"];
function stem(w) {
  for (let pass = 0; pass < 2; pass++) {
    const s = SUFFIXES.find(x => w.endsWith(x) && w.length - x.length >= 4); if (!s) break;
    w = w.slice(0, -s.length);
  }
  return w;
}
const FORMS = new Map();
function noteForm(key, form) { let m = FORMS.get(key); if (!m) FORMS.set(key, m = new Map()); m.set(form, (m.get(form) || 0) + 1); }
function surface(key) { const m = FORMS.get(key); if (!m) return key; let best = key, n = 0; for (const [f, c] of m) if (c > n) { best = f; n = c; } return best; }
function tokens(r) {
  const words = ((r.title || "") + " " + (r.text || "")).toLowerCase().split(/[^\p{L}]+/u).filter(w => w.length >= 2), out = new Set();
  const add = (key, form) => { if (!out.has(key)) { out.add(key); noteForm(key, form); } };
  const ok = w => w.length >= 3 && !STOP.has(w);
  for (let i = 0; i < words.length; i++) {
    const a = words[i], b = words[i + 1];
    if (ok(a)) add(stem(a), a);
    if (b && ((ok(a) && ok(b)) || (NEG.has(a) && ok(b)) || (ok(a) && NEG.has(b)))) add((NEG.has(a) ? a : stem(a)) + " " + (NEG.has(b) ? b : stem(b)), a + " " + b);
  }
  return [...out];
}
// Typische Wörter zweier Gruppen: Log-Odds-Verhältnis mit informativem Dirichlet-Prior und z-Wert
// (Monroe, Colaresi, Quinn 2008, „Fightin’ Words“). Liefert Wörter, die in A deutlich häufiger sind als in B und umgekehrt;
// gezeigt nur ab |z| ≥ minZ, damit bei wenig Text nicht Zufallsfunde als „typisch“ erscheinen.
function logOdds(groupA, groupB, limit = 12, minCount = 2, minZ = 1) {
  const ca = new Map(), cb = new Map(), all = new Map(); let na = 0, nb = 0;
  for (const r of groupA) for (const w of tokens(r)) { ca.set(w, (ca.get(w) || 0) + 1); all.set(w, (all.get(w) || 0) + 1); na++; }
  for (const r of groupB) for (const w of tokens(r)) { cb.set(w, (cb.get(w) || 0) + 1); all.set(w, (all.get(w) || 0) + 1); nb++; }
  const n0 = na + nb, a0 = 0.5 * all.size, out = [];
  if (!n0) return { a: [], b: [] };
  for (const [w, tot] of all) {
    const ya = ca.get(w) || 0, yb = cb.get(w) || 0; if (ya + yb < minCount) continue;
    const aw = a0 * tot / n0, d = Math.log((ya + aw) / (na + a0 - ya - aw)) - Math.log((yb + aw) / (nb + a0 - yb - aw)), v = 1 / (ya + aw) + 1 / (yb + aw);
    out.push({ w: surface(w), key: w, z: d / Math.sqrt(v), a: ya, b: yb });
  }
  out.sort((x, y) => y.z - x.z);
  return { a: out.filter(x => x.z >= minZ).slice(0, limit), b: out.filter(x => x.z <= -minZ).reverse().slice(0, limit) };
}
// Neu auftauchende Begriffe: Rezensionen je Tag mit dem Wort in den letzten `days` Tagen gegen die Zeit davor (+1 geglättet);
// gezeigt werden Wörter mit mindestens zwei Treffern und mindestens dreifacher Rate.
function burstWords(rs, asOf, days = 30, limit = 10) {
  const since = daysBeforeIso(asOf, days), rec = rs.filter(r => (r.createdAt || "") >= since), old = rs.filter(r => r.createdAt && r.createdAt < since);
  if (rec.length < 3 || !old.length) return [];
  const firstOld = old.reduce((m, r) => r.createdAt < m ? r.createdAt : m, "9999").slice(0, 10), oldDays = Math.max(days, (Date.parse(since + "T00:00:00Z") - Date.parse(firstOld + "T00:00:00Z")) / 864e5);
  const cr = new Map(), co = new Map();
  for (const r of rec) for (const w of tokens(r)) cr.set(w, (cr.get(w) || 0) + 1);
  for (const r of old) for (const w of tokens(r)) co.set(w, (co.get(w) || 0) + 1);
  return [...cr.entries()].filter(([, n]) => n >= 2).map(([w, n]) => ({ w: surface(w), key: w, n, before: co.get(w) || 0, ratio: (n / days) / (((co.get(w) || 0) + 1) / oldDays) }))
    .filter(x => x.ratio >= 3).sort((x, y) => y.ratio - x.ratio).slice(0, limit);
}
// Store-Bewertungen im Zeitraum: Apple nennt nur Gesamtzahl und Ø seit Erscheinen der App. Aus zwei gespeicherten Ständen
// (snaps: eine App, ein Land, aufsteigend nach capturedAt) ergibt sich die Zahl neuer Bewertungen und deren Ø:
// Ø neu = (Ø_end · n_end − Ø_start · n_start) / (n_end − n_start). Liegt der Zeitraumbeginn vor dem ersten Stand, beginnt die
// Rechnung am ersten Stand (partial = true, since = dessen Tag). Sinkt die Zahl (Apple entfernt Bewertungen), gibt es kein Ø.
function storeChange(snaps, from, to) {
  const day = s => (s.capturedAt || "").slice(0, 10), upto = to ? snaps.filter(s => day(s) <= to) : snaps;
  if (!upto.length) return null;
  const end = upto[upto.length - 1], before = from ? upto.filter(s => day(s) <= from) : [upto[0]];
  const partial = !before.length, base = partial ? upto[0] : before[before.length - 1];
  const delta = (end.total || 0) - (base.total || 0);
  let avg = delta > 0 ? ((end.average || 0) * (end.total || 0) - (base.average || 0) * (base.total || 0)) / delta : null;
  if (avg !== null && !(avg >= 1 && avg <= 5)) avg = null;
  return { delta, avg, since: partial ? day(base) : from, partial };
}
// </core>
