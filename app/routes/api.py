import time
from flask import Blueprint, jsonify, request, session, redirect, url_for
from ..models import db, Player, Game, GamePlayer, PlayerEvent
from ..formation import parse_formation, FormationError

api_bp = Blueprint("api", __name__)


def _parse_kickoff(value):
    """Normalise a kick-off time. Returns (value, error):
    ("HH:MM", None) on success, (None, None) when empty/omitted,
    (None, "…") when the input is not a valid HH:MM time."""
    if value is None or str(value).strip() == "":
        return None, None
    from datetime import datetime as _dt
    try:
        t = _dt.strptime(str(value).strip(), "%H:%M")
    except ValueError:
        return None, "Ungültige Anstoßzeit (Format HH:MM)"
    return t.strftime("%H:%M"), None


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
    games = Game.query.order_by(
        Game.date.desc(),
        Game.kickoff_time.is_(None),   # games with a kick-off time first within a day
        Game.kickoff_time.asc(),       # then chronological by kick-off
        Game.id.asc(),
    ).all()
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

    kickoff_time, kickoff_err = _parse_kickoff(data.get("kickoff_time"))
    if kickoff_err:
        return jsonify({"error": kickoff_err}), 400

    try:
        lines, formation = parse_formation(data.get("formation", ""))
    except FormationError as e:
        return jsonify({"error": str(e)}), 400
    field_players = sum(lines)

    try:
        half_length_minutes = float(data.get("half_length_minutes", 25))
    except (TypeError, ValueError):
        return jsonify({"error": "Ungültige Halbzeitlänge"}), 400
    if half_length_minutes <= 0:
        return jsonify({"error": "Halbzeitlänge muss größer als 0 sein"}), 400
    half_length_seconds = int(half_length_minutes * 60)

    try:
        num_halves = int(data.get("num_halves", 2))
    except (TypeError, ValueError):
        return jsonify({"error": "Ungültige Anzahl Halbzeiten"}), 400
    if num_halves < 1 or num_halves > 20:
        return jsonify({"error": "Anzahl Halbzeiten muss zwischen 1 und 20 liegen"}), 400

    game = Game(
        date=game_date,
        kickoff_time=kickoff_time,
        opponent=opponent,
        field_players=field_players,
        formation=formation,
        half_length_seconds=half_length_seconds,
        num_halves=num_halves,
        current_half=1,
    )
    db.session.add(game)
    db.session.flush()

    player_ids = data.get("player_ids", [])
    goalkeeper_ids = set(data.get("goalkeeper_ids", []))
    for pid in player_ids:
        gp = GamePlayer(game_id=game.id, player_id=pid, on_field=False,
                        is_goalkeeper=pid in goalkeeper_ids)
        db.session.add(gp)

    db.session.commit()
    return jsonify(game.to_dict()), 201


