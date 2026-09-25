# -*- coding: utf-8 -*-
r"""FONT.PXL 안 «ｷﾞﾙ» 그림 두 개를 «길»로 바꾼다 (build_font 끝에서 부른다).

  python tools/gilgfx.py        → my files/그래픽/길_비교.png (원본 / 한글 확대 비교)

FONT.PXL = 4bpp 256×512. 값 1(흰)…5(회색) = 채움 세로 명암, 7 = 어두운 테두리 (숫자와 같은 규칙).
  큰 것  : (갈무리11 굵은체) HUD 줄 «F Lv. HP % ｷﾞﾙ ? / 0‥9», x72‥94 · y321‥335 — 채움 324‥334 (11줄), 테두리 323·335.
  작은 것: 상점 값 «700ｷﾞﾙ» 줄, x80‥96 · y368‥375 — 윗 테두리 368, 채움 369‥375 (7줄), 아래 테두리 없음(사용자 지정).
           ★위(y360‥367) x86‥87 에 창 틀 조각, 아래 y376 에 선(값 5)이 있어 칸이 8줄뿐이다 → 지우는 범위도 368‥375 만.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bdf

FONTDIR = os.path.join('C:' + os.sep, 'claude', 'utils', 'font', 'Galmuri-v2.40.3')
OUT = 7

# 작은 «길» 6×7 손그림 — 갈무리7 의 길은 ㄹ 이 뭉개져서 직접 그린다 (ㄱ+ㅣ 2줄, ㄹ 5줄).
SMALL = ['####.#',
         '...#.#',
         '######',
         '.....#',
         '######',
         '#.....',
         '######']
BIG_BOX = (72, 321, 94, 335)      # x0, y0, x1, y1 (끝 포함)
SMALL_BOX = (80, 368, 96, 375)


def unpack(d):
    a = np.frombuffer(bytes(d), np.uint8).reshape(512, 128)
    return np.stack([a & 15, a >> 4], 2).reshape(512, 256).copy()


def pack(o):
    return (o[:, 0::2] | (o[:, 1::2] << 4)).astype(np.uint8).tobytes()


def ramp(n):
    """채움 세로 명암 1→5 (위가 밝다)"""
    return [1 + round(4 * i / (n - 1)) for i in range(n)]


def stamp(o, mask, x0, y0, box, bottom_outline):
    bx0, by0, bx1, by1 = box
    o[by0:by1 + 1, bx0:bx1 + 1] = 0
    h, w = mask.shape
    sh = ramp(h)
    ring = np.zeros((h + 2, w + 2), bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ring[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] |= mask
    for yy in range(h + 2):
        for xx in range(w + 2):
            y, x = y0 - 1 + yy, x0 - 1 + xx
            inside = 1 <= yy <= h and 1 <= xx <= w and mask[yy - 1, xx - 1]
            if inside:
                o[y, x] = sh[yy - 1]
            elif ring[yy, xx]:
                if y > by1 and not bottom_outline:
                    continue
                assert bx0 <= x <= bx1 and by0 <= y <= by1, ('길 그림이 칸 밖', x, y)
                o[y, x] = OUT


def big_mask():
    """갈무리11 굵은체 «길» 10×11 (사용자 확인 2026-09-26 «큰 거 그대로»)"""
    pts, _ = bdf.Font(os.path.join(FONTDIR, 'Galmuri11-Bold.bdf')).draw('길')
    ox = min(x for x, _ in pts); oy = min(y for _, y in pts)
    w = max(x for x, _ in pts) - ox + 1; h = max(y for _, y in pts) - oy + 1
    m = np.zeros((h, w), bool)
    for x, y in pts:
        m[y - oy, x - ox] = True
    assert m.shape == (11, 10), m.shape
    return m


def apply(d):
    """FONT.PXL 바이트 → «길» 두 개를 그린 바이트"""
    o = unpack(d)
    stamp(o, big_mask(), 74, 324, BIG_BOX, True)                 # 원본 ｷﾞﾙ 왼끝 x72·테두리 한 칸 → 채움은 x74 부터
    sm = np.array([[c == '#' for c in r] for r in SMALL])
    stamp(o, sm, 82, 369, SMALL_BOX, False)                       # 원본 작은 ｷﾞﾙ 왼끝 x81 = 테두리 · 윗 테두리 368, 아래 테두리 없음
    out = pack(o)
    assert len(out) == len(d)
    return out


def preview():
    from PIL import Image
    src = open(os.path.join(ROOT, 'work', 'jp_all', 'FONT.PXL'), 'rb').read()
    pal = {0: (24, 32, 96), 1: (255, 255, 255), 2: (220, 220, 220), 3: (185, 185, 185), 4: (150, 150, 150),
           5: (120, 120, 120), 6: (80, 80, 80), 7: (16, 16, 16)}
    tiles = []
    for d in (src, apply(src)):
        o = unpack(d)
        for (x0, y0, x1, y1) in ((60, 319, 140, 337), (60, 358, 140, 378)):
            c = o[y0:y1, x0:x1]
            im = Image.new('RGB', (c.shape[1], c.shape[0]))
            im.putdata([pal.get(int(v), (255, 0, 255)) for v in c.ravel()])
            tiles.append(im.resize((c.shape[1] * 6, c.shape[0] * 6), Image.NEAREST))
    W = max(t.width for t in tiles)
    canvas = Image.new('RGB', (W * 2 + 20, sum(t.height for t in tiles[:2]) + 10), (255, 255, 255))
    y = 0
    for i in range(2):
        canvas.paste(tiles[i], (0, y)); canvas.paste(tiles[i + 2], (W + 20, y)); y += tiles[i].height + 10
    dst = os.path.join(ROOT, 'my files', '그래픽', '길_비교.png')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    canvas.save(dst)
    print(dst)


if __name__ == '__main__':
    preview()
