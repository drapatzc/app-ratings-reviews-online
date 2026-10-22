// Textseiten (Hilfe, Impressum, Datenschutz): Sprache, Hell/Dunkel und Designfarbe wie im Bericht, gleiche Schlüssel im localStorage.
(function () {
  const PALETTES = /*__PALETTES__*/[];
  // Sprache: Elemente mit lang="de" / lang="en" blendet das CSS je nach html[lang] ein oder aus.
  let LANG = "de"; try { LANG = localStorage.getItem("lang") || LANG; } catch (e) {}
  if (/\blang=en\b/.test(location.search)) LANG = "en"; if (/\blang=de\b/.test(location.search)) LANG = "de";
  if (LANG !== "en") LANG = "de";
  const setLang = l => {
    LANG = l; document.documentElement.lang = l;
    document.querySelectorAll("#langs button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang === l)));
    const title = document.querySelector("title"); if (title && title.dataset && title.dataset[l]) document.title = title.dataset[l];
  };
  document.querySelectorAll("#langs button").forEach(b => b.addEventListener("click", () => { try { localStorage.setItem("lang", b.dataset.lang); } catch (e) {} setLang(b.dataset.lang); }));
  setLang(LANG);
  try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
  if (!document.documentElement.dataset.theme && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) document.documentElement.dataset.theme = "dark";
  document.getElementById("theme").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (e) {}
  });
  let saved = null; try { saved = localStorage.getItem("palette"); } catch (e) {}
  const pal = PALETTES.find(p => p[0] === saved) || PALETTES[0];
  if (pal) { const st = document.documentElement.style; st.setProperty("--p-a", pal[2]); st.setProperty("--p-b", pal[3]); st.setProperty("--p-c", pal[4]); }
})();
