"""Kleiner, sicherer Markdown→HTML-Umwandler (Teilmenge, offline) für die erzeugten Zusammenfassungen und die Doku.

Unterstützt: Überschriften, Absätze, Tabellen, Zitate, Listen, Codeblöcke, Trennlinien, **fett**, *kursiv*, `code`, Links.
Alles wird HTML-maskiert; Links nur http(s), mailto und relative Pfade (.md-Links werden zu .html).
"""
from __future__ import annotations

import html
import re
from pathlib import Path

CSS = """
:root{--bg:#f6f7fc;--card:#fff;--fg:#14162e;--muted:#5b6185;--line:#dfe2f0;--accent:#5b5bff;--code:#eef0fb}
@media (prefers-color-scheme:dark){:root{--bg:#0b0d1c;--card:#151936;--fg:#eceefc;--muted:#9aa1c8;--line:#2a3058;--accent:#8f95ff;--code:#1d2246}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
main{max-width:920px;margin:2rem auto;padding:2rem clamp(1rem,4vw,2.4rem);background:var(--card);border:1px solid var(--line);border-radius:20px;box-shadow:0 12px 40px -18px rgba(40,40,120,.35)}
h1,h2,h3,h4{letter-spacing:-.02em;line-height:1.25}h1{font-size:2rem;margin-top:0}h2{margin-top:2rem;padding-bottom:.3rem;border-bottom:1px solid var(--line)}
a{color:var(--accent)}code{background:var(--code);padding:.1em .35em;border-radius:6px;font-size:.9em}pre{background:var(--code);padding:1rem;border-radius:12px;overflow:auto}pre code{background:none;padding:0}
blockquote{margin:.8rem 0;padding:.4rem 1rem;border-left:4px solid var(--accent);background:var(--code);border-radius:0 10px 10px 0}
table{border-collapse:collapse;width:100%;display:block;overflow-x:auto;margin:1rem 0}th,td{border-bottom:1px solid var(--line);padding:.5rem .7rem;text-align:left}th{font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
hr{border:none;border-top:1px solid var(--line);margin:2rem 0}.muted{color:var(--muted)}
"""

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _safe_href(url: str) -> str | None:
    url = html.unescape(url).strip()
    if re.match(r"^(https?:|mailto:)", url, re.I):
        return url
    if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) or url.startswith("//"):
        return None  # javascript:, data: usw. werden nie verlinkt
    return re.sub(r"\.md(?=(#|$))", ".html", url)


def inline(text: str) -> str:
    """Wandelt Inline-Markdown in HTML um; Eingabe wird zuerst vollständig maskiert."""
    codes: list[str] = []
    text = re.sub(r"`([^`]+)`", lambda m: codes.append(m.group(1)) or f"\x00{len(codes) - 1}\x00", text)
    text = html.escape(text, quote=True)

    def link(m: re.Match) -> str:
        href = _safe_href(m.group(2))
        return f'<a href="{html.escape(href, quote=True)}">{m.group(1)}</a>' if href else m.group(1)

    text = _LINK.sub(link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*\s][^*]*)\*(?!\w)", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w])_([^_\s][^_]*)_(?!\w)", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{html.escape(codes[int(m.group(1))])}</code>", text)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def convert(md: str) -> str:
    """Markdown-Text → HTML-Fragment."""
    lines, out, i = md.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            out.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
            i += 1
        elif m := re.match(r"^(#{1,6})\s+(.*)$", line):
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
            i += 1
        elif re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
            i += 1
        elif line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            head, aligns = _cells(line), [("right" if c.endswith(":") else "left") for c in _cells(lines[i + 1])]
            rows, i = [], i + 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            th = "".join(f'<th style="text-align:{aligns[k] if k < len(aligns) else "left"}">{inline(c)}</th>' for k, c in enumerate(head))
            body = "".join("<tr>" + "".join(f'<td style="text-align:{aligns[k] if k < len(aligns) else "left"}">{inline(c)}</td>'
                                            for k, c in enumerate(r)) + "</tr>" for r in rows)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>")
        elif line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i][1:].lstrip())
                i += 1
            out.append("<blockquote>" + "<br>".join(inline(q) for q in quote) + "</blockquote>")
        elif re.match(r"^\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.", line))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(inline(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i])))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{x}</li>" for x in items) + f"</{tag}>")
        elif not line.strip():
            i += 1
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|```|>|\s*\|)", lines[i]) \
                    and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append("<p>" + " ".join(inline(p) for p in para) + "</p>")
    return "\n".join(out)


def to_page(md: str, title: str) -> str:
    """Vollständige, eigenständige HTML-Seite (ohne externe Ressourcen)."""
    return ("<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src data:\">"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><main>{convert(md)}</main></body></html>")


def convert_file(source: Path, target_dir: Path) -> Path:
    """Schreibt `source` als HTML nach `target_dir/<name>.html` und gibt den Pfad zurück."""
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (source.stem + ".html")
    target.write_text(to_page(source.read_text(encoding="utf-8"), source.stem), encoding="utf-8")
    return target
