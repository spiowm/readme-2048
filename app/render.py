"""Компактний SVG дошки для README: без фону, скриптів і зовнішніх шрифтів; темна тема через prefers-color-scheme."""

from html import escape

CELL, GAP = 72, 10
BOARD = 4 * CELL + 5 * GAP
W = BOARD
TOP = 36
H = TOP + BOARD + 38

TILES = {
    2: ("#eee4da", "#776e65"),
    4: ("#ede0c8", "#776e65"),
    8: ("#f2b179", "#f9f6f2"),
    16: ("#f59563", "#f9f6f2"),
    32: ("#f67c5f", "#f9f6f2"),
    64: ("#f65e3b", "#f9f6f2"),
    128: ("#edcf72", "#f9f6f2"),
    256: ("#edcc61", "#f9f6f2"),
    512: ("#edc850", "#f9f6f2"),
    1024: ("#edc53f", "#f9f6f2"),
    2048: ("#edc22e", "#f9f6f2"),
}
FONT = {1: 40, 2: 38, 3: 32, 4: 26}

STYLE = (
    "text{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-weight:600}"
    ".t{font-size:20px}.f{font-size:17px}"
    ".grid{fill:#bbada0}.slot{fill:#cdc1b4}.t{fill:#59636e}.v{font-weight:700;fill:#1f2328}"
    ".c{text-anchor:middle;dominant-baseline:central;font-weight:700}"
    "@media (prefers-color-scheme:dark){.grid{fill:#3d444d}.slot{fill:#2d333b}.t{fill:#9198a1}.v{fill:#f0f6fc}}"
)


def _tile(v, x, y):
    bg, fg = TILES.get(v, ("#3c3a32", "#f9f6f2"))
    size = FONT.get(len(str(v)), 22)
    return (
        f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="6" fill="{bg}"/>'
        f'<text class="c" x="{x + CELL / 2}" y="{y + CELL / 2 + 1}" fill="{fg}" font-size="{size}">{v}</text>'
    )


def board_svg(state):
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f"<style>{STYLE}</style>",
        f'<text class="t" x="2" y="22">score <tspan class="v">{state["score"]}</tspan></text>',
        f'<text class="t" x="{W - 2}" y="22" text-anchor="end">best <tspan class="v">{state["best"]}</tspan></text>',
        f'<rect class="grid" x="0" y="{TOP}" width="{BOARD}" height="{BOARD}" rx="8"/>',
    ]
    for r in range(4):
        for c in range(4):
            x = GAP + c * (CELL + GAP)
            y = TOP + GAP + r * (CELL + GAP)
            v = state["board"][r][c]
            parts.append(
                _tile(v, x, y) if v else f'<rect class="slot" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="6"/>'
            )

    if state["status"] == "won":
        foot = "2048! Any arrow starts a new game"
    elif state["status"] == "lost":
        foot = "No moves left · any arrow restarts"
    else:
        n = state["players"]
        foot = f"game #{state['game']} · move {state['moves']} · {n} player{'s' if n != 1 else ''}"
    parts.append(f'<text class="t f" x="{W / 2}" y="{TOP + BOARD + 26}" text-anchor="middle">{escape(foot)}</text>')
    parts.append("</svg>")
    return "".join(parts)
