# Spielzeitmanager

Web-App zur Erfassung der Spielzeit von Fußballspielern im Jugendfußball.

## Stack

- **Backend**: Python 3.12 + Flask
- **Datenbank**: SQLite via SQLAlchemy (liegt in `/storage/spielzeit.db`)
- **Frontend**: Alpine.js + Tailwind CSS (CDN, kein Build-Schritt)
- **PWA**: Service Worker + Web Manifest (Offline-Fähigkeit)
- **Deployment**: Docker + Once (ghcr.io)

## Entwicklung

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
APP_PASSWORD=test flask run
```

## Deployment

Tags triggern den CI/CD-Build:

```bash
git tag v1.0.0
git push --tags
```

GitHub Actions baut das Docker-Image und pusht nach `ghcr.io/jensedler/spielzeitmanager`.

## Spiellogik

- Spiellänge: 2 × 25 Minuten
- Maximal 7 Spieler gleichzeitig auf dem Platz
- Fair Share = (50 min × 7) / Anzahl Spieler im Kader
- Timer läuft client-seitig (Alpine.js), Events werden ans Backend gesendet
- Auto-Stop bei 25:00 (Halbzeit) und 50:00 (Spielende)

## Umgebungsvariablen

| Variable | Beschreibung | Default |
|---|---|---|
| `APP_PASSWORD` | Passwort für Login | `changeme` |
| `DATABASE_URL` | SQLite-Pfad | `sqlite:////storage/spielzeit.db` |
| `SECRET_KEY` | Flask Session Key | zufällig generiert |