@api_bp.route("/games/<int:game_id>", methods=["PATCH"])
@api_login_required
def update_game(game_id):
    """Edit an existing game. Date, opponent and kick-off time can always be
    changed; formation, half length and number of halves only while the game
    is still in `setup` (changing them later would break slot assignments and
    the timer maths). Changing the formation clears all slot assignments."""
    game = Game.query.get_or_404(game_id)
    data = request.get_json() or {}

    if "opponent" in data:
        opponent = (data.get("opponent") or "").strip()
        if not opponent:
            return jsonify({"error": "Gegner erforderlich"}), 400
        game.opponent = opponent

    if "date" in data:
        from datetime import date
        try:
            game.date = date.fromisoformat(data["date"])
        except (TypeError, ValueError):
            return jsonify({"error": "Ungültiges Datum"}), 400

    if "kickoff_time" in data:
        kickoff_time, kickoff_err = _parse_kickoff(data.get("kickoff_time"))
        if kickoff_err:
            return jsonify({"error": kickoff_err}), 400
        game.kickoff_time = kickoff_time

    setup_only_fields = ("formation", "half_length_minutes", "num_halves")
    if any(f in data for f in setup_only_fields) and game.status != "setup":
        return jsonify({"error": "Formation, Halbzeitlänge und Anzahl Halbzeiten "
                                 "können nur vor dem Anpfiff geändert werden"}), 400

    if "half_length_minutes" in data:
        try:
            half_length_minutes = float(data["half_length_minutes"])
        except (TypeError, ValueError):
            return jsonify({"error": "Ungültige Halbzeitlänge"}), 400
        if half_length_minutes <= 0:
            return jsonify({"error": "Halbzeitlänge muss größer als 0 sein"}), 400
        game.half_length_seconds = int(half_length_minutes * 60)

    if "num_halves" in data:
        try:
            num_halves = int(data["num_halves"])
        except (TypeError, ValueError):
            return jsonify({"error": "Ungültige Anzahl Halbzeiten"}), 400
        if num_halves < 1 or num_halves > 20:
            return jsonify({"error": "Anzahl Halbzeiten muss zwischen 1 und 20 liegen"}), 400
        game.num_halves = num_halves

    if "formation" in data:
        try:
            lines, formation = parse_formation(data.get("formation", ""))
        except FormationError as e:
            return jsonify({"error": str(e)}), 400
        if formation != game.formation:
            game.formation = formation
            game.field_players = sum(lines)
            # slot indices may no longer be valid – send everyone back to the bench
            for gp in GamePlayer.query.filter_by(game_id=game_id):
                gp.slot_line = None
                gp.slot_index = None
                gp.on_field = False

    db.session.commit()
    return jsonify(game.to_dict())


@api_bp.route("/games/<int:game_id>", methods=["DELETE"])
@api_login_required
def delete_game(game_id):
    game = Game.query.get_or_404(game_id)
    db.session.delete(game)
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/games/<int:game_id>/roster", methods=["POST"])
@api_login_required
def add_to_roster(game_id):
    """Add one or more existing players to a game's squad (as bench players).
    Allowed any time before the game is finished, so a squad forgotten or
    missing at game creation can still be filled in later."""
    game = Game.query.get_or_404(game_id)
    if game.status == "finished":
        return jsonify({"error": "Spiel ist bereits beendet"}), 400

    data = request.get_json()
    player_ids = data.get("player_ids", [])
    goalkeeper_ids = set(data.get("goalkeeper_ids", []))
    existing = {gp.player_id for gp in GamePlayer.query.filter_by(game_id=game_id).all()}

    added = 0
    for pid in player_ids:
        if pid in existing or not Player.query.get(pid):
            continue
        db.session.add(GamePlayer(game_id=game_id, player_id=pid, on_field=False,
                                  is_goalkeeper=pid in goalkeeper_ids))
        existing.add(pid)
        added += 1

    db.session.commit()
    return jsonify({"ok": True, "added": added})


@api_bp.route("/games/<int:game_id>/set-goalkeeper", methods=["POST"])
@api_login_required
def set_goalkeeper(game_id):
    """Mark or unmark a squad player as this game's designated goalkeeper.
    Designated goalkeepers are left out of the fair-share denominator, so a
    keeper waiting on the bench no longer dilutes everyone else's target."""
    game = Game.query.get_or_404(game_id)
    if game.status == "finished":
        return jsonify({"error": "Spiel ist bereits beendet"}), 400

    data = request.get_json() or {}
    gp = GamePlayer.query.filter_by(
        game_id=game_id, player_id=data.get("player_id")
    ).first_or_404()
    gp.is_goalkeeper = bool(data.get("is_goalkeeper"))
    db.session.commit()
    return jsonify({"ok": True, "player_id": gp.player_id, "is_goalkeeper": gp.is_goalkeeper})


