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

GitHub Actions baut das Docker-Image und pusht nach `ghcr.io/jensedler/spielzeitmanager`. Von dort läuft eine **produktive Instanz über Once** (Self-Hosting-Plattform) mit echten Daten.

**Wichtig für jedes Update mit Schema-Änderung**: Neue Migrationen in `migrate.py` müssen vor dem Taggen/Deployen getestet werden (z.B. lokal gegen eine Kopie der Produktions-DB oder mit realistischen Altdaten), damit beim Rollout keine Daten auf der produktiven Instanz verloren gehen.

## Spiellogik

- Spiellänge: 2 Halbzeiten, Länge pro Halbzeit wird bei Spielanlage frei festgelegt (`half_length_seconds`, Default 25 Min)
- Formation wird bei Spielanlage als String eingegeben (z.B. `3-3-2` oder `343`, siehe `app/formation.py`) und bestimmt Anzahl und Anordnung der Feldspieler; sie ist danach fix
- Zusätzlich zur Formation ist immer genau 1 Torhüter zu besetzen (nicht Teil der Formationsangabe)
- Aufstellung erfolgt slot-basiert: jeder `GamePlayer` bekommt eine `slot_line` (0 = Torhüter, 1..N = Formationslinie) + `slot_index`; Ein-/Auswechseln = Antippen eines Slots im Spielfeld, Auswahl eines Bankspielers (`POST /games/<id>/assign-slot`)
- Der Kader eines Spiels ist nicht auf die bei Anlage gewählten Spieler beschränkt: über `POST /games/<id>/roster` (UI: „Spieler zum Kader hinzufügen" in der Spielansicht) können jederzeit vor Spielende weitere bereits angelegte Spieler ergänzt werden
- Fair Share = (Halbzeitlänge × 2 × Anzahl Feldspieler laut Formation) / Anzahl Spieler im Kader
- Torhüterzeit wird separat erfasst (`PlayerEvent.is_gk`) und angezeigt, fließt aber nicht in die Fair-Share-Berechnung ein
- Timer läuft client-seitig (Alpine.js), Events werden ans Backend gesendet
- Auto-Stop bei Ende der jeweiligen Halbzeitlänge und bei doppelter Halbzeitlänge (Spielende)
- Die Timer-Anzeige zeigt primär die Zeit der laufenden Halbzeit (startet bei Wechsel in die 2. Halbzeit wieder bei 0:00), Gesamtspielzeit wird kleiner darunter angezeigt; Basis dafür ist `Game.half_start_seconds` (Gesamtzeit-Stand zu Beginn der aktuellen Halbzeit), gesetzt in `start`/`start-second-half`

## Umgebungsvariablen

| Variable | Beschreibung | Default |
|---|---|---|
| `APP_PASSWORD` | Passwort für Login | `changeme` |
| `DATABASE_URL` | SQLite-Pfad | `sqlite:////storage/spielzeit.db` |
| `SECRET_KEY` | Flask Session Key | zufällig generiert |
