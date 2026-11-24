"""Сервер спільної партії 2048 для GitHub README: картинка дошки й посилання-ходи з редиректом назад."""

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse

from . import game
from .render import board_svg

PROFILE_URL = os.environ.get("PROFILE_URL", "https://github.com/spiowm")
DB_PATH = os.environ.get("DB_PATH", "/data/game.db")
STATS_TOKEN = os.environ.get("STATS_TOKEN", "")
MIN_INTERVAL = float(os.environ.get("MIN_MOVE_INTERVAL", "0.3"))
# Скільки секунд після чужого ходу неможливий хід вважається кліком по застарілій дошці
STALE_WINDOW = 120
VIEW_FLUSH_SECONDS = 60

BOT_UA = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|telegram|discord|whatsapp|curl|wget|python",
    re.IGNORECASE,
)
NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}
# https://www.cloudflare.com/ips/ (24.11.2026): лише від цих адрес довіряти CF-Connecting-IP
CLOUDFLARE = [
    ipaddress.ip_network(n)
    for n in (
        "173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22 141.101.64.0/18 108.162.192.0/18 "
        "190.93.240.0/20 188.114.96.0/20 197.234.240.0/22 198.41.128.0/17 162.158.0.0/15 104.16.0.0/13 "
        "104.24.0.0/14 172.64.0.0/13 131.0.72.0/22 2400:cb00::/32 2606:4700::/32 2803:f800::/32 "
        "2405:b500::/32 2405:8100::/32 2a06:98c0::/29 2c0f:f248::/32"
    ).split()
]

# Статичні клавіші з «вічним» кешем: camo і браузер тримають їх у себе. Зміна вигляду = нова версія в шляху.
STATIC_VERSION = "v1"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
STATIC = {name: open(os.path.join(STATIC_DIR, name), "rb").read() for name in os.listdir(STATIC_DIR)}
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}

os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA synchronous=NORMAL")
db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
db.execute("CREATE TABLE IF NOT EXISTS events (ts REAL, day TEXT, kind TEXT, player TEXT)")
db.execute("CREATE INDEX IF NOT EXISTS events_day ON events(day, kind)")
db.execute("CREATE TABLE IF NOT EXISTS daily_views (day TEXT PRIMARY KEY, views INTEGER NOT NULL)")


def _kv(key):
    row = db.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
    return row[0] if row else None


def _salt():
    """Сіль для хешу IP: зі змінної середовища або згенерована один раз і збережена в базі."""
    if os.environ.get("PLAYER_SALT"):
        return os.environ["PLAYER_SALT"].encode()
    salt = _kv("salt") or secrets.token_urlsafe(24)
    db.execute("INSERT OR IGNORE INTO kv VALUES ('salt', ?)", (salt,))
    return salt.encode()


def _new_state(prev=None):
    return {
        "board": game.new_board(),
        "score": 0,
        "moves": 0,
        "status": "playing",
        "game": (prev["game"] + 1) if prev else 1,
        "best": prev["best"] if prev else 0,
        "players": prev["players"] if prev else 0,
    }


def _load_state():
    """Стан з бази; пошкоджений або неповний запис замінюється новою партією, а не валить старт."""
    try:
        st = json.loads(_kv("state") or "null")
        board = st["board"]
        assert len(board) == 4 and all(len(row) == 4 for row in board)
        assert st["status"] in ("playing", "won", "lost")
        for key in ("score", "moves", "game", "best", "players"):
            assert isinstance(st[key], int)
        return st
    except (TypeError, KeyError, ValueError, AssertionError):
        return _new_state()


def _day():
    return datetime.now(UTC).strftime("%Y-%m-%d")


SALT = _salt()
state = _load_state()
players = {p for (p,) in db.execute("SELECT DISTINCT player FROM events WHERE kind='move'")}
state["players"] = len(players)
svg_cache = board_svg(state)
last_move = {}  # гравець -> час останнього запиту на хід (monotonic)
last_change = {"at": 0.0, "by": None}  # коли й ким востаннє змінено дошку
pending_views = {}  # день -> перегляди, ще не записані в базу
last_flush = time.monotonic()
lock = threading.Lock()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _flush_views():
    """Перегляди пишуться пачкою раз на хвилину: картинка дошки не залежить від запису в базу."""
    global last_flush
    last_flush = time.monotonic()
    try:
        for day, n in list(pending_views.items()):
            db.execute(
                "INSERT INTO daily_views VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET views = views + excluded.views",
                (day, n),
            )
            del pending_views[day]
    except sqlite3.Error:
        pass  # лічильник лишається в пам'яті до наступної спроби


def _client_ip(request):
    """Адреса гравця: CF-Connecting-IP лише коли запит справді прийшов від Cloudflare."""
    peer = request.client.host if request.client else ""
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer or "unknown"
    if any(peer_ip in net for net in CLOUDFLARE):
        try:
            return str(ipaddress.ip_address(request.headers.get("cf-connecting-ip", "").strip()))
        except ValueError:
            pass
    return peer


def _player_id(request):
    return hmac.new(SALT, _client_ip(request).encode(), hashlib.sha256).hexdigest()[:16]


