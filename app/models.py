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
    # setup | first_half | paused_first | second_half | paused_second | finished
    status = db.Column(db.String(20), default="setup")
    field_players = db.Column(db.Integer, default=7)
    # wall-clock time when the current running period started
    period_started_at = db.Column(db.Float, nullable=True)
    # total game seconds already elapsed when last period started
    game_seconds_at_period_start = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    players = db.relationship("GamePlayer", backref="game", lazy=True, cascade="all, delete-orphan")
    events = db.relationship("PlayerEvent", backref="game", lazy=True, cascade="all, delete-orphan")

    def current_game_seconds(self):
        import time
        if self.status in ("first_half", "second_half") and self.period_started_at:
            elapsed = time.time() - self.period_started_at
            return self.game_seconds_at_period_start + elapsed
        return self.game_seconds_at_period_start

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "opponent": self.opponent,
            "status": self.status,
            "field_players": self.field_players,
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

    player = db.relationship("Player")

    def to_dict(self):
        return {
            "id": self.id,
            "player_id": self.player_id,
            "name": self.player.name,
            "on_field": self.on_field,
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    player = db.relationship("Player")
