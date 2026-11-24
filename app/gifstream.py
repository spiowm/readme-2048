"""Кадри дошки як GIF-блоки для нескінченного стріму: заголовок один раз, далі кадр за кадром."""

import io
import os
import struct

from PIL import Image, ImageDraw, ImageFont

SCALE = 2
CELL, GAP = 72, 10
BOARD = 4 * CELL + 5 * GAP
TOP, BOTTOM = 36, 38
W, H = BOARD, TOP + BOARD + BOTTOM
PX_W, PX_H = W * SCALE, H * SCALE

BG = (246, 248, 250)
GRID, SLOT = (187, 173, 160), (205, 193, 180)
TEXT, DIM = (31, 35, 40), (89, 99, 110)
TILES = {
    2: ((238, 228, 218), (119, 110, 101)),
    4: ((237, 224, 200), (119, 110, 101)),
    8: ((242, 177, 121), (249, 246, 242)),
    16: ((245, 149, 99), (249, 246, 242)),
    32: ((246, 124, 95), (249, 246, 242)),
    64: ((246, 94, 59), (249, 246, 242)),
    128: ((237, 207, 114), (249, 246, 242)),
    256: ((237, 204, 97), (249, 246, 242)),
    512: ((237, 200, 80), (249, 246, 242)),
    1024: ((237, 197, 63), (249, 246, 242)),
    2048: ((237, 194, 46), (249, 246, 242)),
}
TILE_FONT = {1: 40, 2: 38, 3: 32, 4: 26}
FONT_PATHS = [
    os.environ.get("FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
]
_fonts = {}


def _font(size):
    if size not in _fonts:
        path = next(p for p in FONT_PATHS if p and os.path.exists(p))
        _fonts[size] = ImageFont.truetype(path, size * SCALE)
    return _fonts[size]


def render(state, note=None):
    """Кадр дошки як RGB-зображення у 2x масштабі."""
    s = SCALE
    im = Image.new("RGB", (PX_W, PX_H), BG)
    d = ImageDraw.Draw(im)
    d.text((2 * s, 22 * s), f"score {state['score']}", font=_font(18), fill=DIM, anchor="ls")
    d.text(((W - 2) * s, 22 * s), f"best {state['best']}", font=_font(18), fill=DIM, anchor="rs")
    d.rounded_rectangle([0, TOP * s, BOARD * s - 1, (TOP + BOARD) * s - 1], radius=8 * s, fill=GRID)
    for r in range(4):
        for c in range(4):
            x = (GAP + c * (CELL + GAP)) * s
            y = (TOP + GAP + r * (CELL + GAP)) * s
            v = state["board"][r][c]
            bg, fg = TILES.get(v, ((60, 58, 50), (249, 246, 242))) if v else (SLOT, None)
            d.rounded_rectangle([x, y, x + CELL * s - 1, y + CELL * s - 1], radius=6 * s, fill=bg)
            if v:
                font = _font(TILE_FONT.get(len(str(v)), 22))
                d.text((x + CELL * s / 2, y + CELL * s / 2), str(v), font=font, fill=fg, anchor="mm")
    if note is None:
        if state["status"] == "won":
            note = "2048! Any arrow starts a new game"
        elif state["status"] == "lost":
            note = "No moves left. Any arrow starts a new game"
        else:
            n = state["players"]
            note = f"game #{state['game']} · move {state['moves']} · {n} player{'s' if n != 1 else ''}"
    d.text((W / 2 * s, (TOP + BOARD + 26) * s), note, font=_font(17), fill=DIM, anchor="ms")
    return im


def header():
    """Заголовок GIF без глобальної палітри: кожен кадр несе власну."""
    return b"GIF89a" + struct.pack("<HHBBB", PX_W, PX_H, 0x70, 0, 0)


def frame(im):
    """Один кадр як GIF-блоки: керування показом, дескриптор з локальною палітрою, дані LZW."""
    p = im.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
    buf = io.BytesIO()
    p.save(buf, "GIF", optimize=False)
    raw = buf.getvalue()

    packed = raw[10]
    gct = 3 * (2 ** ((packed & 0x07) + 1)) if packed & 0x80 else 0
    pos = 13
    palette = raw[pos : pos + gct]
    pos += gct
    while raw[pos] != 0x2C:  # пропуск розширень до дескриптора зображення
        pos += 2
        while raw[pos]:
            pos += raw[pos] + 1
        pos += 1
    desc = bytearray(raw[pos : pos + 10])
    desc[9] = 0x80 | (packed & 0x07)  # локальна палітра того ж розміру
    data = raw[pos + 10 : -1]  # LZW без трейлера 0x3B
    gce = b"\x21\xf9\x04\x00\x00\x00\x00\x00"
    return gce + bytes(desc) + palette + data


TRAILER = b"\x3b"
