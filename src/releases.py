"""Veröffentlichungsdaten von App-Versionen für die Versionsleiste im Bericht.

Quelle für das exakte Datum: iTunes Lookup, Feld `currentVersionReleaseDate` (am 22.10.2026 live geprüft). Es gilt nur
für die jeweils aktuelle Version; ältere Versionen bekommen erst ein Datum, wenn sie bei einem Lauf aktuell waren.
Die Versionsliste der App Store Connect API (`createdDate`) ist das Anlegedatum, nicht die Veröffentlichung, und wird
dafür nicht verwendet. Eine Näherung aus den Sitzungsdaten berechnet erst der Bericht (`releaseList` im Template).
"""
from __future__ import annotations


def apply_release_dates(versions_doc: dict, summaries: list[dict], now: str) -> bool:
    """Trägt `releasedAt` der aktuellen Store-Version in versions.json ein. Ein vorhandenes Datum bleibt unverändert.

    Fehlt die Version in der Liste (Versionen werden nur bei vollständigen Läufen geholt), wird ein Eintrag mit
    Quelle `itunes-lookup` angelegt. Gibt True zurück, wenn sich etwas geändert hat.
    """
    found = next(((summary.get("currentVersion"), summary.get("currentVersionReleasedAt")) for summary in summaries
                  if summary.get("currentVersion") and summary.get("currentVersionReleasedAt")), None)
    if not found:
        return False
    version, released = found
    entries = versions_doc.setdefault("versions", [])
    entry = next((entry for entry in entries if entry.get("version") == version and entry.get("build") is None), None)
    if entry is None:
        entries.append({"version": version, "build": None, "platform": "apple", "releasedAt": released,
                        "releasedAtSource": "itunes-lookup", "firstSeenAt": now, "source": "itunes-lookup",
                        "reviewIds": []})
        entries.sort(key=lambda entry: (str(entry["version"]), str(entry.get("build"))))
        return True
    if entry.get("releasedAt"):
        return False
    entry["releasedAt"], entry["releasedAtSource"] = released, "itunes-lookup"
    return True
