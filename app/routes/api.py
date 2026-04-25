import time
from flask import Blueprint, jsonify, request, session, redirect, url_for
from ..models import db, Player, Game, GamePlayer, PlayerEvent

api_bp = Blueprint("api", __name__)


def api_login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Players ────────────────────────────────────────────────────────────────

@api_bp.route("/players", methods=["GET"])
@api_login_required
def list_players():
    players = Player.query.order_by(Player.name).all()
    return jsonify([p.to_dict() for p in players])


@api_bp.route("/players", methods=["POST"])
@api_login_required
def create_player():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name erforderlich"}), 400
    player = Player(name=name)
    db.session.add(player)
    db.session.commit()
    return jsonify(player.to_dict()), 201


@api_bp.route("/players/<int:player_id>", methods=["DELETE"])
@api_login_required
def delete_player(player_id):
    player = Player.query.get_or_404(player_id)
    db.session.delete(player)
    db.session.commit()
    return jsonify({"ok": True})


# ── Games ──────────────────────────────────────────────────────────────────

@api_bp.route("/games", methods=["GET"])
@api_login_required
def list_games():
    games = Game.query.order_by(Game.date.desc(), Game.id.desc()).all()
    return jsonify([g.to_dict() for g in games])


@api_bp.route("/games", methods=["POST"])
@api_login_required
def create_game():
    data = request.get_json()
    from datetime import date
    try:
        game_date = date.fromisoformat(data["date"])
    except (KeyError, ValueError):
        return jsonify({"error": "Ungültiges Datum"}), 400
    opponent = (data.get("opponent") or "").strip()
    if not opponent:
        return jsonify({"error": "Gegner erforderlich"}), 400

    game = Game(date=game_date, opponent=opponent)
    db.session.add(game)
    db.session.flush()

    player_ids = data.get("player_ids", [])
    for pid in player_ids:
        gp = GamePlayer(game_id=game.id, player_id=pid, on_field=False)
        db.session.add(gp)

    db.session.commit()
    return jsonify(game.to_dict()), 201


@api_bp.route("/games/<int:game_id>", methods=["DELETE"])
@api_login_required
def delete_game(game_id):
    game = Game.query.get_or_404(game_id)
    db.session.delete(game)
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/games/<int:game_id>/state", methods=["GET"])
@api_login_required
def game_state(game_id):
    game = Game.query.get_or_404(game_id)
    roster = GamePlayer.query.filter_by(game_id=game_id).all()
    game_secs = game.current_game_seconds()

    player_times = _compute_player_times(game_id, game_secs)
    squad_size = len(roster)
    fair_share = (50 * 60 * 7) / squad_size if squad_size > 0 else 0

    players_data = []
    for gp in sorted(roster, key=lambda x: x.player.name):
        pt = player_times.get(gp.player_id, 0.0)
        players_data.append({
            **gp.to_dict(),
            "played_seconds": pt,
            "fair_share_seconds": fair_share,
        })

    return jsonify({
        "game": game.to_dict(),
        "players": players_data,
        "squad_size": squad_size,
        "fair_share_seconds": fair_share,
    })


def _compute_player_times(game_id, current_game_seconds):
    """Returns dict of player_id -> total played seconds."""
    events = (
        PlayerEvent.query
        .filter_by(game_id=game_id)
        .order_by(PlayerEvent.game_seconds)
        .all()
    )
    times = {}
    on_since = {}
    for ev in events:
        pid = ev.player_id
        if ev.event_type == "on":
            on_since[pid] = ev.game_seconds
        elif ev.event_type == "off":
            if pid in on_since:
                times[pid] = times.get(pid, 0.0) + (ev.game_seconds - on_since.pop(pid))
    # still on field
    for pid, start in on_since.items():
        times[pid] = times.get(pid, 0.0) + (current_game_seconds - start)
    return times


# ── Game actions ───────────────────────────────────────────────────────────

@api_bp.route("/games/<int:game_id>/toggle-player", methods=["POST"])
@api_login_required
def toggle_player(game_id):
    """Pre-game: toggle on_field flag."""
    game = Game.query.get_or_404(game_id)
    if game.status != "setup":
        return jsonify({"error": "Nur vor Spielstart möglich"}), 400
    data = request.get_json()
    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=data["player_id"]).first_or_404()
    gp.on_field = not gp.on_field
    db.session.commit()
    return jsonify(gp.to_dict())


