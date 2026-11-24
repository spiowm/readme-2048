"""2048 за правилами monobank: партія закінчується, щойно з'являється плитка 2048."""

import random

SIZE = 4
GOAL = 2048
DIRECTIONS = ("up", "down", "left", "right")


def empty_board():
    return [[0] * SIZE for _ in range(SIZE)]


def spawn(board, rng=random):
    cells = [(r, c) for r in range(SIZE) for c in range(SIZE) if board[r][c] == 0]
    if not cells:
        return board
    r, c = rng.choice(cells)
    board[r][c] = 2 if rng.random() < 0.9 else 4
    return board


def new_board(rng=random):
    return spawn(spawn(empty_board(), rng), rng)


def _slide_left(row):
    """Зсув одного рядка вліво: (новий рядок, набрані очки)."""
    tiles = [v for v in row if v]
    out, gained, i = [], 0, 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            out.append(tiles[i] * 2)
            gained += tiles[i] * 2
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    return out + [0] * (SIZE - len(out)), gained


def _transpose(board):
    return [list(col) for col in zip(*board)]


def move(board, direction):
    """Повертає (нова дошка, очки, чи змінилась дошка)."""
    if direction == "left":
        rows = board
    elif direction == "right":
        rows = [row[::-1] for row in board]
    elif direction == "up":
        rows = _transpose(board)
    elif direction == "down":
        rows = [row[::-1] for row in _transpose(board)]
    else:
        raise ValueError(direction)

    slid, gained = [], 0
    for row in rows:
        new_row, g = _slide_left(row)
        slid.append(new_row)
        gained += g

    if direction == "right":
        result = [row[::-1] for row in slid]
    elif direction == "up":
        result = _transpose(slid)
    elif direction == "down":
        result = _transpose([row[::-1] for row in slid])
    else:
        result = slid
    return result, gained, result != board


def has_goal(board):
    return any(v >= GOAL for row in board for v in row)


def can_move(board):
    return any(move(board, d)[2] for d in DIRECTIONS)
