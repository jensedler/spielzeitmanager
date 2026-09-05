"""
Schema migrations for Spielzeitmanager.

Each migration is a tuple (version, description, sql).
Versions are applied in order; already-applied ones are skipped.
Run standalone:  python migrate.py
Or called automatically from app/__init__.py on startup.
"""

import os
import sqlite3

MIGRATIONS = [
    (
        1,
        "Initial schema",
        """
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY,
            date DATE NOT NULL,
            opponent TEXT NOT NULL,
            status TEXT DEFAULT 'setup',
            period_started_at REAL,
            game_seconds_at_period_start REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS game_players (
            id INTEGER PRIMARY KEY,
            game_id INTEGER REFERENCES games(id),
            player_id INTEGER REFERENCES players(id),
            on_field INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS player_events (
            id INTEGER PRIMARY KEY,
            game_id INTEGER REFERENCES games(id),
            player_id INTEGER REFERENCES players(id),
            event_type TEXT NOT NULL,
            game_seconds REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        2,
        "Add field_players to games",
        "ALTER TABLE games ADD COLUMN field_players INTEGER DEFAULT 7;",
    ),
    (
        3,
        "Add formation, configurable half length, and goalkeeper slot tracking",
        """
        ALTER TABLE games ADD COLUMN formation TEXT;
        ALTER TABLE games ADD COLUMN half_length_seconds INTEGER DEFAULT 1500;
        ALTER TABLE game_players ADD COLUMN slot_line INTEGER;
        ALTER TABLE game_players ADD COLUMN slot_index INTEGER;
        ALTER TABLE player_events ADD COLUMN is_gk INTEGER DEFAULT 0;
        UPDATE games SET half_length_seconds = 1500 WHERE half_length_seconds IS NULL;
        UPDATE games SET formation = CAST(field_players AS TEXT) WHERE formation IS NULL;
        """,
    ),
    (
        4,
        "Add half_start_seconds to games for a per-half timer",
        """
        ALTER TABLE games ADD COLUMN half_start_seconds REAL DEFAULT 0.0;
        UPDATE games SET half_start_seconds = 0.0 WHERE half_start_seconds IS NULL;
        UPDATE games SET half_start_seconds = half_length_seconds
            WHERE status IN ('second_half', 'paused_second', 'finished');
        """,
    ),
    (
        5,
        "Configurable number of halves; generalise the game status machine",
        """
        ALTER TABLE games ADD COLUMN num_halves INTEGER DEFAULT 2;
        ALTER TABLE games ADD COLUMN current_half INTEGER DEFAULT 1;
        UPDATE games SET num_halves = 2 WHERE num_halves IS NULL;
        UPDATE games SET current_half = 1 WHERE current_half IS NULL;
        UPDATE games SET current_half = 2 WHERE status IN ('second_half', 'paused_second');
        UPDATE games SET current_half = num_halves WHERE status = 'finished';
        UPDATE games SET status = 'running' WHERE status IN ('first_half', 'second_half');
        UPDATE games SET status = 'paused' WHERE status IN ('paused_first', 'paused_second');
        """,
    ),
    (
        6,
        "Add kickoff time to games and a per-game goalkeeper flag",
        """
        ALTER TABLE games ADD COLUMN kickoff_time TEXT;
        ALTER TABLE game_players ADD COLUMN is_goalkeeper INTEGER DEFAULT 0;
        UPDATE game_players SET is_goalkeeper = 0 WHERE is_goalkeeper IS NULL;
        """,
    ),
]


def _db_path():
    url = os.environ.get("DATABASE_URL", "sqlite:///instance/spielzeit.db")
    # strip sqlite:/// or sqlite:////
    if url.startswith("sqlite:////"):
        return url[len("sqlite:///"):]
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        if not os.path.isabs(path):
            base = os.path.dirname(os.path.abspath(__file__))
            return os.path.join(base, path)
        return path
    raise ValueError(f"Unsupported DATABASE_URL scheme: {url}")


def run_migrations(db_path=None):
    if db_path is None:
        db_path = _db_path()

    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.commit()

    applied = {row[0] for row in con.execute("SELECT version FROM schema_version")}

    for version, description, sql in MIGRATIONS:
        if version in applied:
            continue
        print(f"  Applying migration {version}: {description}")
        for statement in sql.strip().split(";"):
            statement = statement.strip()
            if statement:
                con.execute(statement)
        con.execute(
            "INSERT INTO schema_version (version, description) VALUES (?, ?)",
            (version, description),
        )
        con.commit()
        print(f"  Migration {version} applied.")

    con.close()


if __name__ == "__main__":
    print("Running database migrations…")
    run_migrations()
    print("Done.")
