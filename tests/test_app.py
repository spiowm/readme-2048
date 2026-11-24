import importlib
import ipaddress
import random

import pytest
from fastapi.testclient import TestClient

from app import game

HUMAN = {"User-Agent": "Mozilla/5.0", "Sec-Fetch-Mode": "navigate"}
COLUMN = [[2, 0, 0, 0], [4, 0, 0, 0], [8, 0, 0, 0], [16, 0, 0, 0]]  # ліворуч і вгору ходу немає


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "game.db"))
    monkeypatch.setenv("PLAYER_SALT", "test")
    monkeypatch.setenv("STATS_TOKEN", "secret")
    monkeypatch.setenv("MIN_MOVE_INTERVAL", "0")
    import app.main as main

    main = importlib.reload(main)
    main.state.update(board=[row[:] for row in COLUMN], status="playing")
    return main


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def move(client, direction, headers=HUMAN):
    return client.get(f"/move/{direction}", headers=headers, follow_redirects=False)


def as_player(app_module, monkeypatch, name):
    monkeypatch.setattr(app_module, "_client_ip", lambda request: name)


# Логіка гри


def test_merge_and_score():
    assert game.move([[2, 2, 4, 4]] + [[0] * 4] * 3, "left")[:2] == ([[4, 8, 0, 0]] + [[0] * 4] * 3, 12)


def test_merge_happens_once_per_tile():
    assert game.move([[2, 2, 2, 2]] + [[0] * 4] * 3, "left")[0][0] == [4, 4, 0, 0]
    assert game.move([[4, 4, 8, 0]] + [[0] * 4] * 3, "left")[0][0] == [8, 8, 0, 0]


def test_directions_are_rotations_of_left():
    board = [[random.Random(i).choice([0, 2, 4, 8]) for i in range(r * 4, r * 4 + 4)] for r in range(4)]
    right = game.move([row[::-1] for row in board], "left")[0]
    assert game.move(board, "right")[0] == [row[::-1] for row in right]


def test_goal_ends_on_2048():
    assert game.has_goal(game.move([[1024, 1024, 0, 0]] + [[0] * 4] * 3, "left")[0])


# Ходи через HTTP


def test_valid_move_redirects_and_counts(client, app_module):
    assert move(client, "right").status_code == 303
    assert app_module.state["moves"] == 1 and app_module.state["players"] == 1


def test_impossible_move_keeps_page(client, app_module):
    assert move(client, "left").status_code == 204
    assert app_module.state["moves"] == 0


def test_bots_prefetch_and_head_do_not_move(client, app_module):
    assert move(client, "right", {"User-Agent": "curl/8"}).status_code == 204
    assert move(client, "right", {**HUMAN, "Sec-Fetch-Mode": "no-cors"}).status_code == 204
    assert move(client, "right", {**HUMAN, "Sec-Purpose": "prefetch"}).status_code == 204
    assert client.head("/move/right", headers=HUMAN).status_code == 204
    assert move(client, "diagonal").status_code == 204
    assert app_module.state["moves"] == 0


def test_stale_view_gets_a_refresh(client, app_module, monkeypatch):
    as_player(app_module, monkeypatch, "alice")
    assert move(client, "right").status_code == 303  # alice рухає дошку
    board = app_module.state["board"]
    blocked = next(d for d in game.DIRECTIONS if not game.move(board, d)[2])
    as_player(app_module, monkeypatch, "bob")
    assert move(client, blocked).status_code == 303  # bob бачив стару дошку: оновити сторінку
    assert move(client, blocked).status_code == 204  # тепер бачить свіжу: нічого не робити


def test_any_arrow_after_the_end_starts_a_new_game(client, app_module):
    app_module.state["status"] = "won"
    game_no = app_module.state["game"]
    assert move(client, "left").status_code == 303
    assert app_module.state["game"] == game_no + 1
    assert f"game #{game_no + 1}" in app_module.svg_cache


def test_failed_write_keeps_previous_state(client, app_module, monkeypatch):
    class Broken:
        in_transaction = False

        def execute(self, *args):
            raise app_module.sqlite3.OperationalError("disk full")

    monkeypatch.setattr(app_module, "db", Broken())
    before = [row[:] for row in app_module.state["board"]]
    assert move(client, "right").status_code == 503
    assert app_module.state["board"] == before and app_module.state["moves"] == 0


# Гравці, кеш, статистика


def test_cf_header_trusted_only_from_cloudflare(app_module):
    class Req:
        def __init__(self, peer, cf):
            self.client = type("C", (), {"host": peer})
            self.headers = {"cf-connecting-ip": cf}

    assert ipaddress.ip_address("104.16.0.1") in app_module.CLOUDFLARE[11]
    assert app_module._client_ip(Req("104.16.0.1", "203.0.113.7")) == "203.0.113.7"
    assert app_module._client_ip(Req("198.51.100.9", "203.0.113.7")) == "198.51.100.9"


def test_board_is_never_cached(client):
    response = client.get("/board")
    assert response.headers["content-type"] == "image/svg+xml"
    assert "no-store" in response.headers["cache-control"]


def test_keys_are_cached_for_a_year(client):
    response = client.get("/static/v1/key-up.svg")
    assert response.status_code == 200 and "immutable" in response.headers["cache-control"]
    assert client.get("/static/v0/key-up.svg").status_code == 404


def test_stats_need_the_token(client):
    client.get("/board")
    assert client.get("/stats?token=wrong").status_code == 403
    assert client.get("/stats?token=ключ").status_code == 403
    data = client.get("/stats?token=secret").json()
    assert data["days"][0]["views"] == 1
