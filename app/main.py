"""Сервер спільної партії 2048 для GitHub README: картинка дошки й посилання-ходи з редиректом назад."""

import hashlib
import hmac
import json
import os
import random
import re
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
SECRET = os.environ.get("PLAYER_SALT", "dev-salt").encode()
STATS_TOKEN = os.environ.get("STATS_TOKEN", "")
MIN_INTERVAL = float(os.environ.get("MIN_MOVE_INTERVAL", "0.3"))

BOT_UA = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|telegram|discord|whatsapp|curl|wget|python",
    re.IGNORECASE,
)
NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

# Статичні клавіші з «вічним» кешем: camo і браузер тримають їх у себе. Зміна вигляду = нова версія в шляху.
STATIC_VERSION = "v1"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
STATIC = {name: open(os.path.join(STATIC_DIR, name), "rb").read() for name in os.listdir(STATIC_DIR)}
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
lock = threading.Lock()
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA synchronous=NORMAL")
db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
db.execute("CREATE TABLE IF NOT EXISTS events (ts REAL, day TEXT, kind TEXT, player TEXT)")
db.execute("CREATE INDEX IF NOT EXISTS events_day ON events(day, kind)")


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
    row = db.execute("SELECT v FROM kv WHERE k='state'").fetchone()
    return json.loads(row[0]) if row else _new_state()


def _save_state():
    db.execute("INSERT OR REPLACE INTO kv VALUES ('state', ?)", (json.dumps(state),))


state = _load_state()
players = {p for (p,) in db.execute("SELECT DISTINCT player FROM events WHERE kind='move'")}
state["players"] = len(players)
last_move = {}
svg_cache = board_svg(state)


def _log(kind, player=None):
    now = time.time()
    day = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
    db.execute("INSERT INTO events VALUES (?, ?, ?, ?)", (now, day, kind, player))


def _player_id(request):
    # За проксі Cloudflare справжня адреса в CF-Connecting-IP; без нього адреса з'єднання
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
    return hmac.new(SECRET, ip.encode(), hashlib.sha256).hexdigest()[:16]


@app.get("/board")
def board():
    with lock:
        _log("view")
        body = svg_cache
    return Response(body, media_type="image/svg+xml", headers=NO_CACHE)


@app.api_route("/move/{direction}", methods=["GET", "HEAD"])
def make_move(direction: str, request: Request):
    global state, svg_cache
    back = RedirectResponse(PROFILE_URL, status_code=303, headers=NO_CACHE)
    if request.method != "GET" or direction not in game.DIRECTIONS:
        return back
    if BOT_UA.search(request.headers.get("user-agent", "")):
        return back

    player = _player_id(request)
    now = time.monotonic()
    with lock:
        if now - last_move.get(player, 0) < MIN_INTERVAL:
            return back
        last_move[player] = now

        if state["status"] != "playing":
            state = _new_state(state)
        new_board, gained, changed = game.move(state["board"], direction)
        if changed:
            state["board"] = new_board
            state["score"] += gained
            state["moves"] += 1
            state["best"] = max(state["best"], state["score"])
            if game.has_goal(new_board):
                state["status"] = "won"
            else:
                game.spawn(new_board)
                if not game.can_move(new_board):
                    state["status"] = "lost"
            if player not in players:
                players.add(player)
                state["players"] = len(players)
            _log("move", player)
            _save_state()
            svg_cache = board_svg(state)
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
    if not STATS_TOKEN or not hmac.compare_digest(token, STATS_TOKEN):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    with lock:
        rows = db.execute(
            "SELECT day, SUM(kind='view'), SUM(kind='move'), COUNT(DISTINCT CASE WHEN kind='move' THEN player END) "
            "FROM events GROUP BY day ORDER BY day DESC LIMIT 60"
        ).fetchall()
    return {
        "days": [{"day": d, "views": v, "moves": m, "players": p} for d, v, m, p in rows],
        "players_total": len(players),
        "state": {k: state[k] for k in ("game", "moves", "score", "best", "status")},
    }


random.seed()