@api_bp.route("/games/<int:game_id>/start", methods=["POST"])
@api_login_required
def start_game(game_id):
    game = Game.query.get_or_404(game_id)
    now = time.time()

    if game.status == "setup":
        game.status = "first_half"
        game.period_started_at = now
        game.game_seconds_at_period_start = 0.0
        # Record 'on' events for all players currently on field
        for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
            ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="on", game_seconds=0.0)
            db.session.add(ev)

    elif game.status in ("paused_first", "paused_second"):
        half = "first_half" if game.status == "paused_first" else "second_half"
        game.status = half
        game.period_started_at = now
        # Record 'on' for players currently on field
        current_secs = game.game_seconds_at_period_start
        for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
            ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="on", game_seconds=current_secs)
            db.session.add(ev)

    elif game.status == "first_half":
        # Manual transition to second half (shouldn't normally happen, auto-stop handles this)
        elapsed = now - game.period_started_at
        game.game_seconds_at_period_start = min(game.game_seconds_at_period_start + elapsed, 25 * 60)
        game.status = "paused_first"
        game.period_started_at = None
        _record_off_for_on_field(game_id, game.game_seconds_at_period_start)

    else:
        return jsonify({"error": f"Ungültiger Status: {game.status}"}), 400

    db.session.commit()
    return jsonify(game.to_dict())


@api_bp.route("/games/<int:game_id>/start-second-half", methods=["POST"])
@api_login_required
def start_second_half(game_id):
    game = Game.query.get_or_404(game_id)
    if game.status not in ("paused_first",):
        return jsonify({"error": "Erste Halbzeit muss beendet sein"}), 400

    now = time.time()
    game.status = "second_half"
    game.period_started_at = now
    current_secs = game.game_seconds_at_period_start

    for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
        ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="on", game_seconds=current_secs)
        db.session.add(ev)

    db.session.commit()
    return jsonify(game.to_dict())


@api_bp.route("/games/<int:game_id>/pause", methods=["POST"])
@api_login_required
def pause_game(game_id):
    game = Game.query.get_or_404(game_id)
    now = time.time()

    if game.status in ("first_half", "second_half"):
        elapsed = now - game.period_started_at
        new_secs = game.game_seconds_at_period_start + elapsed
        # cap at half boundaries
        if game.status == "first_half":
            new_secs = min(new_secs, 25 * 60)
            game.status = "paused_first"
        else:
            new_secs = min(new_secs, 50 * 60)
            game.status = "paused_second"
        game.game_seconds_at_period_start = new_secs
        game.period_started_at = None
        _record_off_for_on_field(game_id, new_secs)

    elif game.status in ("paused_first", "paused_second"):
        # Resume
        current_secs = game.game_seconds_at_period_start
        half = "first_half" if game.status == "paused_first" else "second_half"
        game.status = half
        game.period_started_at = now
        for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
            ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="on", game_seconds=current_secs)
            db.session.add(ev)

    else:
        return jsonify({"error": f"Kein aktives Spiel"}), 400

    db.session.commit()
    return jsonify(game.to_dict())


@api_bp.route("/games/<int:game_id>/substitute", methods=["POST"])
@api_login_required
def substitute(game_id):
    """Toggle a player on/off during the game."""
    game = Game.query.get_or_404(game_id)
    running = game.status in ("first_half", "second_half")
    paused = game.status in ("paused_first", "paused_second")

    if not (running or paused):
        return jsonify({"error": "Spiel läuft nicht"}), 400

    data = request.get_json()
    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=data["player_id"]).first_or_404()
    game_secs = game.current_game_seconds()

    if gp.on_field:
        gp.on_field = False
        ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="off", game_seconds=game_secs)
        db.session.add(ev)
    else:
        gp.on_field = True
        ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="on", game_seconds=game_secs)
        db.session.add(ev)

    db.session.commit()
    return jsonify(gp.to_dict())


@api_bp.route("/games/<int:game_id>/finish", methods=["POST"])
@api_login_required
def finish_game(game_id):
    game = Game.query.get_or_404(game_id)
    now = time.time()

    if game.status in ("second_half",):
        elapsed = now - game.period_started_at
        new_secs = min(game.game_seconds_at_period_start + elapsed, 50 * 60)
        game.game_seconds_at_period_start = new_secs
        _record_off_for_on_field(game_id, new_secs)
    elif game.status == "paused_second":
        _record_off_for_on_field(game_id, game.game_seconds_at_period_start)

    game.status = "finished"
    game.period_started_at = None
    db.session.commit()
    return jsonify(game.to_dict())


def _record_off_for_on_field(game_id, game_seconds):
    for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
        ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="off", game_seconds=game_seconds)
        db.session.add(ev)
