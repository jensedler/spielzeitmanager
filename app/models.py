from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Player(db.Model):
    __tablename__ = "players"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Game(db.Model):
    __tablename__ = "games"
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    opponent = db.Column(db.String(100), nullable=False)
    # setup | running | paused | finished
    status = db.Column(db.String(20), default="setup")
    # number of outfield players simultaneously on the pitch (sum of formation lines)
    field_players = db.Column(db.Integer, default=7)
    # canonical formation string, e.g. "3-3-2" (goalkeeper not included)
    formation = db.Column(db.String(20), default="7")
    half_length_seconds = db.Column(db.Integer, default=1500)
    # number of halves / periods; 2 for a normal match, more to cover a tournament
    num_halves = db.Column(db.Integer, default=2)
    # which half is currently running/paused (1..num_halves)
    current_half = db.Column(db.Integer, default=1)
    # wall-clock time when the current running period started
    period_started_at = db.Column(db.Float, nullable=True)
    # total game seconds already elapsed when last period started
    game_seconds_at_period_start = db.Column(db.Float, default=0.0)
    # total game seconds elapsed at the moment the current half began (0 for
    # the first half; set to whatever the total was when the second half
    # was started) — lets the UI show a per-half clock that starts at 0:00
    half_start_seconds = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    players = db.relationship("GamePlayer", backref="game", lazy=True, cascade="all, delete-orphan")
    events = db.relationship("PlayerEvent", backref="game", lazy=True, cascade="all, delete-orphan")

    def current_game_seconds(self):
        import time
        if self.status == "running" and self.period_started_at:
            elapsed = time.time() - self.period_started_at
            return self.game_seconds_at_period_start + elapsed
        return self.game_seconds_at_period_start

    @property
    def game_length_seconds(self):
        return self.half_length_seconds * self.num_halves

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "opponent": self.opponent,
            "status": self.status,
            "field_players": self.field_players,
            "formation": self.formation,
            "formation_lines": [int(n) for n in self.formation.split("-")] if self.formation else [],
            "half_length_seconds": self.half_length_seconds,
            "num_halves": self.num_halves,
            "current_half": self.current_half,
            "game_length_seconds": self.game_length_seconds,
            "half_start_seconds": self.half_start_seconds,
            "period_started_at": self.period_started_at,
            "game_seconds_at_period_start": self.game_seconds_at_period_start,
            "game_seconds": self.current_game_seconds(),
        }


class GamePlayer(db.Model):
    __tablename__ = "game_players"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    # True = currently on the field, False = on bench
    on_field = db.Column(db.Boolean, default=False)
    # 0 = goalkeeper, 1..N = formation line (1 = defense, ascending toward attack), NULL = bench
    slot_line = db.Column(db.Integer, nullable=True)
    # position within the line, 0-based
    slot_index = db.Column(db.Integer, nullable=True)

    player = db.relationship("Player")

    def to_dict(self):
        return {
            "id": self.id,
            "player_id": self.player_id,
            "name": self.player.name,
            "on_field": self.on_field,
            "slot_line": self.slot_line,
            "slot_index": self.slot_index,
        }


class PlayerEvent(db.Model):
    """Records when a player goes on/off the field with the game time at that moment."""
    __tablename__ = "player_events"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    # 'on' or 'off'
    event_type = db.Column(db.String(3), nullable=False)
    game_seconds = db.Column(db.Float, nullable=False)
    # True if the player was in the goalkeeper slot for this event
    is_gk = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    player = db.relationship("Player")
