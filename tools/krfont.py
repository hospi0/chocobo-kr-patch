# -*- coding: utf-8 -*-
r"""한글 글리프를 FONT.PXL 의 «빈 칸»에 심는다

  python tools/krfont.py --preview 저기요묵고싶은데

## 칸 구조 (docs/01_초기조사.md §5-1, §6-1)
```
FONT.PXL = 4bpp 텍스처 256×512. 니블의 «아래 2비트»가 면0, «위 2비트»가 면1.
색인 i → 면 = 0 if i<441 else 1 · j = i or i−441 · 행,열 = divmod(j,21) · (열×12, 행×12)
값 0=투명 1=흰(획) 2=중간 3=어두움(그림자)
```
⛔한 니블에 두 면이 들어 있으므로 **반드시 읽고-고쳐-쓰기**로 한쪽 면만 바꾼다.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bdf
import msg

FONTDIR = os.path.join('C:' + os.sep, 'claude', 'utils', 'font', 'Galmuri-v2.40.3')
BDF = os.path.join(FONTDIR, 'Galmuri11.bdf')
BDF7 = os.path.join(FONTDIR, 'Galmuri7.bdf')      # 이름칸(8×8 작은 아틀라스)용
INK, MID, DARK = 1, 2, 3
_F = None


def font():
    global _F
    if _F is None:
        _F = bdf.Font(BDF)
    return _F


def glyph12(ch, shadow=True):
    """한 글자 → 12×12 값 배열 (원문과 같은 «흰 획 + 오른아래 어두운 그림자»)"""
    pts, w = font().draw(ch)
    if not pts:
        raise KeyError(ch)
    ox = min(x for x, _ in pts)
    oy = min(y for _, y in pts)
    ink = {(x - ox, y - oy) for x, y in pts}
    gw = max(x for x, _ in ink) + 1
    gh = max(y for _, y in ink) + 1
    if gw > 11 or gh > 11:
        raise SystemExit('⛔ %r 글리프가 11×11 을 넘는다 (%d×%d)' % (ch, gw, gh))
    sx = (12 - gw - 1) // 2
    sy = (12 - gh - 1) // 2
    g = np.zeros((12, 12), np.uint8)
    if shadow:
        for x, y in ink:
            q = (sx + x + 1, sy + y + 1)
            if (q[0] - sx, q[1] - sy) not in ink and q[0] < 12 and q[1] < 12:
                g[q[1], q[0]] = DARK
    for x, y in ink:
        g[sy + y, sx + x] = INK
    return g


def glyph8(ch):
    """한 글자 → 8×8 값 배열 (이름칸용 작은 글꼴 · 갈무리7)

    ★작은 아틀라스는 «칸 8×8 · 줄당 32칸 · y=256 부터»이고 색인은 큰 글꼴과 같다.
      7×7 이라 그림자는 넣지 않는다(넣으면 획이 메워진다).
    """
    global _F7
    try:
        _F7
    except NameError:
        _F7 = None
    if _F7 is None:
        _F7 = bdf.Font(BDF7)
    pts, w = _F7.draw(ch)
    if not pts:
        raise KeyError(ch)
    ox = min(x for x, _ in pts)
    oy = min(y for _, y in pts)
    ink = [(x - ox, y - oy) for x, y in pts]
    gw = max(x for x, _ in ink) + 1
    gh = max(y for _, y in ink) + 1
    if gw > 8 or gh > 8:
        raise SystemExit('⛔ %r 가 8×8 을 넘는다 (%d×%d)' % (ch, gw, gh))
    g = np.zeros((8, 8), np.uint8)
    sx, sy = (8 - gw) // 2, (8 - gh) // 2
    for x, y in ink:
        g[sy + y, sx + x] = INK
    return g


def put_small(d, i, g):
    """작은 아틀라스(8×8)에 심는다 — 아래 2비트 면"""
    r, c = divmod(i, 32)
    y0, x0 = 256 + r * 8, c * 8
    for rr in range(8):
        for cc in range(8):
            row, col = y0 + rr, x0 + cc
            off = row * 128 + col // 2
            hi = (col % 2) == 1
            b = d[off]
            nib = (b >> 4) if hi else (b & 15)
            nib = (nib & 0xC) | (int(g[rr, cc]) & 3)
            d[off] = ((b & 0x0F) | (nib << 4)) if hi else ((b & 0xF0) | nib)


def put(d, i, g):
    """FONT.PXL 바이트열(bytearray) 의 색인 i 칸에 12×12 값 배열을 심는다"""
    p, x, y = msg.where(i)
    shift = 0 if p == 0 else 2
    for r in range(12):
        row = y + r
        for c in range(12):
            col = x + c
            off = row * 128 + col // 2
            nib_hi = (col % 2) == 1
            b = d[off]
            nib = (b >> 4) if nib_hi else (b & 15)
            nib = (nib & ~(3 << shift) & 0xF) | ((int(g[r, c]) & 3) << shift)
            d[off] = ((b & 0x0F) | (nib << 4)) if nib_hi else ((b & 0xF0) | nib)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview', default='저기요묵고싶은데')
    a = ap.parse_args()
    from PIL import Image
    n = len(a.preview)
    img = np.zeros((13, n * 13), np.uint8)
    for k, ch in enumerate(a.preview):
        img[0:12, k * 13:k * 13 + 12] = glyph12(ch)
    p = os.path.join(ROOT, 'work', 'shot', 'kr_preview.png')
    Image.fromarray((img * 85).astype(np.uint8)).resize((img.shape[1] * 6, 13 * 6), Image.NEAREST).save(p)
    print('→', p)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
