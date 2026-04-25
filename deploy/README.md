# Deployment mit Once

## Voraussetzungen

- Server mit Docker (Once installiert)
- Domain, die auf den Server zeigt
- GitHub Container Registry: `ghcr.io/jensedler/spielzeitmanager`

## Erstinstallation

```bash
# Once installieren
curl https://get.once.com | sh

# App starten (Once fragt nach Hostname und Image)
once install ghcr.io/jensedler/spielzeitmanager:latest
```

## Umgebungsvariablen

In der Once-Konfiguration folgende Variablen setzen:

| Variable | Beschreibung |
|---|---|
| `APP_PASSWORD` | Login-Passwort für die App |
| `SECRET_KEY` | Langer zufälliger String für Flask-Sessions |

## Persistente Daten

Die SQLite-Datenbank wird in `/storage/spielzeit.db` gespeichert.
Once mountet `/storage` automatisch als persistentes Volume.

## Updates deployen

```bash
# Lokal: neuen Tag setzen
git tag v1.2.3
git push --tags

# → GitHub Actions baut das Image automatisch
# → Once zieht das neue Image beim nächsten Update-Zyklus
```

## Manuelles Update auf dem Server

```bash
once update
```
