# -*- coding: utf-8 -*-
r"""FBDAP.BIN 안 데미지 숫자 판의 «ミス»(공격 빗나감) 그림 → «미스» (빌더가 부른다).

  python tools/missgfx.py        → my files/그래픽/미스_비교.png (원본 / 한글 확대 비교)

판 = 4bpp 256px 폭(한 줄 128 B), VRAM (256,481) 에 올라간다(세이브스테이트 «미스.sav» 로 찾음, 2026-09-26).
  «0123456789ミス» 한 줄 · 칸 8×11 · 값 1 = 테두리, 2‥5 = 채움(5 가 밝다).
  ミ = x80‥87, ス = x88‥95, 줄 481‥491 (채움 482‥490 · 테두리 481·491).
★같은 판이 파일 안에 세 벌(줄 481 머리 749696 · 751744 · 794752) — 셋 다 바꾼다.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'work', 'jp_all', 'FBDAP.BIN')
COPIES = (749696, 751744, 794752)       # 판의 줄 481 머리(x0)
ROW, H = 128, 11
X0, X1 = 80, 96                         # ミス 두 칸(끝 제외)
OUTLINE = 1

# 채움 6×9 손그림 (칸 8 폭 = 테두리 1 + 채움 6 + 테두리 1)
MI = ['####.#',
      '#..#.#',
      '#..#.#',
      '#..#.#',
      '#..#.#',
      '####.#',
      '.....#',
      '.....#',
      '.....#']
SEU = ['..##..',
       '..##..',
       '.#..#.',
       '.#..#.',
       '#....#',
       '......',
       '######',
       '......',
       '......']
SIG = bytes.fromhex('412552140051140051244215512442150041550121252212105413013133431531155113413553155155341255555512')   # 줄 483 x0‥95


def block(d, base):
    a = np.frombuffer(bytes(d[base:base + ROW * H]), np.uint8).reshape(H, ROW)
    return np.stack([a & 15, a >> 4], 2).reshape(H, ROW * 2).copy()


def apply(d):
    d = bytearray(d)
    for base in COPIES:
        assert bytes(d[base + 2 * ROW:base + 2 * ROW + len(SIG)]) == SIG, ('미스 판 원문 불일치', base)
        o = block(d, base)
        o[:, X0:X1] = 0
        for cx, g in ((X0, MI), (X0 + 8, SEU)):
            m = np.array([[c == '#' for c in r] for r in g])
            ring = np.zeros((H, 8), bool)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ring[1 + dy:1 + dy + 9, 1 + dx:1 + dx + 6] |= m
            for y in range(H):
                for x in range(8):
                    inside = 1 <= y <= 9 and 1 <= x <= 6 and m[y - 1, x - 1]
                    if inside:
                        top = y == 1 or not m[y - 2, x - 1]
                        bot = y == 9 or not m[y, x - 1]
                        o[y, cx + x] = 4 if (top or bot) else 5     # 획 끝은 한 단 어둡게(숫자 «1441/1541» 꼴)
                    elif ring[y, x]:
                        o[y, cx + x] = OUTLINE
        packed = (o[:, 0::2] | (o[:, 1::2] << 4)).astype(np.uint8).tobytes()
        d[base:base + ROW * H] = packed
    return bytes(d)


def preview():
    from PIL import Image
    src = open(SRC, 'rb').read()
    pal = {0: (40, 48, 60), 1: (16, 16, 16), 2: (110, 110, 110), 3: (160, 160, 160), 4: (210, 210, 210), 5: (255, 255, 255)}
    tiles = []
    for d in (src, apply(src)):
        c = block(d, COPIES[0])[:, 0:104]
        im = Image.new('RGB', (c.shape[1], c.shape[0]))
        im.putdata([pal.get(int(v), (255, 0, 255)) for v in c.ravel()])
        tiles.append(im.resize((c.shape[1] * 8, c.shape[0] * 8), Image.NEAREST))
    canvas = Image.new('RGB', (tiles[0].width, tiles[0].height * 2 + 16), (255, 255, 255))
    canvas.paste(tiles[0], (0, 0)); canvas.paste(tiles[1], (0, tiles[0].height + 16))
    dst = os.path.join(ROOT, 'my files', '그래픽', '미스_비교.png')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    canvas.save(dst)
    print(dst)


if __name__ == '__main__':
    preview()