@api_bp.route("/games/<int:game_id>/state", methods=["GET"])
@api_login_required
def game_state(game_id):
    game = Game.query.get_or_404(game_id)
    roster = GamePlayer.query.filter_by(game_id=game_id).all()
    game_secs = game.current_game_seconds()

    player_times, gk_times = _compute_player_times(game_id, game_secs)
    squad_size = len(roster)
    # designated goalkeepers are excluded from the fair-share denominator
    outfield_squad_size = sum(1 for gp in roster if not gp.is_goalkeeper)
    fp = game.field_players
    game_length = game.game_length_seconds
    fair_share = (game_length * fp) / outfield_squad_size if outfield_squad_size > 0 else 0

    players_data = []
    for gp in sorted(roster, key=lambda x: x.player.name):
        pt = player_times.get(gp.player_id, 0.0)
        gt = gk_times.get(gp.player_id, 0.0)
        players_data.append({
            **gp.to_dict(),
            "played_seconds": pt,
            "gk_seconds": gt,
            "fair_share_seconds": 0 if gp.is_goalkeeper else fair_share,
        })

    return jsonify({
        "game": game.to_dict(),
        "players": players_data,
        "squad_size": squad_size,
        "outfield_squad_size": outfield_squad_size,
        "fair_share_seconds": fair_share,
    })


def _compute_player_times(game_id, current_game_seconds):
    """Returns (field_times, gk_times): dicts of player_id -> total seconds played,
    split by whether the player was in the goalkeeper slot for that stretch."""
    events = (
        PlayerEvent.query
        .filter_by(game_id=game_id)
        .order_by(PlayerEvent.game_seconds)
        .all()
    )
    field_times = {}
    gk_times = {}
    on_since = {}
    for ev in events:
        pid = ev.player_id
        if ev.event_type == "on":
            on_since[pid] = (ev.game_seconds, ev.is_gk)
        elif ev.event_type == "off":
            if pid in on_since:
                start, is_gk = on_since.pop(pid)
                duration = ev.game_seconds - start
                bucket = gk_times if is_gk else field_times
                bucket[pid] = bucket.get(pid, 0.0) + duration
    # still on field
    for pid, (start, is_gk) in on_since.items():
        duration = current_game_seconds - start
        bucket = gk_times if is_gk else field_times
        bucket[pid] = bucket.get(pid, 0.0) + duration
    return field_times, gk_times


# ── Game actions ───────────────────────────────────────────────────────────

@api_bp.route("/games/<int:game_id>/assign-slot", methods=["POST"])
@api_login_required
def assign_slot(game_id):
    """Assign a bench player to a pitch slot (GK=0, or formation line 1..N).
    If the slot is already occupied, the previous occupant goes back to the bench.
    Works both pre-game (setup, no events) and during/paused a running game
    (records substitution events)."""
    game = Game.query.get_or_404(game_id)
    if game.status == "finished":
        return jsonify({"error": "Spiel ist bereits beendet"}), 400

    data = request.get_json()
    try:
        slot_line = int(data["slot_line"])
        slot_index = int(data["slot_index"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Ungültiger Slot"}), 400

    incoming = GamePlayer.query.filter_by(game_id=game_id, player_id=data.get("player_id")).first_or_404()
    if incoming.slot_line is not None:
        return jsonify({"error": "Spieler ist bereits im Feld"}), 400

    outgoing = GamePlayer.query.filter_by(
        game_id=game_id, slot_line=slot_line, slot_index=slot_index
    ).first()

    running_or_paused = game.status in ("running", "paused")
    if running_or_paused:
        game_secs = game.current_game_seconds()
        if outgoing:
            ev = PlayerEvent(game_id=game_id, player_id=outgoing.player_id, event_type="off",
                              game_seconds=game_secs, is_gk=(outgoing.slot_line == 0))
            db.session.add(ev)
        ev = PlayerEvent(game_id=game_id, player_id=incoming.player_id, event_type="on",
                          game_seconds=game_secs, is_gk=(slot_line == 0))
        db.session.add(ev)

    if outgoing:
        outgoing.slot_line = None
        outgoing.slot_index = None
        outgoing.on_field = False

    incoming.slot_line = slot_line
    incoming.slot_index = slot_index
    incoming.on_field = True

    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/games/<int:game_id>/unassign-slot", methods=["POST"])
@api_login_required
def unassign_slot(game_id):
    """Setup only: send a slotted player back to the bench without a replacement."""
    game = Game.query.get_or_404(game_id)
    if game.status != "setup":
        return jsonify({"error": "Nur vor Spielstart möglich"}), 400
    data = request.get_json()
    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=data.get("player_id")).first_or_404()
    gp.slot_line = None
    gp.slot_index = None
    gp.on_field = False
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/games/<int:game_id>/start", methods=["POST"])
@api_login_required
def start_game(game_id):
    game = Game.query.get_or_404(game_id)
    now = time.time()

    if game.status == "setup":
        on_count = GamePlayer.query.filter_by(game_id=game_id, on_field=True).count()
        required = game.field_players + 1
        if on_count != required:
            return jsonify({"error": f"Bitte genau {required} Spieler (inkl. Torhüter) aufstellen (aktuell: {on_count})"}), 400
        game.status = "running"
        game.current_half = 1
        game.period_started_at = now
        game.game_seconds_at_period_start = 0.0
        game.half_start_seconds = 0.0
        for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
            ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="on",
                              game_seconds=0.0, is_gk=(gp.slot_line == 0))
            db.session.add(ev)

    elif game.status == "paused":
        # Resume the current half
        game.status = "running"
        game.period_started_at = now
        current_secs = game.game_seconds_at_period_start
        for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
            ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="on",
                              game_seconds=current_secs, is_gk=(gp.slot_line == 0))
            db.session.add(ev)

    else:
        return jsonify({"error": f"Ungültiger Status: {game.status}"}), 400

    db.session.commit()
    return jsonify(game.to_dict())


