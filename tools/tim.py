# -*- coding: utf-8 -*-
r"""TIM 읽기·쓰기와 «.TD 묶음» 풀기

  python tools/tim.py work/jp/MIS.TD --out work/tim/MIS      # 그림 전부 PNG 로
  python tools/tim.py work/jp/MIS.TD                          # 목록만

## .TD 묶음 (실측)
```
+0  u32 n           그림 수
+4  u32 off[n]      각 TIM 의 파일 오프셋
…   TIM …           압축 없음(0x00000010 로 시작)
```
## TIM
```
+0  u32 0x10
+4  u32 flags       하위 3비트 = 0:4bpp 1:8bpp 2:16bpp 3:24bpp · 비트3 = CLUT 있음
[CLUT]  u32 크기(헤더 12 포함) · u16 x,y,w,h · u16 색 w*h
[화소]  u32 크기(헤더 12 포함) · u16 x,y,w,h  ← w 는 «16비트 낱말» 단위
```
"""
import argparse, os, struct, sys


def parse(d, p=0):
    """(bpp, clut, (x,y,w,h), 화소바이트, 다음오프셋)"""
    magic, flags = struct.unpack_from('<2I', d, p)
    if magic != 0x10:
        raise ValueError('TIM 이 아니다 @%X (%08X)' % (p, magic))
    bpp = (0, 1, 2, 3)[flags & 3]
    q = p + 8
    clut = None
    if flags & 8:
        sz, cx, cy, cw, ch = struct.unpack_from('<I4H', d, q)
        clut = (cx, cy, cw, ch, d[q + 12:q + sz])
        q += sz
    sz, ix, iy, iw, ih = struct.unpack_from('<I4H', d, q)
    px = d[q + 12:q + sz]
    return bpp, clut, (ix, iy, iw, ih), px, q + sz


def pixels(bpp, rect, px):
    """(가로, 세로, [색인…]) — 4bpp 는 낮은 니블이 왼쪽"""
    ix, iy, iw, ih = rect
    stride = iw * 2
    w = iw * (4 if bpp == 0 else 2 if bpp == 1 else 1)
    out = []
    for y in range(ih):
        row = px[y * stride:(y + 1) * stride]
        if bpp == 0:
            r = []
            for b in row:
                r += [b & 0xF, b >> 4]
        elif bpp == 1:
            r = list(row)
        else:
            r = [struct.unpack_from('<H', row, 2 * x)[0] for x in range(iw)]
        out.append(r[:w])
    return w, ih, out


def rgb(c):
    return ((c & 0x1F) << 3, ((c >> 5) & 0x1F) << 3, ((c >> 10) & 0x1F) << 3)


def to_png(bpp, clut, rect, px, path, pal=0):
    from PIL import Image
    w, h, rows = pixels(bpp, rect, px)
    im = Image.new('RGB', (w, h))
    q = im.load()
    if bpp in (0, 1) and clut:
        cw = clut[2]
        base = pal * cw * 2
        cols = [rgb(struct.unpack_from('<H', clut[4], base + 2 * i)[0])
                for i in range(cw)]
    else:
        cols = None
    for y in range(h):
        for x in range(w):
            v = rows[y][x]
            q[x, y] = cols[v % len(cols)] if cols else rgb(v)
    im.save(path)
    return w, h


def td(d):
    """[(오프셋, 길이)] — .TD 묶음의 TIM 목록"""
    n = struct.unpack_from('<I', d, 0)[0]
    if not (1 <= n <= 4096):
        raise ValueError('TD 묶음이 아니다 (n=%d)' % n)
    offs = list(struct.unpack_from('<%dI' % n, d, 4))
    return [(o, (offs[i + 1] if i + 1 < n else len(d)) - o) for i, o in enumerate(offs)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--out')
    ap.add_argument('--pal', type=int, default=0)
    a = ap.parse_args()
    d = open(a.path, 'rb').read()
    items = td(d) if struct.unpack_from('<I', d, 0)[0] != 0x10 else [(0, len(d))]
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    for i, (o, ln) in enumerate(items):
        try:
            bpp, clut, rect, px, nxt = parse(d, o)
        except ValueError as e:
            print('%2d  %08X  %s' % (i, o, e))
            continue
        w = rect[2] * (4 if bpp == 0 else 2 if bpp == 1 else 1)
        print('%2d  %08X  %2dbpp  VRAM(%d,%d) %dx%d  CLUT %s'
              % (i, o, (4, 8, 16, 24)[bpp], rect[0], rect[1], w, rect[3],
                 '%dx%d@(%d,%d)' % (clut[2], clut[3], clut[0], clut[1]) if clut else '없음'))
        if a.out:
            to_png(bpp, clut, rect, px, os.path.join(a.out, '%02d.png' % i), a.pal)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
