"""Terminal-Darstellung: Farben (nur auf echten Terminals), Tabellen, relative Zeitangaben."""
from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import datetime, timezone

COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def paint(text: str, *codes: str) -> str:
    """Färbt Text mit Standard-ANSI-Farben (auf hellen und dunklen Terminals lesbar)."""
    return f"\033[{';'.join(codes)}m{text}\033[0m" if COLOR and codes else text


def visible_len(text: str) -> int:
    return len(_ANSI.sub("", text))


def pad(text: str, width: int, align: str = "left") -> str:
    gap = max(0, width - visible_len(text))
    return " " * gap + text if align == "right" else text + " " * gap


def table(headers: list[str], rows: list[list[str]], aligns: list[str] | None = None) -> str:
    """Zeichnet eine Rahmentabelle; Zellen dürfen Farbcodes enthalten."""
    aligns = aligns or ["left"] * len(headers)
    widths = [max(visible_len(str(c)) for c in col) for col in zip(headers, *rows)] if rows else [len(h) for h in headers]
    line = lambda l, m, r: paint(l + m.join("─" * (w + 2) for w in widths) + r, "35")  # noqa: E731
    bar = paint("│", "35")
    out = [line("╭", "┬", "╮"),
           bar + bar.join(f" {paint(pad(h, w, a), '1')} " for h, w, a in zip(headers, widths, aligns)) + bar,
           line("├", "┼", "┤")]
    for row in rows:
        out.append(bar + bar.join(f" {pad(str(c), w, a)} " for c, w, a in zip(row, widths, aligns)) + bar)
    out.append(line("╰", "┴", "╯"))
    return "\n".join(out)


def heading(text: str) -> str:
    return paint(f"\n{text}", "1", "35")


def parse_ts(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def ago(value: str | None, now: datetime | None = None) -> str:
    """„vor 5 Min", „vor 3 Std", „vor 2 Tagen" plus Datum (lokale Zeit); „–" ohne Wert."""
    ts = parse_ts(value)
    if ts is None:
        return "–"
    now = now or datetime.now(timezone.utc)
    seconds = max(0, int((now - ts).total_seconds()))
    if seconds < 90:
        rel = "gerade eben"
    elif seconds < 3600:
        rel = f"vor {seconds // 60} Min"
    elif seconds < 86400:
        rel = f"vor {seconds // 3600} Std"
    else:
        days = seconds // 86400
        rel = f"vor {days} Tag{'en' if days != 1 else ''}"
    return f"{rel} ({ts.astimezone():%d.%m. %H:%M})"


def status_badge(status: str | None) -> str:
    """Symbol + Text; Farbe zusätzlich zum Symbol (nie nur Farbe)."""
    return {"ok": paint("✔ ok", "1", "32"), "partial": paint("◐ teilweise", "1", "33"), "failed": paint("✖ Fehler", "1", "31"),
            "never_synced": paint("○ nie abgerufen", "2" if COLOR else "0"), None: paint("○ nie abgerufen")
            }.get(status, status or "–")


def width() -> int:
    return shutil.get_terminal_size((100, 24)).columns


def fmt_seconds(seconds: float) -> str:
    """Deutsche Dauerangabe: „4,7 s", „2 min 05 s"."""
    if seconds < 60:
        return f"{seconds:.1f} s".replace(".", ",")
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rest:02d} s"


def fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def progress_printer(label: str, done: int, total: int) -> None:
    """Fortschrittsbalken in einer Zeile (nur auf echten Terminals); total=0 löscht die Zeile."""
    if not sys.stdout.isatty():
        return
    if total <= 0:
        sys.stdout.write("\r\033[2K")
    else:
        width_bar = 24
        filled = int(width_bar * done / total)
        sys.stdout.write(f"\r\033[2K  {paint('█' * filled, '35')}{'░' * (width_bar - filled)} {done}/{total}  {label} …")
    sys.stdout.flush()
