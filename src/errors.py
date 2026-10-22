"""Gemeinsame Fehlertypen. Meldungen enthalten niemals Tokens oder Schlüssel."""


class ToolError(Exception):
    """Basisklasse für erwartbare Fehler mit verständlicher Meldung."""


class ConfigError(ToolError):
    """Ungültige oder unvollständige Konfiguration."""


class StorageError(ToolError):
    """JSON-Datei beschädigt, gesperrt oder nicht schreibbar."""


class AuthError(ToolError):
    """Ungültige Zugangsdaten oder fehlende Berechtigung (HTTP 401/403)."""


class ApiError(ToolError):
    """API-Fehler nach ausgeschöpften Wiederholungsversuchen."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status
