  // Reiter, Bereiche ein-/zuklappen, Erklärtexte (INFO), Rezensionstabelle, Gesamtdarstellung.
  // ---- Bereiche: jeder gehört zu einem Reiter (TABS); je Bereich ein-/zuklappen (localStorage „sections“) ----
  // Reihenfolge = Reihenfolge der Karten; innerhalb eines Reiters gilt dieselbe Reihenfolge (Rezensionen direkt unter
  // „Themen und Wörter“, weil ein Klick auf ein Thema die Liste darunter filtert)
  const SECS = [["ueberblick", "Überblick", "Overview"], ["steckbrief", "Die wichtigsten Zahlen je App", "Key figures per app"],
    ["appvgl", "Apps im Vergleich", "Apps compared"], ["storewerte", "Sterne im App Store", "Stars in the App Store"],
    ["latestver", "Neueste Version im Store", "Latest version in the store"], ["diagramme", "Diagramme", "Charts"], ["stab", "Stabilität", "Stability"],
    ["vergleich", "Vergleich nach Version", "Comparison by version"], ["release", "Was ein Update verändert hat", "What an update changed"], ["fragen", "Fragen und Antworten", "Questions and answers"],
    ["themen", "Themen und Wörter", "Topics and words"], ["rezensionen", "Rezensionen", "Reviews"],
    ["antworten", "Antworten des Supports", "Support replies"],
    ["wettbewerber", "Wettbewerber (nur Apple)", "Competitors (Apple only)"],
    ["kifragen", "Fragen an die Daten (KI)", "Questions to the data (AI)"],
    ["hinweise", "Wie vollständig sind die Daten?", "How complete is the data?"]];
  // KI-Inhalte stehen in den Fachbereichen (kein eigener Reiter, Entscheidung des Nutzers 24.10.2026); featOn() in ki.js
  // prüft je Baustein die Funktion aus ai.features. Nur „Fragen an die Daten“ hat einen eigenen Reiter „KI-Anfragen“ (Wunsch des Nutzers 24.10.2026).
  // Fachliche Erklärung je Bereich (rotes „i“ neben der Überschrift öffnet sie als Fenster): Absätze de/en
  const INFO = {
    ueberblick: [["Was hier steht", "What this shows"],
      ["Der Überblick beantwortet drei Fragen auf einen Blick, immer für die letzten 30 Tage, unabhängig vom Zeitraum im Filter: Wie läuft es insgesamt? Was ist jetzt auffällig? Was hat das letzte Update verändert? Kunde, App und Plattform aus dem Filter gelten auch hier.",
        "The overview answers three questions at a glance, always for the last 30 days regardless of the period in the filter: how is it going overall? Which app needs attention? What did the latest update change? Customer, app and platform from the filter apply here too."],
      ["Wie läuft es insgesamt: Die Sterne sind die offizielle Store-Bewertung, über alle Apps der Auswahl nach Anzahl der Bewertungen gewichtet. Der Pfeil zeigt die Veränderung gegenüber dem gespeicherten Stand von vor 30 Tagen, sobald es ihn gibt. Darunter stehen die neuen Rezensionen der letzten 30 Tage und ob sie im Schnitt besser oder schlechter waren als die 30 Tage davor; mit weniger als drei Rezensionen auf einer Seite gibt es keinen Vergleich.",
        "How is it going overall: the stars are the official store rating, weighted across all apps in the selection by number of ratings. The arrow shows the change against the stored snapshot from 30 days ago, once there is one. Below are the new reviews of the last 30 days and whether they were on average better or worse than the 30 days before; with fewer than three reviews on either side there is no comparison."],
      ["Ampel je App (Warnung von heute, feste Fenster von 7 und 30 Tagen, anders als das Diagramm „Alle Apps auf einen Blick“ im Reiter Diagramme, das die Lage über den Zeitraum im Filter zeigt): Rot heißt handeln, gelb heißt ansehen, grün heißt nichts zu tun. Rot gibt es bei drei oder mehr Rezensionen mit 1 oder 2 Sternen in sieben Tagen, bei mindestens 2 Abstürzen je 1000 Nutzungen oder wenn sich die Absturzrate gegenüber den 30 Tagen davor verdoppelt hat. Gelb gibt es bei einer negativen Rezension in sieben Tagen, bei einer offenen negativen Rezension ohne Antwort, bei anderthalbfacher Absturzrate oder wenn die App im Store unter 4 Sternen steht. Absturzregeln gelten erst ab 500 Nutzungen, sonst ist die Zahl Zufall. Die Spalte „Warum“ nennt den Grund.",
        "Traffic light per app (today’s warning, fixed windows of 7 and 30 days, unlike the chart “All apps at a glance” on the Charts tab, which shows the position over the period in the filter): red means act, yellow means look, green means nothing to do. Red is given for three or more reviews with 1 or 2 stars in seven days, for at least 2 crashes per 1,000 uses, or when the crash rate has doubled compared with the 30 days before. Yellow is given for one negative review in seven days, for an open negative review without a reply, for a crash rate up by half, or when the app is below 4 stars in the store. Crash rules only apply from 500 uses, otherwise the figure is chance. The “Why” column names the reason."],
      ["Was das letzte Update verändert hat: die jüngste bekannte Veröffentlichung in der Auswahl mit 14 Tagen davor und danach, wie im Bereich „Was ein Update verändert hat“. Liegt das Update weniger als 14 Tage zurück, ist die Zeit danach noch unvollständig; das steht dann dabei.",
        "What the latest update changed: the most recent known release in the selection with 14 days before and after, as in the section “What an update changed”. If the update is less than 14 days ago, the time after is still incomplete; this is stated."],
      ["Unauffällige Apps sind zu einer Zeile zusammengefasst und lassen sich einblenden. „Mehr Zahlen anzeigen“ unter dem Überblick öffnet die ausführlichen Tabellen (wichtigste Zahlen je App, Kassen-Vergleich, alle Updates).",
        "Unremarkable apps are combined into one row and can be shown. “Show more figures” below the overview opens the detailed tables (key figures per app, customer comparison, all updates)."],
      ["Drucken und Kopieren: Oben in der Karte macht „Monatsbericht drucken“ aus den letzten 30 Tagen eine druckfertige Zusammenfassung (Lage, Ampel, Maßnahmen, mit KI die Stimmen der Nutzer), im Druckdialog auch als PDF. „In Zwischenablage“ kopiert denselben Bericht formatiert, zum Einfügen in Word, Mail, Teams oder Jira. Jeder Ausdruck beginnt mit Datum und Uhrzeit und dem eingestellten Filter.",
        "Print and copy: at the top of the card, “Print monthly report” turns the last 30 days into a print-ready summary (situation, traffic light, actions, with AI what users say), also as PDF via the print dialog. “Copy to clipboard” copies the same report with formatting, to paste into Word, mail, Teams or Jira. Every printout starts with date and time and the filter in use."],
      ["Mit KI: Unter den drei Karten steht „Das sollten wir tun“, eine Liste von höchstens fünf Punkten aus Ampel, offenen Rezensionen und den Maßnahmenvorschlägen der KI, jeder mit Beleg (Zahl oder Zitat) und Sprung in den Bereich, in dem man ihn prüft. In der Ampeltabelle öffnet „Was sagen die Nutzer“ je App die Zusammenfassung der KI in drei Sätzen mit Zitaten. „Monatsbericht drucken“ bringt Lage, Ampel und Maßnahmen auf eine Seite.",
        "With AI: below the three cards is “What we should do”, a list of at most five points from the traffic light, open reviews and the AI’s suggested measures, each with evidence (a figure or quote) and a jump to the section where it can be checked. In the traffic light table, “What users say” opens the AI’s three-sentence summary per app with quotes. “Print monthly report” puts status, traffic light and measures on one page."]],
    steckbrief: [["Was hier steht", "What this shows"],
      ["Hier sehen Sie für jede App die wichtigsten Zahlen in einer Zeile. Gezählt werden nur die Rezensionen, die zu Ihrer Auswahl oben im Filter passen.",
        "Here you see the most important figures for each app in one row. Only the reviews that match your selection in the filter above are counted."],
      ["Faire Note: Das ist der Sternedurchschnitt, aber mit einer Vorsichtsregel. Eine App mit nur drei Rezensionen zu je 5 Sternen hätte sonst eine glatte 5,0 und stünde vor einer App mit 200 Rezensionen und 4,6. Das wäre unfair. Darum wird eine App mit wenigen Rezensionen etwas Richtung Mittelmaß gezogen. Je mehr Rezensionen, desto mehr zählt der echte Durchschnitt. Das ± dahinter sagt, wie verlässlich die Note ist. ±0,1 heißt: sehr verlässlich. ±0,8 heißt: nur eine grobe Schätzung.",
        "Fair rating: this is the star average, but with a safety rule. An app with only three 5-star reviews would otherwise score a flat 5.0 and rank above an app with 200 reviews at 4.6. That would be unfair. So an app with few reviews is pulled a little towards the middle. The more reviews, the more the real average counts. The ± behind it says how reliable the rating is. ±0.1 means very reliable. ±0.8 means only a rough guess."],
      ["Zufrieden minus unzufrieden: Wie viel Prozent der Rezensionen sind zufrieden (4 und 5 Sterne), wie viel Prozent sind unzufrieden (1 und 2 Sterne)? Die Zahl ist der Unterschied. Beispiel: 70 % zufrieden und 20 % unzufrieden ergibt +50. Bestenfalls +100, schlimmstenfalls −100. Diese Zahl ist oft ehrlicher als der Durchschnitt, weil die meisten Menschen entweder 5 Sterne oder 1 Stern geben und fast nie 3.",
        "Happy minus unhappy: what percentage of reviews are happy (4 and 5 stars), what percentage are unhappy (1 and 2 stars)? The figure is the difference. Example: 70 % happy and 20 % unhappy gives +50. At best +100, at worst −100. This figure is often more honest than the average, because most people give either 5 stars or 1 star and almost never 3."],
      ["Trend: Läuft es gerade besser oder schlechter als sonst? Dafür werden die Rezensionen aus dem gewählten Zeitraum mit allen Rezensionen der App verglichen. Grün heißt: zuletzt besser als sonst. Rot heißt: zuletzt schlechter als sonst.",
        "Trend: is it going better or worse than usual right now? The reviews from the selected period are compared with all reviews of the app. Green means recently better than usual. Red means recently worse than usual."],
      ["Anteil 1 ★: Wie viel Prozent der Rezensionen geben nur einen Stern. Beschwerden: Wie viele negative Rezensionen kommen auf 1000 neue Installationen. Das gibt es nur für Apple, weil nur Apple sagt, wie oft die App installiert wurde. Antwortquote: Auf wie viel Prozent der Rezensionen hat der Support geantwortet.",
        "Share 1 ★: what percentage of reviews give just one star. Complaints: how many negative reviews come per 1,000 new installations. Apple only, because only Apple tells how often the app was installed. Reply rate: what percentage of reviews support has answered."],
      ["Blasse Zeilen mit ⚠ haben zu wenige Rezensionen. Die Zahlen dort sagen noch nichts über die App aus. Bitte nicht überbewerten.",
        "Pale rows with ⚠ have too few reviews. The figures there say nothing about the app yet. Please do not read too much into them."],
      ["Mit KI kommt die Spalte „Drohen zu wechseln“ dazu: Anteil der analysierten Rezensionen im Zeitraum, in denen Nutzer Wechsel oder Löschen ankündigen. Das ist ein Frühwarnsignal, das die Store-Note erst Wochen später zeigt.",
        "With AI, the column “Threaten to leave” is added: share of analysed reviews in the period in which users announce leaving or deleting. It is an early warning that the store rating shows only weeks later."]],
    storewerte: [["Was hier steht", "What this shows"],
      ["Das sind die Sterne, die Apple selbst im App Store anzeigt, für jedes Land einzeln: der Durchschnitt und wie viele Menschen bewertet haben, seit es die App gibt. Genau diese Zahl sieht auch ein Kunde, wenn er die App im Store sucht.",
        "These are the stars Apple itself shows in the App Store, for each country separately: the average and how many people have rated since the app exists. This is exactly the figure a customer sees when looking up the app in the store."],
      ["Wichtig zu wissen: Im Store kann man Sterne vergeben, ohne einen Text zu schreiben. Das machen sehr viele. Apple gibt diese reinen Sterne-Bewertungen aber nicht einzeln heraus, nur die Rezensionen mit Text. Der ganze übrige Bericht beruht darum nur auf den Rezensionen mit Text. Deshalb ist die Store-Note hier eine andere als die Note bei „Die wichtigsten Zahlen je App“. Beide stimmen, sie zählen nur verschiedene Dinge.",
        "Good to know: in the store you can give stars without writing a text. Very many people do. But Apple does not release these plain star ratings individually, only the reviews with text. The whole rest of the report is therefore based only on reviews with text. That is why the store rating here differs from the rating in “Key figures per app”. Both are correct, they just count different things."],
      ["Die Zahlen werden bei jedem Abruf aus dem App Store gelesen und mit Datum gespeichert. Ist oben ein Zeitraum gewählt, zeigen zwei zusätzliche Spalten, wie viele Bewertungen in diesem Zeitraum neu dazugekommen sind und wie viele Sterne sie im Schnitt hatten. Das wird aus den gespeicherten Ständen berechnet und geht erst ab dem Tag, an dem die Aufzeichnung begonnen hat. Die Sterne aus dem Filter wirken hier nicht.",
        "The figures are read from the App Store on every run and stored with their date. If a period is selected above, two extra columns show how many ratings were added in that period and their average stars. This is calculated from the stored snapshots and only works from the day recording began. The star filters do not apply here."]],
    latestver: [["Was hier steht", "What this shows"],
      ["Für jede App: Welche Version steht gerade im App Store, seit wann, und was steht dort unter „Neue Funktionen“? Stand ist der letzte Abruf.",
        "For each app: which version is currently in the App Store, since when, and what does it say under “What's new”? As of the last run."],
      ["Wozu das gut ist: Jede Rezension bezieht sich auf die Version, die der Nutzer gerade hatte. Wenn Sie eine Beschwerde lesen, sehen Sie hier sofort, ob diese Version noch aktuell ist. Vielleicht gab es seitdem ein Update, das das Problem schon behoben hat.",
        "Why this is useful: every review refers to the version the user had at the time. When you read a complaint, you see here at once whether that version is still current. Maybe there has been an update since that already fixed the problem."],
      ["Jede neue Version wird mit ihrem Datum gemerkt. Daraus entstehen die kleinen Kreise unter den Diagrammen und die Zuordnung der Rezensionen zu Versionen im Vergleich nach Version und bei „Was ein Update verändert hat“.",
        "Every new version is remembered with its date. This feeds the small circles under the charts and the assignment of reviews to versions in the customer comparison and in “What an update changed”."]],
    diagramme: [["Was hier steht", "What this shows"],
      ["Eine Karte, mehrere Diagramme. Mit der Auswahlbox oder den Pfeilen wechseln Sie zwischen ihnen. Alle Diagramme richten sich nach dem Filter oben. Sind Apple und Google gewählt, stehen beide nebeneinander.",
        "One card, several charts. Use the selection box or the arrows to switch between them. All charts follow the filter above. With Apple and Google selected, both appear side by side."],
      ["„Alle Apps auf einen Blick“: Jede App ist ein Kreis. Je weiter rechts der Kreis, desto öfter stürzt die App ab. Je weiter oben, desto bessere Sterne. Um die Apps unten rechts im roten Feld sollte man sich kümmern: Sie stürzen oft ab und bekommen schlechte Sterne. Das Diagramm zeigt die Lage über den Zeitraum im Filter (Durchschnitt der Rezensionen und Absturzrate im Zeitraum, feste Grenzen 4 ★ und 2 Abstürze je 1000 Sitzungen). Die Ampel im Überblick ist dagegen die Warnung von heute: Sie schaut auf die letzten 7 und 30 Tage, auf offene Rezensionen und auf die offizielle Store-Note. Darum kann dieselbe App im Diagramm grün und in der Ampel rot sein, oder umgekehrt; das ist kein Fehler, sondern eine andere Frage.",
        "“All apps at a glance”: each app is a circle. The further right the circle, the more often the app crashes. The higher up, the better the stars. The apps bottom right in the red area deserve attention: they crash often and get poor stars. The chart shows the position over the period in the filter (average of the reviews and crash rate in the period, fixed limits 4 ★ and 2 crashes per 1,000 sessions). The traffic light on the overview is today’s warning instead: it looks at the last 7 and 30 days, at open reviews and at the official store rating. So the same app can be green in the chart and red in the traffic light, or the other way round; that is not an error but a different question."],
      ["Die anderen Diagramme zeigen den Verlauf über die Zeit, nach Wochen oder Monaten: wie viele Rezensionen mit wie vielen Sternen, der Durchschnitt, Abstürze, Nutzung, Downloads. Die Leiste darunter zeigt jede neue Version als nummerierten Kreis. Fahren Sie mit der Maus darüber, sehen Sie Version, Datum und wie es danach weiterging.",
        "The other charts show the course over time, by week or month: how many reviews with how many stars, the average, crashes, usage, downloads. The bar below shows each new version as a numbered circle. Hover over it to see version, date and what happened afterwards."],
      ["Maus über einen Balken oder Punkt zeigt die genauen Zahlen, auf dem Handy antippen. Das Symbol ⤢ zeigt das Diagramm groß, zum Beispiel für eine Besprechung.",
        "Hover a bar or point for exact figures, tap on a phone. The ⤢ symbol shows the chart large, for example for a meeting."],
      ["Drucken und Kopieren: „Bericht drucken“ in der Kopfzeile druckt zehn Diagramme in fester Reihenfolge (Alle Apps auf einen Blick, Entwicklung, Sterne-Verteilung, Rezensionen pro App, Zufrieden minus unzufrieden, Downloads pro Woche und nach Land, Abstürze und Bewertung, Sitzungen pro Woche, Wochenübersicht), Apple und Google untereinander. Fehlt eine Plattform, etwa Stabilität für Google, steht „Nur für iOS“ bzw. „Nur für Android“ daneben; fehlen beide, fehlt das Diagramm. „In Zwischenablage“ kopiert dasselbe, Diagramme als Bilder.",
        "Print and copy: “Print report” in the header prints ten charts in fixed order (all apps at a glance, trend, star distribution, reviews per app, happy minus unhappy, downloads per week and by country, crashes and rating, sessions per week, weekly overview), Apple and Google one below the other. If a platform is missing, such as stability for Google, “iOS only” or “Android only” is shown next to the title; if both are missing, the chart is left out. “Copy to clipboard” copies the same, charts as images."]],
    fragen: [["Was hier steht", "What this shows"],
      ["Sechs Fragen, die Auftraggeber und Geschäftsführung oft stellen, je mit einem Satz als Antwort. Alle Zahlen gelten für den Zeitraum im Filter, ohne Zeitraum für die letzten 90 Tage, und für die gewählten Kunden, Apps und Plattformen. Store-Zahlen und Sitzungen liefert bisher nur Apple.",
        "Six questions that clients and management often ask, each with a one-sentence answer. All figures cover the period in the filter, or the last 90 days without one, and the selected customers, apps and platforms. Store figures and sessions are only provided by Apple so far."],
      ["Laden Store-Besucher die App: Wie oft die App im Store gezeigt wurde (in Suchergebnissen, Listen oder auf ihrer Seite) und wie oft sie danach geladen wurde, als Anteil. Apple zählt hier jede Einblendung, auch mehrfach beim selben Menschen; der Wert ist deshalb niedriger als die Konversionsrate in App Store Connect, eignet sich aber gut zum Vergleich der Apps untereinander. Liegt eine App bei gleichem Code deutlich darunter, liegt es meist am Store-Auftritt oder daran, wie die App beworben wird.",
        "Do store visitors download the app: how often the app was shown in the store (in search results, lists or on its page) and how often it was then downloaded, as a share. Apple counts every impression here, including repeated ones for the same person, so the figure is lower than the conversion rate in App Store Connect, but it works well for comparing the apps with each other. If an app with the same code is clearly lower, the cause is usually the store listing or how the app is promoted."],
      ["Woher kommen die Downloads: über welchen Weg neue Nutzer die App zum ersten Mal geladen haben, etwa über die Suche im Store oder über einen Link auf einer Webseite. Kommt bei einer App fast nichts über Webseiten, verlinkt der Anbieter die App vermutlich nicht. Behalten die Nutzer die App: wie viele Löschungen auf 100 Installationen kommen. Wie schnell kommen Nutzer auf die neueste Version: welcher Teil der Nutzung der letzten sieben Tage schon auf der neuesten Version läuft. Welche Systemversionen sind im Einsatz: hilft bei der Entscheidung, ab welcher iOS-Version die App noch laufen muss.",
        "Where do downloads come from: the route by which new users first downloaded the app, for example via store search or via a link on a website. If almost nothing comes from websites for an app, the provider probably does not link to it. Do users keep the app: how many deletions there are per 100 installs. How fast do users move to the latest version: what part of the use in the last seven days already runs on the latest version. Which OS versions are in use: helps decide from which iOS version the app still has to run."],
      ["Liegt es an der App oder am Anbieter: Die negativen Rezensionen (1 und 2 Sterne) werden über feste Wortlisten Themen zugeordnet, und jedes Thema gehört entweder zur App (etwa Abstürze, Bedienung) oder zum Anbieter (etwa Freischaltung, Service, Einreichung). Das ist eine Wortzählung, keine Bedeutungsanalyse: Sie zeigt, wo man lesen sollte, nicht, was dort steht.",
        "Is it the app or the provider: negative reviews (1 and 2 stars) are assigned to topics via fixed word lists, and each topic belongs either to the app (for example crashes, usability) or to the provider (for example activation, service, submissions). This is word counting, not an analysis of meaning: it shows where to read, not what it says."],
      ["„Sichere Aussage“ heißt: Es gibt genug Daten, um die Zahl ernst zu nehmen (zum Beispiel mindestens 1000 Einblendungen und 30 Downloads, 100 Installationen, 500 Sitzungen oder 30 negative Rezensionen mit Thema). „Hinweis“ heißt: Die Zahl stimmt, kann aber Zufall sein.",
        "“Reliable” means: there is enough data to take the figure seriously (for example at least 1,000 impressions and 30 downloads, 100 installs, 500 sessions or 30 negative reviews with a topic). “Indication” means: the figure is correct but may be chance."]],
    appvgl: [["Was hier steht", "What this shows"],
      ["Eine Zeile je Apple-App in der Auswahl mit sechs Zahlen für den Zeitraum im Filter (ohne Zeitraum: letzte 90 Tage). Die letzte Zeile zeigt den Median, also den mittleren Wert aller Apps. Ein Pfeil ▲ heißt deutlich besser, ▼ deutlich schlechter als der Median; „deutlich“ ist ein Viertel Abweichung, bei der Store-Note 0,2 Sterne, beim Update-Tempo 10 Prozentpunkte.",
        "One row per Apple app in the selection with six figures for the period in the filter (without a period: last 90 days). The last row shows the median, the middle value of all apps. An arrow ▲ means clearly better, ▼ clearly worse than the median; “clearly” means a quarter difference, 0.2 stars for the store rating, 10 percentage points for update speed."],
      ["Die Spalten: Downloads je 1000 der Zielgruppe (erste Downloads im Zeitraum geteilt durch die Größe der Zielgruppe, die für jede App von Hand eingetragen wird, zum Beispiel die Zahl der Kunden des Anbieters); Einblendungen, die zum Download führen; die offizielle Store-Note; Abstürze je 1000 Sitzungen; Löschungen je 100 Installationen; Anteil der Sitzungen der letzten sieben Tage auf der neuesten Version.",
        "The columns: downloads per 1,000 of the target group (first downloads in the period divided by the target group size, entered by hand for each app, for example the provider’s number of customers); impressions leading to a download; the official store rating; crashes per 1,000 sessions; deletions per 100 installs; share of sessions in the last seven days on the latest version."],
      ["Wozu das gut ist: Laufen die Apps auf demselben Code, zeigt eine Abweichung vom Median, wo der Unterschied beim Anbieter liegt, etwa im Store-Auftritt, in der Werbung oder in den eigenen Abläufen. Blasse Werte haben zu wenig Daten für ein Urteil und bekommen keinen Pfeil.",
        "Why this is useful: if the apps run on the same code, a difference from the median shows where the difference lies with the provider, for example in the store listing, the promotion or its own processes. Pale values have too little data for a verdict and get no arrow."],
      ["App-Bericht drucken: fasst eine App auf einer Seite zusammen, mit Rangplatz je Zahl („Platz 4 von 20“), Median, den auffälligen Abweichungen und Hinweisen. Verglichen wird mit allen Apple-Apps der im Filter gewählten Kunden; die anderen Apps erscheinen ohne Namen. Gedruckt wird über den Druckdialog des Browsers, dort lässt sich auch ein PDF speichern.",
        "Print app report: summarises one app on one page, with a rank per figure (“rank 4 of 20”), the median, the notable differences and suggestions. The comparison uses all Apple apps of the customers selected in the filter; the other apps appear without names. Printing uses the browser’s print dialog, which can also save a PDF."],
      ["Mit KI kommen vier Spalten dazu: Anteil verärgerter oder resignierter Nutzer laut KI im Zeitraum, Hauptlob, Hauptkritik und Einschätzung (Produkt-, Update- oder Anbieterproblem) aus der Zusammenfassung. Laufen Apps auf gleichem Code, zeigt das, ob ein Problem beim Anbieter liegt (Service, Freischaltung) oder in der App. Die Einschätzung ist ein Vorschlag der KI, Sterne und Anzahlen sind Messwerte.",
        "With AI, four columns are added: share of annoyed or resigned users according to the AI in the period, main praise, main criticism and assessment (product, update or provider problem) from the summary. If apps run on the same code, this shows whether a problem lies with the provider (service, activation) or in the app. The assessment is an AI suggestion; stars and counts are measurements."],
      ["Drucken und Kopieren: „Bericht drucken“ oben in dieser Karte druckt den ganzen Reiter: Apps im Vergleich, Sterne im App Store und Neueste Version im Store; „In Zwischenablage“ kopiert dasselbe formatiert für Word, Mail, Teams oder Jira. Der App-Bericht (eine App gegen die anderen, ohne Namen) hat weiterhin seinen eigenen Knopf.",
        "Print and copy: “Print report” at the top of this card prints the whole tab: apps compared, stars in the App Store and latest version in the store; “Copy to clipboard” copies the same with formatting for Word, mail, Teams or Jira. The app report (one app against the others, unnamed) keeps its own button."]],
    stab: [["Was hier steht", "What this shows"],
      ["Wie oft stürzt die App ab? Apple meldet für jeden Tag, wie oft die App abgestürzt ist und wie oft sie benutzt wurde. Daraus entsteht eine einfache Zahl: Abstürze je 1000 Nutzungen. So kann man eine App mit 500 Nutzern fair mit einer App mit 50.000 Nutzern vergleichen.",
        "How often does the app crash? Apple reports for every day how often the app crashed and how often it was used. This gives one simple figure: crashes per 1,000 uses. That way an app with 500 users can be fairly compared with an app with 50,000 users."],
      ["Apple kennt diese Zahlen nur von einem Teil der Nutzer, nämlich von denen, die beim Einrichten ihres iPhones zugestimmt haben, solche Daten zu teilen. Das sind meist 20 bis 30 von 100. Die reinen Stückzahlen sind deshalb zu klein. Die Zahl „Abstürze je 1000 Nutzungen“ stimmt trotzdem, weil Abstürze und Nutzungen von denselben Menschen stammen.",
        "Apple knows these figures only from some users, namely those who agreed to share such data when setting up their iPhone. That is usually 20 to 30 out of 100. The raw counts are therefore too small. The figure “crashes per 1,000 uses” is still right, because crashes and uses come from the same people."],
      ["Faustregel: Weniger als 1 Absturz je 1000 Nutzungen ist gut. Mehr als 5 ist ein Problem. Das wichtigste Warnzeichen ist ein Sprung nach oben direkt nach einem Update. Der Bereich „Was ein Update verändert hat“ zeigt das für jede Version.",
        "Rule of thumb: fewer than 1 crash per 1,000 uses is good. More than 5 is a problem. The most important warning sign is a jump right after an update. The section “What an update changed” shows that for each version."],
      ["Für Android-Apps gibt es diese Zahlen hier nicht. Der Bereich bleibt dann leer.",
        "For Android apps these figures are not available here. The section then stays empty."],
      ["Drucken und Kopieren: „Bericht drucken“ oben in der Karte druckt Kennzahlen und die Tabellen nach Version, System und Gerät; „In Zwischenablage“ kopiert dasselbe formatiert für Word, Mail, Teams oder Jira. Beides nur, wenn es Stabilitätsdaten für die Auswahl gibt.",
        "Print and copy: “Print report” at the top of the card prints the key figures and the tables by version, system and device; “Copy to clipboard” copies the same with formatting for Word, mail, Teams or Jira. Both only when stability data exists for the selection."]],
    vergleich: [["Was hier steht", "What this shows"],
      ["Eine Tabelle: Jede Zeile ist eine App, jede Spalte eine App-Version. In jedem Feld steht der Sternedurchschnitt und in Klammern, wie viele Rezensionen diese App zu dieser Version bekommen hat. Die letzte Zeile zeigt den mittleren Wert über alle Apps der Spalte. So bleibt die Tabelle auch bei vielen Apps übersichtlich: Sie wird länger, nicht breiter.",
        "A table: each row is an app, each column an app version. Each cell shows the star average and, in brackets, how many reviews that app received for that version. The last row shows the middle value across all apps in the column. This keeps the table readable with many apps: it grows longer, not wider."],
      ["Wozu das gut ist: Laufen mehrere Apps auf demselben Code, nur mit eigenem Namen und eigenen Inhalten, lässt sich hier trennen, was am Code liegt und was am Anbieter. Hat eine App bei derselben Version deutlich schlechtere Sterne als die anderen, liegt es nicht am Code. Dann lohnt sich ein Blick auf das, was nur diese App betrifft: ihre Inhalte, wie der Anbieter sie seinen Nutzern vorgestellt hat, seine Abläufe und seine Kommunikation. Fallen alle Apps bei einer Version gemeinsam ab, liegt es an der Version.",
        "Why this is useful: when several apps run on the same code, only with their own name and content, this separates what is down to the code from what is down to the provider. If one app has clearly worse stars than the others on the same version, the code is not the cause. Then look at what concerns only that app: its content, how the provider introduced it to its users, the provider’s processes and communication. If all apps drop together on one version, the version is the cause."],
      ["Eine Einschränkung: Apple sagt bei einer Rezension nicht, mit welcher Version sie geschrieben wurde. Darum gilt hier: Eine Rezension gehört zu der Version, die an diesem Tag im Store war. Das klappt erst ab dem Tag, an dem dieser Bericht angefangen hat, die Versionen mitzuschreiben. Bei Google steht die Version direkt in der Rezension.",
        "One limitation: Apple does not say which version a review was written with. So the rule here is: a review belongs to the version that was in the store on that day. This only works from the day this report started recording versions. For Google the version is part of the review."],
      ["Gezeigt werden die zehn Versionen mit den meisten Rezensionen. Blasse Felder haben weniger als fünf Rezensionen, das reicht für kein Urteil. Damit der Vergleich erscheint, müssen im Filter mindestens zwei Apps gewählt sein.",
        "The ten versions with the most reviews are shown. Pale cells have fewer than five reviews, not enough for a verdict. For the comparison to appear, at least two apps must be selected in the filter."],
      ["Mit KI steht unter der Tabelle, welche Beschwerden nur in der neuesten Version vorkommen und in älteren fehlen: der schnellste Hinweis darauf, dass ein Update etwas kaputt gemacht hat. Vorsicht bei kleinen Zahlen: Eine einzelne Rezension macht noch keine Häufung.",
        "With AI, below the table are the complaints that occur only in the latest version and are missing in older ones: the quickest hint that an update broke something. Beware of small numbers: a single review does not make a cluster."]],
    release: [["Was hier steht", "What this shows"],
      ["Hat ein Update etwas besser oder schlechter gemacht? Für jede neue Version wird die Zeit davor mit der gleich langen Zeit danach verglichen, wahlweise 14 oder 30 Tage: Wie viele Rezensionen, welcher Sternedurchschnitt, wie viele negative Rezensionen, wie viele Abstürze. Immer als „vorher → nachher“.",
        "Did an update make things better or worse? For each new version the time before is compared with the same length of time after, 14 or 30 days: how many reviews, which star average, how many negative reviews, how many crashes. Always as “before → after”."],
      ["So lesen Sie es: Die Spalte Δ zeigt, wie sich der Sternedurchschnitt verändert hat. Grün heißt besser geworden, rot heißt schlechter geworden, jeweils ab 0,3 Sternen Unterschied. Steigen die Abstürze nach dem Update, ist das Update sehr wahrscheinlich schuld.",
        "How to read it: the Δ column shows how the star average has changed. Green means improved, red means worsened, each from 0.3 stars difference. If crashes rise after the update, the update is very likely to blame."],
      ["Nicht erschrecken: Direkt nach einem Update kommen fast immer mehr Rezensionen als sonst. Die App bittet nach dem Update um eine Bewertung, und wer sich über eine Änderung ärgert, schreibt sofort. Entscheidend ist, ob der Durchschnitt fällt, nicht, dass es mehr Rezensionen werden.",
        "Do not be alarmed: right after an update there are almost always more reviews than usual. The app asks for a rating after updating, and whoever is annoyed by a change writes immediately. What matters is whether the average falls, not that there are more reviews."],
      ["Das Datum kommt aus dem App Store. Ein ≈ bedeutet: geschätzt, weil der Bericht diese Version nicht selbst gesehen hat. Blasse Zeilen mit ⚠ haben auf einer Seite weniger als fünf Rezensionen. Gezeigt werden nur Updates aus dem gewählten Zeitraum. Die Sterne aus dem Filter wirken hier nicht, weil sonst der Vergleich vorher und nachher keinen Sinn ergibt.",
        "The date comes from the App Store. A ≈ means estimated, because the report did not see this version itself. Pale rows with ⚠ have fewer than five reviews on one side. Only updates from the selected period are shown. The star filters do not apply here, because the before and after comparison would otherwise make no sense."],
      ["Mit KI kommt die Spalte „Beschwerden (KI)“ dazu: Kernaussagen negativer oder dringender Rezensionen im Fenster nach dem Update, die im Fenster davor fehlten („neu“), und solche, die davor vorkamen und danach fehlen („verschwunden“). Das ist die Wirkungskontrolle: Hat das Update ein Problem behoben oder eines gebracht? Die Kernaussagen formuliert die KI je Rezension; gleiche Formulierungen werden zusammengezählt, ähnliche nicht.",
        "With AI, the column “Complaints (AI)” is added: core statements of negative or urgent reviews in the window after the update that were missing in the window before (“new”), and those that occurred before and are missing after (“gone”). This is the effect check: did the update fix a problem or bring one? The AI phrases the core statements per review; identical phrasings are added up, similar ones are not."]],
    themen: [["Was hier steht", "What this shows"],
      ["Themen: Worüber schreiben die Nutzer? Für jedes Thema gibt es eine feste Liste von Wörtern. Für „Anmeldung“ sind das zum Beispiel Login, Passwort, anmelden. Steht eines dieser Wörter in einer Rezension, zählt sie zu dem Thema. Eine Rezension kann zu mehreren Themen zählen. Der Schalter „nur negative“ zeigt, worüber sich die unzufriedenen Nutzer beschweren.",
        "Topics: what do users write about? Each topic has a fixed list of words. For “login” these are, for example, login, password, sign in. If one of these words appears in a review, it counts for the topic. A review can count for several topics. The “negative only” switch shows what unhappy users complain about."],
      ["Klick auf ein Thema: Der Balken wird hervorgehoben, und direkt darunter erscheint die Liste der Rezensionen zu diesem Thema. Ein Klick auf eine Zeile öffnet die Rezension. Der übrige Bericht ändert sich dadurch nicht. Zurück: noch einmal auf denselben Balken klicken oder auf „Liste schließen“. Wer den ganzen Bericht auf ein Thema beschränken will, wählt es oben im Filter bei „Thema“ (unter „Erweitert“). Nur der Filter oben wirkt auf alle Reiter.",
        "Clicking a topic: the bar is highlighted, and the list of reviews on this topic appears right below. Click a row to open the review. The rest of the report does not change. To go back, click the same bar again or “Close list”. To limit the whole report to one topic, choose it under “Topic” in the filter above (under “Advanced”). Only the filter above affects all tabs."],
      ["Woher die Themen kommen: Die Wortlisten stehen in der Datei config/themen.json und enthalten deutsche und englische Begriffe, damit Rezensionen in beiden Sprachen erkannt werden. Sie lassen sich dort ergänzen; danach den Bericht neu erzeugen. Das Diagramm „Themen der Rezensionen“ im Reiter Diagramme nutzt dieselben Listen und zeigt dieselben Zahlen, nur ohne die Liste der Rezensionen.",
        "Where the topics come from: the word lists live in the file config/themen.json and contain German and English terms, so reviews in both languages are recognised. You can add terms there and then rebuild the report. The chart “Review topics” on the Charts tab uses the same lists and shows the same figures, just without the list of reviews."],
      ["Typische Wörter: Welche Wörter kommen in schlechten Rezensionen auffällig oft vor, in guten aber kaum? Und umgekehrt? So sehen Sie, ohne alles zu lesen, was die Unzufriedenen beschäftigt. Füllwörter wie „und“, „aber“, „nicht“ werden weggelassen. Fahren Sie mit der Maus über ein Wort, sehen Sie, in wie vielen guten und schlechten Rezensionen es steht.",
        "Typical words: which words appear strikingly often in bad reviews but hardly in good ones? And the other way round? This shows you, without reading everything, what bothers the unhappy users. Filler words like “and”, “but”, “not” are left out. Hover over a word to see how many good and bad reviews contain it."],
      ["Zuletzt häufiger: Wörter, die in den letzten 30 Tagen deutlich öfter vorkommen als in der Zeit davor. Taucht hier plötzlich „Absturz“ oder „Anmeldung“ auf, ist das ein frühes Warnzeichen für ein neues Problem, oft nach einem Update.",
        "Recently more frequent: words that appear clearly more often in the last 30 days than before. If “crash” or “login” suddenly shows up here, that is an early warning sign of a new problem, often after an update."],
      ["Das alles ist reines Wörterzählen, ohne künstliche Intelligenz. Das ist nachvollziehbar, aber grob: Ironie, Tippfehler und Umschreibungen erkennt es nicht. Im Zweifel lesen Sie die Rezensionen selbst.",
        "All of this is plain word counting, without artificial intelligence. That is easy to follow but coarse: it does not recognise irony, typos or paraphrases. When in doubt, read the reviews yourself."],
      ["Drucken und Kopieren: „Bericht drucken“ oben in der Karte druckt die Gesamtbewertung mit Verteilung und Kennzahlen, darunter die Themen einmal für alle und einmal nur für negative Rezensionen und, mit KI, die meistgewünschten Funktionen; die Wortlisten bleiben weg. „In Zwischenablage“ kopiert denselben Bericht formatiert für Word, Mail, Teams oder Jira.",
        "Print and copy: “Print report” at the top of the card prints the overall rating with distribution and key figures, below the topics once for all and once for negative reviews only and, with AI, the most requested features; the word lists are left out. “Copy to clipboard” copies the same report with formatting for Word, mail, Teams or Jira."],
      ["Mit KI folgen drei Knöpfe, die je ein Overlay öffnen: „Themen laut KI“ sind Schlagwörter, die die KI je Rezension frei vergibt, mit Anzahl, negativem Anteil und ob das Thema schon in der Themenliste steht; „Vorschläge für die Themenliste“ kommen erst nach Bestätigung in config/themen.json (./ratings.sh ai-themes --accept NR, Menü KI-Analyse); „Meistgewünschte Funktionen“ zählt die Kernaussagen der Rezensionen mit Stimmung „Wunsch“, mit Trend gegenüber den 90 Tagen davor. Die regelbasierten Themen oben bleiben die Referenz, weil sie für alle Rezensionen gleich und nachvollziehbar sind.",
        "With AI, three buttons follow, each opening an overlay: “Topics according to the AI” are keywords the AI freely assigns per review, with count, negative share and whether the topic already exists in the topic list; “Suggestions for the topic list” enter config/themen.json only after confirmation (./ratings.sh ai-themes --accept NR, menu AI analysis); “Most requested features” counts the core statements of reviews with sentiment “wish”, with a trend against the 90 days before. The rule-based topics above remain the reference because they apply equally and traceably to all reviews."]],
    antworten: [["Was hier steht", "What this shows"],
      ["Wie gut kümmert sich der Support um die Rezensionen? Antwortquote: Auf wie viel Prozent der Rezensionen wurde im Store geantwortet, einmal für alle und einmal nur für die mit 1 und 2 Sternen. Antwortzeit: Wie viele Tage vergehen zwischen Rezension und Antwort. Gezeigt wird der typische Fall. Einzelne sehr späte Antworten verfälschen die Zahl nicht.",
        "How well does support look after the reviews? Reply rate: what percentage of reviews got a reply in the store, once for all and once only for those with 1 and 2 stars. Reply time: how many days pass between review and reply. The typical case is shown. Single very late replies do not distort the figure."],
      ["Nach Antwort verbessert: Wie oft hat ein Nutzer nach der Antwort seine Sterne nach oben geändert? Das ist der eigentliche Erfolg einer Antwort. Die Zahl ist eher zu niedrig als zu hoch, weil der Bericht eine Änderung nur bemerkt, wenn er sie beim nächsten vollständigen Abruf sieht.",
        "Improved after reply: how often did a user raise their stars after the reply? That is the real success of a reply. The figure is more likely too low than too high, because the report only notices a change when it sees it during the next full run."],
      ["Offene negative Rezensionen: Rezensionen mit 1 oder 2 Sternen, auf die noch niemand geantwortet hat, die neuesten zuerst, höchstens 20. Das ist die Arbeitsliste für den Support. Klick auf eine Zeile öffnet die Rezension.",
        "Open negative reviews: reviews with 1 or 2 stars that nobody has answered yet, newest first, at most 20. This is the work list for support. Click a row to open the review."],
      ["Mit KI hat jede offene Rezension einen Antwortentwurf in der Sprache der Rezension: höflich, konkret, höchstens 350 Zeichen (Grenze der Play Console), ohne Namen und ohne Terminversprechen; „[Kontakt]“ ist ein Platzhalter für den echten Kontaktweg. „Entwurf“ klappt ihn auf, „Kopieren“ legt ihn in die Zwischenablage; geantwortet wird in App Store Connect oder der Play Console, das Programm sendet nie etwas. „Erledigt“ merkt sich nur dieser Browser. Entwürfe vor dem Senden lesen und Fakten prüfen.",
        "With AI, each open review has a reply draft in the review’s language: polite, concrete, at most 350 characters (Play Console limit), without names and without promised dates; “[Kontakt]” is a placeholder for the real contact channel. “Draft” expands it, “Copy” puts it on the clipboard; replies are posted in App Store Connect or the Play Console, the tool never sends anything. “Done” is remembered only in this browser. Read drafts and check facts before sending."]],
    rezensionen: [["Was hier steht", "What this shows"],
      ["Alle Rezensionen, die zum Filter passen, als Liste: App, Sterne, Titel, Datum, Land, Version, Themen und ob geantwortet wurde. Klick auf eine Spaltenüberschrift sortiert die Liste. Klick auf eine Zeile zeigt den ganzen Text und die Antwort des Supports.",
        "All reviews matching the filter as a list: app, stars, title, date, country, version, topics and whether answered. Click a column header to sort the list. Click a row to see the full text and the support reply."],
      ["Hier stehen nur Rezensionen mit Text. Sterne ohne Text gibt Apple nicht heraus. Darum ist die Anzahl hier viel kleiner als die Anzahl der Bewertungen bei „Sterne im App Store“. Die Namen der Verfasser werden nicht gespeichert.",
        "Only reviews with text appear here. Apple does not release stars without text. That is why the count here is much smaller than the number of ratings in “Stars in the App Store”. The authors' names are not stored."],
      ["Export CSV und JSON speichern genau diese gefilterte Liste als Datei, zum Beispiel für Excel oder ein Ticketsystem.",
        "Export CSV and JSON save exactly this filtered list as a file, for example for Excel or a ticket system."],
      ["Mit KI steht über der Tabelle die Stimmungsleiste: Begeistert, Zufrieden, Wunsch, Verärgert, Resigniert mit Anzahl; ein Klick setzt den Filter „Stimmung (KI)“. Dazu, wie oft die Sterne dem Text widersprechen (drei Sterne, aber verärgert) und wie oft Nutzer mit Wechsel drohen. In der Tabelle stehen Stimmung und Kernaussage als Spalten; der Klick auf die Zeile zeigt immer den Originaltext und die vollständige Einschätzung der KI.",
        "With AI, the sentiment strip sits above the table: delighted, satisfied, wish, annoyed, resigned with counts; a click sets the “Sentiment (AI)” filter. Plus how often the stars contradict the text (three stars but angry) and how often users threaten to leave. In the table, sentiment and core statement are columns; clicking the row always shows the original text and the AI’s full assessment."]],
    hinweise: [["Was hier steht", "What this shows"],
      ["Für jede App: Wie viele Rezensionen liegen vor, hat der letzte Abruf geklappt, wann war er, und gibt es Lücken? Darüber stehen die wichtigsten Grenzen der Datenquellen, damit niemand aus fehlenden Zahlen falsche Schlüsse zieht.",
        "For each app: how many reviews exist, did the last run succeed, when was it, and are there gaps? Above that are the main limits of the data sources, so that nobody draws wrong conclusions from missing figures."],
      ["Die wichtigsten Grenzen: Apple gibt nur Rezensionen mit Text heraus, keine Sterne ohne Text. Absturzzahlen stammen nur von Nutzern, die das Teilen solcher Daten erlaubt haben. Zu welcher Version eine Apple-Rezension gehört, wird über das Datum geschätzt. Google Play ist noch nicht angebunden. Was eine Quelle nicht liefert, bleibt leer und wird nie geschätzt oder erfunden.",
        "The main limits: Apple releases only reviews with text, no stars without text. Crash figures come only from users who allowed sharing such data. Which version an Apple review belongs to is estimated from the date. Google Play is not connected yet. What a source does not deliver stays empty and is never estimated or invented."]],
    wettbewerber: [["Was hier steht", "What this shows"],
      ["Fremde Apple-Apps, die in der Konfiguration als Wettbewerber eingetragen sind, neben den eigenen Apps des gewählten Kunden: offizielle Store-Note, Rezensionen der letzten 90 Tage mit Durchschnitt und Anteil negativer Rezensionen, aktuelle Version und die Ampel nach denselben Regeln wie im Überblick. Dieser Reiter erscheint nur, wenn Wettbewerber eingetragen und abgerufen sind.",
        "Third-party Apple apps listed as competitors in the configuration, next to the selected customer’s own apps: official store rating, reviews of the last 90 days with average and share of negative reviews, current version and the traffic light by the same rules as in the overview. This tab appears only when competitors are configured and fetched."],
      ["Woher die Daten kommen: Apple veröffentlicht für jede App einen Feed mit den jüngsten 500 Kundenrezensionen je Land und eine Bewertungsübersicht (iTunes Lookup), beides ohne Anmeldung. Es fehlen Entwicklerantworten, Sprache und Gerät, dafür steht die App-Version an jeder Rezension. Abstürze, Downloads und Sitzungen gibt es nur für eigene Apps. Für Google gibt es keine öffentliche Quelle, deshalb gibt es Wettbewerber nur für Apple.",
        "Where the data comes from: for every app Apple publishes a feed with the newest 500 customer reviews per country and a rating summary (iTunes Lookup), both without sign-in. Developer replies, language and device are missing; the app version is attached to every review. Crashes, downloads and sessions exist only for your own apps. Google offers no public source, so competitors exist for Apple only."],
      ["Wettbewerber fließen nicht in die eigenen Zahlen ein: Überblick, Kennzahlen, Diagramme und Rezensionsliste zeigen sie nur, wenn sie im App-Filter ausdrücklich gewählt sind (Einträge mit „Wettbewerber:“). Sie lösen keine Benachrichtigung aus. Mit KI steht je App, was die Nutzer loben und bemängeln; Antwortentwürfe und Maßnahmen gibt es für fremde Apps nicht.",
        "Competitors do not affect your own figures: overview, key figures, charts and the review list show them only when they are explicitly selected in the app filter (entries prefixed “Competitor:”). They never trigger a notification. With AI, each app shows what users praise and criticise; reply drafts and measures are not produced for third-party apps."]],
    kifragen: [["Was hier steht", "What this shows"],
      ["Freitextfragen an die gespeicherten Rezensionen, gestellt in der Kommandozeile (./ratings.sh ask \"…\") oder im Menü, mit Antwort, Sicherheit und wörtlichen Belegen. Die Funktion ist standardmäßig aus (ai.features.questions), weil jede Frage eine Anfrage beim Anbieter kostet.",
        "Free-text questions to the stored reviews, asked on the command line (./ratings.sh ask \"…\") or in the menu, with answer, confidence and verbatim evidence. The function is off by default (ai.features.questions) because each question costs one request to the provider."],
      ["„Sichere Aussage“ gibt es nur mit mehreren Belegen; ohne wörtlichen Beleg steht „unklar“. Die Frage sieht höchstens die jüngsten Rezensionen der Auswahl (Einstellung maxReviewsPerQuestion), nicht Store-Zahlen oder Abstürze.",
        "“Reliable” requires several sources; without a verbatim source the answer is marked “unclear”. A question sees at most the most recent reviews of the selection (setting maxReviewsPerQuestion), not store figures or crashes."],
      ["Läuft der lokale Fragedienst (./ratings.sh ai-report), steht hier ein Eingabefeld; während der Anfrage zeigt ein Wartefenster, dass die Antwort unterwegs ist (meist 5 bis 30 Sekunden). Gespeichert werden höchstens 100 Fragen, gezeigt die neuesten 10 („Alle zeigen“ blendet den Rest ein). Löschen: Knopf „Löschen“ an der Frage bei laufendem Dienst oder ./ratings.sh ai-questions --delete NR.",
        "If the local question service is running (./ratings.sh ai-report), an input field appears here; while asking, a waiting dialog shows that the answer is on its way (usually 5 to 30 seconds). At most 100 questions are stored, the latest 10 are shown (“Show all” reveals the rest). Delete: the “Delete” button on a question while the service runs, or ./ratings.sh ai-questions --delete NR."],
      ["Unten der Verbrauch des Monats gegenüber dem Limit aus der Konfiguration. Kosten ergeben sich aus Tokens mal Preis des Anbieters; das Programm speichert keine Preise.",
        "Below is this month’s usage against the limit from the configuration. Cost is tokens times the provider’s price; the tool stores no prices."],
      ["In Zwischenablage: Der Knopf neben „Löschen“ kopiert Frage, Antwort, Einordnung (Sicherheit, gelesene Rezensionen, Auswahl, Anbieter, Datum) und die Belege als reinen Text, zum Einfügen in Jira, Mail oder Teams. Im Gesamtbericht (Knopf neben „Filter zurücksetzen“) erscheinen die Fragen nur, wenn die KI eingeschaltet ist.",
        "Copy to clipboard: the button next to “Delete” copies question, answer, classification (confidence, reviews read, selection, provider, date) and the evidence as plain text, to paste into Jira, mail or Teams. In the full report (button next to “Reset filters”) the questions appear only when the AI is switched on."]],
  };
  function openInfo(id) {
    const sec = SECS.find(x => x[0] === id), paras = INFO[id] || [], d = $("info");
    d.replaceChildren(h("div", { class: "infohead" }, h("h2", {}, sec ? tx(sec[1], sec[2]) : ""),
      h("button", { type: "button", class: "chnav", "aria-label": tx("Schließen", "Close"), title: tx("Schließen", "Close"), onclick: () => d.close() }, "×")),
      h("div", { class: "infobody" }, paras.slice(1).map(([de, en]) => h("p", {}, tx(de, en)))));
    if (d.showModal) d.showModal(); else d.setAttribute("open", "");
  }
  $("info").addEventListener("click", e => { if (e.target === $("info") && $("info").close) $("info").close(); });
  // Rotes „i“ neben der Überschrift; in einem <summary> darf der Klick das Auf-/Zuklappen nicht auslösen
  function infoBtn(id) {
    const l = tx("Was zeigt dieser Bereich?", "What does this section show?");
    return h("button", { type: "button", class: "infobtn", "aria-label": l, title: l, "aria-haspopup": "dialog",
      onclick: e => { e.preventDefault(); e.stopPropagation(); openInfo(id); } }, "i");
  }
  // Sicherheitsabfrage als Dialog (Ja/Nein); `onYes` läuft nur nach „Ja“
  function confirmDialog(question, note, onYes, onNo) {
    const d = $("confirmdlg"); if (!d.replaceChildren) { onYes(); return; }
    const close = () => { if (d.close && d.open) d.close(); else if (d.removeAttribute) d.removeAttribute("open"); };
    d.replaceChildren(h("h2", { style: "font-size:1.15rem;margin:0 0 .5rem" }, question), note ? h("p", { class: "muted", style: "margin:0" }, note) : null,
      h("div", { class: "row" }, h("button", { type: "button", class: "btn", onclick: () => { close(); if (onNo) onNo(); } }, tx("Nein", "No")), h("button", { type: "button", class: "btn primary", onclick: () => { close(); onYes(); } }, tx("Ja", "Yes"))));
    if (d.showModal && !d.open) d.showModal(); else d.setAttribute("open", "");
  }
  // Reiter (nur Produktion): Kennung, Beschriftung de/en, Bereiche (IDs von Karten; auch Karten außerhalb von SECS wie
  // hero-score und kpis). „Wie vollständig sind die Daten?“ hat den letzten Reiter „Datenstand“ (nach „KI-Anfragen“, sonst nach „Diagramme“/„Wettbewerber“). MORE: Bereiche des Überblicks hinter
  // „Mehr Zahlen anzeigen“. Der Testbetrieb ist ein eigener Prozess und hat den Umschalter #modeseg im Kopf (kein Reiter).
  const TABS = [["start", "Überblick", "Overview", ["ueberblick", "morebar", "steckbrief", "vergleich", "release", "fragen"]],
    ["rez", "Rezensionen", "Reviews", ["hero-score", "kpis", "themen", "rezensionen", "antworten"]],
    ["stabil", "Stabilität", "Stability", ["stab"]], ["store", "Downloads & Store", "Downloads & store", ["appvgl", "storewerte", "latestver"]],
    ["charts", "Diagramme", "Charts", ["diagramme"]],
    ["rivals", "Wettbewerber", "Competitors", ["wettbewerber"]],
    ["ask", "KI-Anfragen", "AI questions", ["kifragen"]],
    ["data", "Datenstand", "Data status", ["hinweise"]]];
  // Der Reiter „Wettbewerber“ erscheint nur, wenn Wettbewerber eingetragen und abgerufen sind (DATA.hasCompetitors); sonst
  // bleibt der Bericht exakt wie ohne diese Funktion (Wunsch des Nutzers, 25.10.2026)
  // Der Reiter „KI-Anfragen“ erscheint nur, wenn man die KI wirklich ansprechen kann (Wunsch des Nutzers 24.10.2026): der lokale
  // Fragedienst läuft und hat auf die Statusabfrage geantwortet; ki.js setzt `askUp` und zeichnet die Reiter neu
  let askUp = false;
  const visibleTabs = () => TABS.filter(t => (t[0] !== "ask" || askUp) && (t[0] !== "rivals" || DATA.hasCompetitors));
  const MORE = ["fragen", "steckbrief", "vergleich", "release"];
  let secState = { collapsed: [], tab: "start", more: false };
  try { const v = JSON.parse(localStorage.getItem("sections") || "null"); if (v && Array.isArray(v.collapsed)) secState = { collapsed: v.collapsed.filter(x => x !== "hinweise"), tab: typeof v.tab === "string" ? v.tab : "start", more: !!v.more }; } catch (e) {}
  const tabFlag = /\btab=([a-z]+)/.exec(flags); if (tabFlag) secState.tab = tabFlag[1];  // index.html?tab=stabil wählt einen Reiter vor
  if (/\balle\b/.test(flags)) { secState.collapsed = []; secState.more = true; }  // index.html?alle: alles aufgeklappt (Bildschirmfotos)
  if (!visibleTabs().some(t => t[0] === secState.tab)) secState.tab = "start";
  const saveSecs = () => { try { localStorage.setItem("sections", JSON.stringify(secState)); } catch (e) {} };
  let onMode = () => {};  // wird vom Testbetrieb-Block gesetzt (zeichnet die Testansicht, tauscht die Kopfzeile)
  function setTab(id) { secState.tab = id; saveSecs(); applyTabs(); if (window.scrollTo && $("tabs").getBoundingClientRect && $("tabs").getBoundingClientRect().top < 0) $("tabs").scrollIntoView(); }
  function applyTabs() {
    const cur = visibleTabs().find(t => t[0] === secState.tab) || TABS[0];
    for (const t of TABS) for (const id of t[3]) { const el = $(id); if (!el || !el.classList) continue; if (t === cur && !(MORE.includes(id) && !secState.more)) el.classList.remove("tabhide"); else el.classList.add("tabhide"); }
    $("tabs").replaceChildren(...visibleTabs().map(([id, de, en]) => h("button", { type: "button", role: "tab", "data-tab": id, "aria-selected": String(id === cur[0]), onclick: () => setTab(id) }, tx(de, en))));
    const mb = $("morebtn"); mb.textContent = secState.more ? tx("Weniger Zahlen anzeigen", "Show fewer figures") : tx("Mehr Zahlen anzeigen (Fragen und Antworten, wichtigste Zahlen je App, Vergleich nach Version, alle Updates)", "Show more figures (questions and answers, key figures per app, comparison by version, all updates)");
    mb.setAttribute("aria-expanded", String(secState.more));
  }
  $("morebtn").addEventListener("click", () => { secState.more = !secState.more; saveSecs(); applyTabs(); });
  // Klick auf „App-Feedback“ in der Kopfleiste: Reiter Überblick, Seite nach oben (Wunsch des Nutzers, 25.10.2026)
  $("brandbtn").addEventListener("click", () => { secState.tab = "start"; saveSecs(); applyTabs(); if (window.scrollTo) window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" }); });
  // Umschalter Produktion / Testbetrieb im Kopf: body[data-mode] blendet .prod bzw. .test aus; nicht gespeichert, Start immer Produktion
  function setMode(mode) {
    document.body.dataset.mode = mode;
    document.querySelectorAll("#modeseg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
    onMode(mode);
  }
  document.querySelectorAll("#modeseg button").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode)));
  const withId = (list, id, on) => on ? (list.includes(id) ? list : list.concat([id])) : list.filter(x => x !== id);
  // Gezeichneter Pfeil statt „▾“ (das Zeichen erscheint in vielen Systemschriften sehr klein)
  function chevron() { const svg = s("svg", { viewBox: "0 0 16 16", width: "16", height: "16", "aria-hidden": "true" }); svg.append(s("polyline", { points: "4,6 8,10 12,6", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round" })); return svg; }
  function colBtn(id) {
    const open = !secState.collapsed.includes(id), l = open ? tx("Bereich zuklappen", "Collapse section") : tx("Bereich aufklappen", "Expand section");
    return h("button", { type: "button", class: "colbtn", "aria-expanded": String(open), "aria-controls": id, title: l, "aria-label": l,
      onclick: () => { secState.collapsed = withId(secState.collapsed, id, open); saveSecs(); applySecs(); if (id === "diagramme") renderCharts(); } }, chevron());
  }
  function applySecs() {
    for (const [id] of SECS) {
      const sec = $(id), col = secState.collapsed.includes(id);
      if (!sec.classList) continue;
      sec.classList.add("sec");
      // Klappknopf immer an derselben Stelle: oben rechts in der Karte (CSS .sec>.colbtn); die Diagrammkarte setzt ihn in chartView
      if (id !== "diagramme" && sec.querySelector) { const old = sec.querySelector(":scope > .colbtn"), b = colBtn(id); if (old) old.replaceWith(b); else sec.append(b);
        const h2 = sec.querySelector("h2"); if (h2 && !h2.querySelector(".infobtn")) h2.append(infoBtn(id)); }
      if (col) sec.classList.add("collapsed"); else sec.classList.remove("collapsed");
    }
  }
  applySecs(); applyTabs();

  // ---- Tabelle ----
  const cols = [["appName", "App"], ["platform", tx("Plattform", "Platform")], ["rating", tx("Sterne", "Stars")], ["title", tx("Titel", "Title")], ["text", "Text"], ["createdAt", tx("Datum", "Date")], ["updatedAt", tx("Geändert", "Updated")], ["country", tx("Land", "Country")], ["language", tx("Sprache", "Language")], ["appVersion", "Version"], ["osLabel", tx("Betriebssystem", "Operating system")], ["device", tx("Gerät", "Device")], ["reply", tx("Antwort", "Reply")]];
  if (DATA.ai && DATA.ai.length) cols.push(["aiSentiment", tx("Stimmung (KI)", "Sentiment (AI)")], ["aiIssue", tx("Kern (KI)", "Core (AI)")]);
  const thead = $("tbl").tHead;
  thead.append(h("tr", {}, cols.map(([k, l]) => { const th = h("th", { scope: "col", tabindex: "0", "data-k": k }, l); const go = () => { state.sort = { key: k, dir: state.sort.key === k ? -state.sort.dir : 1 }; SS.set("sort:rez", state.sort); render(); }; th.addEventListener("click", go); th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }); return th; })));
  const pill = n => n ? h("span", { class: "pill r" + n }, "★ " + n) : "–";
  const plat = p => h("span", { class: "plat " + p }, h("i", {}), platName(p));
  function showDetail(r) {
    const d = $("detail"), rows = [[tx("Erstellt", "Created"), fmtDate(r.createdAt)], [tx("Geändert", "Updated"), fmtDate(r.updatedAt)], [tx("Land", "Country"), r.country], [tx("Sprache", "Language"), r.language], [tx("App-Version", "App version"), r.appVersion], ["Build", r.buildNumber], [tx("Betriebssystem", "Operating system"), r.operatingSystem], [tx("OS-Version", "OS version"), r.osVersion], [tx("Gerät", "Device"), r.device], [tx("Erstmals erfasst", "First captured"), fmtDate(r.firstSeenAt)], [tx("Zuletzt gesehen", "Last seen"), fmtDate(r.lastSeenAt)], ["ID", r.id]];
    const close = () => d.close ? d.close() : d.removeAttribute("open");
    d.replaceChildren(
      h("div", { class: "dhead" }, h("div", { class: "row", style: "justify-content:space-between" }, plat(r.platform), h("button", { class: "iconbtn", type: "button", "aria-label": tx("Schließen", "Close"), onclick: close }, "×")),
        h("h2", { style: "font-size:1.5rem;margin:.6rem 0 .3rem" }, r.title || tx("(ohne Titel)", "(no title)")),
        h("div", { class: "row" }, starsSvg(r.rating, 20), h("span", { class: "muted" }, r.appName + " · " + r.customerName), rivalMark(r))),
      h("div", { class: "dbody" }, h("div", { class: "quote" }, r.text || tx("Kein Text.", "No text.")),
        hasReply(r) ? h("div", { style: "margin-top:1rem" }, h("h3", {}, tx("Antwort des Entwicklers", "Developer reply") + (r.developerReply.repliedAt ? " · " + fmtDate(r.developerReply.repliedAt) : "")), h("div", { class: "quote reply" }, r.developerReply.text)) : null,
        r.aiSentiment ? h("div", { style: "margin-top:1rem" }, h("h3", {}, tx("Einschätzung der KI", "AI assessment"), " ", kiMark()),
          h("dl", {}, [[tx("Stimmung", "Sentiment"), sentLabel(r.aiSentiment)], [tx("Dringlichkeit", "Urgency"), (URGENCY.find(u => u[0] === r.aiUrgency) || URGENCY[2])[LANG === "de" ? 1 : 2]], [tx("Kernaussage", "Core statement"), r.aiIssue || "–"],
            [tx("Themen", "Topics"), (r.aiThemes || []).join(", ") || "–"], [tx("Sterne täuschen", "Stars mislead"), r.aiMismatch ? tx("ja", "yes") : tx("nein", "no")], [tx("Droht zu wechseln", "Threatens to leave"), r.aiChurn ? tx("ja", "yes") : tx("nein", "no")]].map(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])),
          r.aiDraft && !hasReply(r) ? h("div", {}, h("h3", {}, tx("Antwortentwurf (KI, nicht gesendet)", "Reply draft (AI, not sent)")), h("div", { class: "quote reply" }, r.aiDraft.text), h("div", { class: "row", style: "margin-top:.5rem" }, copyBtn(r.aiDraft.text))) : null) : null,
        h("h3", {}, "Details"), h("dl", {}, rows.map(([k, v]) => [h("dt", {}, k), h("dd", {}, v === null || v === undefined || v === "" ? "–" : String(v))])),
        h("details", { style: "margin-top:1rem" }, h("summary", { style: "cursor:pointer" }, tx("Rohdaten des Stores", "Raw store data")), h("pre", {}, JSON.stringify(r.raw || {}, null, 2)))));
    if (d.showModal) d.showModal(); else d.setAttribute("open", "");
  }
  $("detail").addEventListener("click", e => { if (e.target === $("detail") && $("detail").close) $("detail").close(); });
  function download(name, mime, content) {
    const url = URL.createObjectURL(new Blob([content], { type: mime }));
    const a = h("a", { href: url, download: name }); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  let current = [];
  $("exjson").addEventListener("click", () => download("rezensionen.json", "application/json", toJson(current)));
  $("excsv").addEventListener("click", () => download("rezensionen.csv", "text/csv;charset=utf-8", "﻿" + toCsv(current)));
  $("prev").addEventListener("click", () => { if (state.page > 0) { state.page--; renderTable(); } });
  $("next").addEventListener("click", () => { if ((state.page + 1) * state.pageSize < current.length) { state.page++; renderTable(); } });
  // Eine Zeile der Rezensionsliste; auch die Liste im Bereich „Themen und Wörter“ nutzt sie, damit beide gleich aussehen
  function reviewRow(r) {
    const tr = h("tr", { tabindex: "0", class: "click" },
      h("td", {}, r.appName, rivalMark(r)), h("td", {}, plat(r.platform)), h("td", {}, pill(r.rating)), h("td", {}, h("div", { class: "clamp2" }, r.title || "–")), h("td", { class: "txt" }, h("div", { class: "clamp" }, r.text || "–")),
      h("td", { class: "num" }, fmtDate(r.createdAt)), h("td", { class: "num" }, fmtDate(r.updatedAt)), h("td", {}, r.country || "–"), h("td", {}, r.language || "–"), h("td", {}, r.appVersion || "–"),
      h("td", {}, r.osLabel || "–"), h("td", {}, r.device || "–"), h("td", { class: hasReply(r) ? "yes" : "no" }, hasReply(r) ? tx("✓ Ja", "✓ Yes") : tx("Nein", "No")));
    if (DATA.ai && DATA.ai.length) tr.append(h("td", {}, r.aiSentiment ? sentPill(r.aiSentiment) : h("span", { class: "muted" }, "–")), h("td", { class: "txt" }, r.aiIssue ? h("div", { class: "clamp2" }, r.aiIssue) : h("span", { class: "muted" }, "–")));
    tr.addEventListener("click", () => showDetail(r)); tr.addEventListener("keydown", e => { if (e.key === "Enter") showDetail(r); });
    return tr;
  }
  // Rezensionsliste wie unter „Rezensionen“ (Spalten, Breiten, Sortierung, 25 je Seite), für andere Bereiche;
  // st = { sort: { key, dir }, page } hält der Aufrufer, rerender() zeichnet nach Sortieren oder Blättern neu
  function reviewList(rs, st, rerender) {
    const sorted = sortReviews(rs, st.sort.key, st.sort.dir), pages = Math.max(1, Math.ceil(sorted.length / state.pageSize));
    if (st.page >= pages) st.page = pages - 1;
    const go = k => () => { st.sort = { key: k, dir: st.sort.key === k ? -st.sort.dir : 1 }; st.page = 0; rerender(); };
    const ths = cols.map(([k, l]) => { const a = { scope: "col", tabindex: "0", "data-k": k, onclick: go(k), onkeydown: e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(k)(); } } };
      if (k === st.sort.key) a["aria-sort"] = st.sort.dir > 0 ? "ascending" : "descending"; return h("th", a, l); });
    const turn = d => () => { const n = st.page + d; if (n >= 0 && n < pages) { st.page = n; rerender(); } };
    return [h("div", { class: "tablewrap" }, h("table", { class: "revtbl" }, h("thead", {}, h("tr", {}, ths)), h("tbody", {}, sorted.slice(st.page * state.pageSize, (st.page + 1) * state.pageSize).map(reviewRow)))),
      h("div", { class: "pager" }, h("button", { class: "btn", type: "button", onclick: turn(-1) }, tx("← Zurück", "← Back")),
        h("span", { class: "note", style: "margin:0" }, tx("Seite ", "Page ") + (st.page + 1) + tx(" von ", " of ") + pages + " · " + fmtInt(sorted.length) + tx(" Rezensionen", " reviews")),
        h("button", { class: "btn", type: "button", onclick: turn(1) }, tx("Weiter →", "Next →")))];
  }
  function renderTable() {
    const sorted = sortReviews(current, state.sort.key, state.sort.dir);
    thead.querySelectorAll("th").forEach(th => { if (th.dataset && th.dataset.k === state.sort.key) th.setAttribute("aria-sort", state.sort.dir > 0 ? "ascending" : "descending"); else th.removeAttribute("aria-sort"); });
    const pages = Math.max(1, Math.ceil(sorted.length / state.pageSize));
    if (state.page >= pages) state.page = pages - 1;
    const slice = sorted.slice(state.page * state.pageSize, (state.page + 1) * state.pageSize);
    const body = $("tbl").tBodies[0]; body.replaceChildren();
    for (const r of slice) body.append(reviewRow(r));
    if (!slice.length) body.append(h("tr", {}, h("td", { colspan: String(cols.length), class: "muted" }, tx("Keine Rezensionen für diese Filter.", "No reviews match these filters."))));
    $("pg").textContent = tx("Seite ", "Page ") + (state.page + 1) + tx(" von ", " of ") + pages + " · " + fmtInt(sorted.length) + tx(" Rezensionen", " reviews");
  }

  // ---- Gesamtdarstellung ----
  function renderScore(st, target) {
    const box = target || $("hero-score"); box.replaceChildren();
    const big = h("div", { class: "big num" }); big.append(h("span", {}, fmt(st.avg, 2)), h("small", {}, "/ 5"));
    const left = h("div", {}, h("div", { class: "lbl" }, tx("Ø Bewertung (aus Rezensionen berechnet)", "Average rating (calculated from reviews)")), big,
      h("div", { class: "stars", style: "color:var(--fg)" }, starsSvg(st.avg, 26)), h("div", { class: "sub" }, tx("Basis: " + fmtInt(st.rated) + (st.rated === 1 ? " Rezension" : " Rezensionen") + ". Nicht identisch mit der offiziellen Store-Gesamtbewertung.", "Based on " + fmtInt(st.rated) + (st.rated === 1 ? " review" : " reviews") + ". Not the official store rating.")));
    const mid = h("div", {}, h("div", { class: "lbl", style: "margin-bottom:.8rem" }, tx("Verteilung", "Distribution")), distBars(st, true));
    const neutral = st.rated - st.pos - st.neg;
    const dn = h("div", { class: "donut" }, donut(st), h("div", { class: "mid" }, h("b", { class: "num" }, st.rated ? fmt(100 * st.pos / st.rated, 0) + " %" : "–"), h("span", {}, tx("positiv", "positive"))));
    const right = h("div", { class: "donut", style: "display:block;text-align:center" }, dn, h("div", { class: "legend", style: "justify-content:center" },
      h("span", {}, h("i", { style: "background:var(--good)" }), st.pos + tx(" positiv", " positive")), h("span", {}, h("i", { style: "background:var(--mid)" }), neutral + " neutral"), h("span", {}, h("i", { style: "background:var(--bad)" }), st.neg + tx(" negativ", " negative"))));
    put(box, left, mid, right);
  }
  // Kunde, App und Plattform aus dem Filter oben gelten für alle Abschnitte; die übrigen Filter betreffen nur Rezensionen.
  function inScope(x) {
    const f = state.f;
    if (rivalHidden(isRival(x) ? { competitor: true } : x, f)) return false;  // Wettbewerber nur bei ausdrücklicher Wahl
    return inSel(f.customerId, x.customerId) && inSel(f.appKey, x.customerId + "/" + x.appId) && !(f.platform && x.platform && x.platform !== f.platform);
  }
  // Wettbewerber-App? Einträge in ratings/stability/ai tragen das Flag nicht selbst, deshalb über DATA.apps nachschlagen
  const rivalKeys = new Set(DATA.apps.filter(a => a.competitor).map(a => a.customerId + "/" + a.appId));
  function isRival(x) { return !!x.competitor || rivalKeys.has(x.customerId + "/" + x.appId); }
  // Kennzeichen „Wettbewerber“ neben einem App-Namen; ohne Wettbewerber in den Daten entsteht nie eines
  const rivalMark = x => isRival(x) ? h("span", { class: "rival", title: tx("Fremde App aus dem öffentlichen Apple-Feed", "Third-party app from Apple’s public feed") }, tx("Wettbewerber", "Competitor")) : null;