def _is_click(request):
    """Відсіює префетч, прев'ю й ботів: хід робить лише навігація людини по посиланню."""
    if request.method != "GET" or BOT_UA.search(request.headers.get("user-agent", "")):
        return False
    mode = request.headers.get("sec-fetch-mode")
    purpose = (request.headers.get("sec-purpose") or request.headers.get("purpose") or "").lower()
    return (mode is None or mode == "navigate") and "prefetch" not in purpose


def _prune(now):
    if len(last_move) > 10_000:
        for player, at in list(last_move.items()):
            if now - at > STALE_WINDOW:
                del last_move[player]


@app.get("/board")
def board():
    with lock:
        day = _day()
        pending_views[day] = pending_views.get(day, 0) + 1
        if time.monotonic() - last_flush > VIEW_FLUSH_SECONDS:
            _flush_views()
        body = svg_cache
    return Response(body, media_type="image/svg+xml", headers=NO_CACHE)


@app.api_route("/move/{direction}", methods=["GET", "HEAD"])
def make_move(direction: str, request: Request):
    global state, svg_cache
    back = RedirectResponse(PROFILE_URL, status_code=303, headers=NO_CACHE)
    # 204: браузер лишається на сторінці без перезавантаження, коли дошка не змінилась
    stay = Response(status_code=204, headers=NO_CACHE)
    if direction not in game.DIRECTIONS or not _is_click(request):
        return stay

    player = _player_id(request)
    with lock:
        now = time.monotonic()
        prev = last_move.get(player)
        if prev is not None and now - prev < MIN_INTERVAL:
            return stay
        last_move[player] = now
        _prune(now)

        # Новий стан рахується окремо й підміняє поточний лише після успішного запису в базу
        reset = state["status"] != "playing"
        new = _new_state(state) if reset else dict(state)
        board_after, gained, changed = game.move(new["board"], direction)
        if not (changed or reset):
            # Неможливий хід. Якщо після попереднього запиту гравця дошку змінив хтось інший,
            # він, найімовірніше, бачить стару картинку: оновити сторінку замість тиші.
            seen = prev if prev is not None else now - STALE_WINDOW
            if last_change["at"] > seen and last_change["by"] != player:
                return back
            return stay

        is_new = changed and player not in players
        if changed:
            new["board"] = board_after
            new["score"] += gained
            new["moves"] += 1
            new["best"] = max(new["best"], new["score"])
            if game.has_goal(board_after):
                new["status"] = "won"
            else:
                game.spawn(board_after)
                if not game.can_move(board_after):
                    new["status"] = "lost"
            new["players"] = len(players) + is_new
        svg = board_svg(new)

        try:
            db.execute("BEGIN")
            db.execute("INSERT OR REPLACE INTO kv VALUES ('state', ?)", (json.dumps(new),))
            if changed:
                db.execute("INSERT INTO events VALUES (?, ?, 'move', ?)", (time.time(), _day(), player))
            db.execute("COMMIT")
        except sqlite3.Error:
            if db.in_transaction:
                db.execute("ROLLBACK")
            return Response(status_code=503, headers=NO_CACHE)

        state, svg_cache = new, svg
        if is_new:
            players.add(player)
        last_change.update(at=now, by=player)
    return back


@app.get("/")
def root():
    return RedirectResponse(PROFILE_URL, status_code=302)


@app.get("/static/{version}/{name}")
def static(version: str, name: str):
    body = STATIC.get(name)
    if version != STATIC_VERSION or body is None:
        return Response(status_code=404)
    return Response(body, media_type="image/svg+xml", headers=IMMUTABLE)


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return "User-agent: *\nDisallow: /\n"


@app.get("/health")
def health():
    return {"ok": True, "game": state["game"], "moves": state["moves"]}


@app.get("/stats")
def stats(token: str = ""):
    if not STATS_TOKEN or not hmac.compare_digest(token.encode(), STATS_TOKEN.encode()):
        return JSONResponse({"error": "forbidden"}, status_code=403, headers=NO_CACHE)
    with lock:
        _flush_views()
        days = {}
        # Старі перегляди лежать подіями 'view', нові агрегатами по днях
        for day, n in db.execute("SELECT day, COUNT(*) FROM events WHERE kind='view' GROUP BY day"):
            days.setdefault(day, {"views": 0, "moves": 0, "players": 0})["views"] += n
        for day, n in db.execute("SELECT day, views FROM daily_views"):
            days.setdefault(day, {"views": 0, "moves": 0, "players": 0})["views"] += n
        for day, n in pending_views.items():
            days.setdefault(day, {"views": 0, "moves": 0, "players": 0})["views"] += n
        moves = "SELECT day, COUNT(*), COUNT(DISTINCT player) FROM events WHERE kind='move' GROUP BY day"
        for day, m, p in db.execute(moves):
            days.setdefault(day, {"views": 0, "moves": 0, "players": 0}).update(moves=m, players=p)
        snapshot = {k: state[k] for k in ("game", "moves", "score", "best", "status")}
        total = len(players)
    rows = [{"day": d, **v} for d, v in sorted(days.items(), reverse=True)[:60]]
    return JSONResponse({"days": rows, "players_total": total, "state": snapshot}, headers=NO_CACHE)
