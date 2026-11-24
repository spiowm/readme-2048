"""SVG дошки для README: без скриптів і зовнішніх шрифтів, світла й темна тема через prefers-color-scheme."""

from html import escape

CELL, GAP, PAD = 72, 10, 16
BOARD = 4 * CELL + 5 * GAP
W = BOARD + 2 * PAD
TOP = 92
H = TOP + BOARD + 52

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
    "text{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-weight:700}"
    ".bg{fill:#faf8ef}.grid{fill:#bbada0}.slot{fill:#cdc1b4}"
    ".title{fill:#776e65;font-size:40px}.sub{fill:#8f7a66;font-size:13px;font-weight:500}"
    ".box{fill:#bbada0}.lbl{fill:#eee4da;font-size:11px}.num{fill:#fff;font-size:18px}"
    ".foot{fill:#776e65;font-size:14px;font-weight:600}.c{text-anchor:middle;dominant-baseline:central}"
    "@media (prefers-color-scheme:dark){.bg{fill:#161b22}.grid{fill:#3d444d}.slot{fill:#2d333b}"
    ".title{fill:#e6edf3}.sub{fill:#9198a1}.box{fill:#2d333b}.lbl{fill:#9198a1}.num{fill:#e6edf3}"
    ".foot{fill:#e6edf3}}"
)


def _tile(v, x, y):
    bg, fg = TILES.get(v, ("#3c3a32", "#f9f6f2"))
    size = FONT.get(len(str(v)), 22)
    return (
        f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="6" fill="{bg}"/>'
        f'<text class="c" x="{x + CELL / 2}" y="{y + CELL / 2 + 1}" fill="{fg}" font-size="{size}">{v}</text>'
    )


def _score_box(label, value, right):
    w = 84
    x = right - w
    return (
        f'<rect class="box" x="{x}" y="{PAD}" width="{w}" height="48" rx="6"/>'
        f'<text class="lbl c" x="{x + w / 2}" y="{PAD + 14}">{label}</text>'
        f'<text class="num c" x="{x + w / 2}" y="{PAD + 33}">{value}</text>'
    )


def board_svg(state):
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f"<style>{STYLE}</style>",
        f'<rect class="bg" width="{W}" height="{H}" rx="12"/>',
        f'<text class="title" x="{PAD}" y="{PAD + 34}">2048</text>',
        f'<text class="sub" x="{PAD}" y="{PAD + 62}">One shared game. Like in monobank, it ends at 2048.</text>',
        _score_box("BEST", state["best"], W - PAD),
        _score_box("SCORE", state["score"], W - PAD - 92),
        f'<rect class="grid" x="{PAD}" y="{TOP}" width="{BOARD}" height="{BOARD}" rx="8"/>',
    ]
    for r in range(4):
        for c in range(4):
            x = PAD + GAP + c * (CELL + GAP)
            y = TOP + GAP + r * (CELL + GAP)
            v = state["board"][r][c]
            parts.append(
                _tile(v, x, y)
                if v
                else f'<rect class="slot" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="6"/>'
            )

    if state["status"] == "won":
        foot = f"2048 reached in {state['moves']} moves! Any arrow starts a new game."
    elif state["status"] == "lost":
        foot = "No moves left. Any arrow starts a new game."
    else:
        n = state["players"]
        foot = f"Game #{state['game']} · move {state['moves']} · {n} player{'s' if n != 1 else ''} so far"
    parts.append(
        f'<text class="foot c" x="{W / 2}" y="{TOP + BOARD + 27}">{escape(foot)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
