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

- Spiellänge: Anzahl Halbzeiten wird bei Spielanlage festgelegt (`num_halves`, Default 2, 1..20 – mehr für ein Turnier), Länge pro Halbzeit ebenfalls frei (`half_length_seconds`, Default 25 Min); alle Halbzeiten sind gleich lang
- Status-Automat: `setup` → `running` ⇄ `paused` → `finished`; `Game.current_half` (1..`num_halves`) hält die aktuell laufende/pausierte Halbzeit
- `POST /games/<id>/next-half`: aus `paused` in die nächste Halbzeit (nur solange `current_half < num_halves`)
- Formation wird bei Spielanlage als String eingegeben (z.B. `3-3-2` oder `343`, siehe `app/formation.py`) und bestimmt Anzahl und Anordnung der Feldspieler; sie ist danach fix
- Zusätzlich zur Formation ist immer genau 1 Torhüter zu besetzen (nicht Teil der Formationsangabe)
- Aufstellung erfolgt slot-basiert: jeder `GamePlayer` bekommt eine `slot_line` (0 = Torhüter, 1..N = Formationslinie) + `slot_index`; Ein-/Auswechseln = Antippen eines Slots im Spielfeld, Auswahl eines Bankspielers (`POST /games/<id>/assign-slot`)
- Der Kader eines Spiels ist nicht auf die bei Anlage gewählten Spieler beschränkt: über `POST /games/<id>/roster` (UI: „Spieler zum Kader hinzufügen" in der Spielansicht) können jederzeit vor Spielende weitere bereits angelegte Spieler ergänzt werden
- Optionale Anstoßzeit `Game.kickoff_time` (`"HH:MM"`, nullable). Die Spielübersicht (`GET /games`) sortiert nach `date` absteigend, dann Spiele mit Uhrzeit vor Spielen ohne, dann `kickoff_time` aufsteigend – so stehen mehrere Spiele eines Tages in zeitlicher Reihenfolge
- `PATCH /games/<id>` bearbeitet ein Spiel: `date`, `opponent`, `kickoff_time` sind immer änderbar; `formation`, `half_length_minutes`, `num_halves` nur im Status `setup` (sonst 400). Formationsänderung setzt alle Slot-Zuordnungen zurück und berechnet `field_players` neu
- Ein `GamePlayer` kann pro Spiel als Torhüter markiert werden (`GamePlayer.is_goalkeeper`): bei Anlage/Roster über `goalkeeper_ids`, danach über `POST /games/<id>/set-goalkeeper` `{player_id, is_goalkeeper}` (UI: „TW"-Schalter im Anlage-Formular und bei Bankspielern). Als Torhüter markierte Spieler zählen **nicht** in den Fair-Share-Nenner – egal ob im Feld oder auf der Bank – und bekommen keinen Fair-Share-Wert
- Fair Share = (Halbzeitlänge × `num_halves` × Anzahl Feldspieler laut Formation) / Anzahl Kaderspieler **ohne** `is_goalkeeper` (`Game.game_length_seconds` = Halbzeitlänge × `num_halves`; im State als `outfield_squad_size`)
- Torhüterzeit wird separat erfasst (`PlayerEvent.is_gk`, gesetzt beim Spielen im Slot `slot_line == 0`) und angezeigt, fließt aber nicht in die Fair-Share-Berechnung ein
- Timer läuft client-seitig (Alpine.js), Events werden ans Backend gesendet
- Auto-Stop am Ende jeder Halbzeit (`half_length_seconds × current_half`); bei der letzten Halbzeit ist das gleichzeitig das Spielende
- Die Timer-Anzeige zeigt primär die Zeit der laufenden Halbzeit (startet bei jedem Halbzeitwechsel wieder bei 0:00), Gesamtspielzeit wird kleiner darunter angezeigt; Basis dafür ist `Game.half_start_seconds` (Gesamtzeit-Stand zu Beginn der aktuellen Halbzeit), gesetzt in `start`/`next-half`

## Umgebungsvariablen

| Variable | Beschreibung | Default |
|---|---|---|
| `APP_PASSWORD` | Passwort für Login | `changeme` |
| `DATABASE_URL` | SQLite-Pfad | `sqlite:////storage/spielzeit.db` |
| `SECRET_KEY` | Flask Session Key | zufällig generiert |