@api_bp.route("/games/<int:game_id>/next-half", methods=["POST"])
@api_login_required
def next_half(game_id):
    """Advance from a paused half to the start of the next one."""
    game = Game.query.get_or_404(game_id)
    if game.status != "paused":
        return jsonify({"error": "Aktuelle Halbzeit muss pausiert sein"}), 400
    if game.current_half >= game.num_halves:
        return jsonify({"error": "Letzte Halbzeit ist bereits erreicht"}), 400

    now = time.time()
    game.current_half += 1
    game.status = "running"
    game.period_started_at = now
    current_secs = game.game_seconds_at_period_start
    game.half_start_seconds = current_secs

    for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
        ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="on",
                          game_seconds=current_secs, is_gk=(gp.slot_line == 0))
        db.session.add(ev)

    db.session.commit()
    return jsonify(game.to_dict())


@api_bp.route("/games/<int:game_id>/pause", methods=["POST"])
@api_login_required
def pause_game(game_id):
    game = Game.query.get_or_404(game_id)
    now = time.time()

    if game.status == "running":
        elapsed = now - game.period_started_at
        # cap at the current half's boundary
        half_end = game.half_length_seconds * game.current_half
        new_secs = min(game.game_seconds_at_period_start + elapsed, half_end)
        game.status = "paused"
        game.game_seconds_at_period_start = new_secs
        game.period_started_at = None
        _record_off_for_on_field(game_id, new_secs)

    elif game.status == "paused":
        # Resume
        current_secs = game.game_seconds_at_period_start
        game.status = "running"
        game.period_started_at = now
        for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
            ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="on",
                              game_seconds=current_secs, is_gk=(gp.slot_line == 0))
            db.session.add(ev)

    else:
        return jsonify({"error": f"Kein aktives Spiel"}), 400

    db.session.commit()
    return jsonify(game.to_dict())


@api_bp.route("/games/<int:game_id>/finish", methods=["POST"])
@api_login_required
def finish_game(game_id):
    game = Game.query.get_or_404(game_id)
    now = time.time()

    if game.status == "running":
        elapsed = now - game.period_started_at
        new_secs = min(game.game_seconds_at_period_start + elapsed, game.game_length_seconds)
        game.game_seconds_at_period_start = new_secs
        _record_off_for_on_field(game_id, new_secs)
    elif game.status == "paused":
        _record_off_for_on_field(game_id, game.game_seconds_at_period_start)

    game.status = "finished"
    game.period_started_at = None
    db.session.commit()
    return jsonify(game.to_dict())


def _record_off_for_on_field(game_id, game_seconds):
    for gp in GamePlayer.query.filter_by(game_id=game_id, on_field=True):
        ev = PlayerEvent(game_id=game_id, player_id=gp.player_id, event_type="off",
                          game_seconds=game_seconds, is_gk=(gp.slot_line == 0))
        db.session.add(ev)
