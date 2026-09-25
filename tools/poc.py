# -*- coding: utf-8 -*-
r"""PoC — 여관 NPC 대사 한 줄을 한글로 (FONT.PXL 빈 칸 + MSG.BIN 문자열 재배치)

  python tools/poc.py                 # work/kr/ 에 만들기만
  python tools/poc.py --install <F: 사본 .bin>

## 무엇을 하나
1. 본문이 «안 쓰는 칸»을 골라 한글 글리프를 심는다 (FONT.PXL, 크기 불변)
2. MSG.BIN 뱅크1 의 그 문자열을 한글 코드로 다시 쓰고, 길어지면 **뱅크 뒤 빈 공간으로 옮긴 뒤
   오프셋표만 고친다** (뱅크 32 KB 중 본문은 11 KB 뿐이라 21 KB 가 남는다)
"""
import argparse, os, struct, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import discfs, krfont, msg

JP = os.path.join(ROOT, 'work', 'jp')
OUT = os.path.join(ROOT, 'work', 'kr')
TEXT = [('저기요', '\x3b\x21'), ('묵고 싶은데요', '\x3b')]     # 줄마다 (한글, 뒤에 붙일 원래 코드)


def used_indices():
    u = set()
    d = open(os.path.join(JP, 'MSG.BIN'), 'rb').read()
    for b in msg.banks(d):
        for off, s in msg.strings(d, b):
            u |= {v - 0x10 for k, v in msg.tokens(s) if k == 'c'}
    e = open(os.path.join(JP, 'SLPS_012.34'), 'rb').read()
    base = 0x06C9F0
    for i in range(struct.unpack_from('<H', e, base)[0] // 2):
        o = struct.unpack_from('<H', e, base + i * 2)[0]
        u |= {v - 0x10 for k, v in msg.tokens(e[base + o:e.index(b'\x00', base + o) + 1]) if k == 'c'}
    return u


def enc(code):
    return bytes([code]) if code < 0x100 else bytes([code >> 8, code & 0xFF])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    # 1) 쓸 칸 고르기 — 본문이 안 쓰는 칸 중 «그림도 비어 있는» 것부터
    used = used_indices()
    planes = msg.atlas()
    free = [i for i in range(882) if i not in used]
    free.sort(key=lambda i: (msg.glyph(planes, i).sum() > 0, i))
    need = sorted({ch for t, _ in TEXT for ch in t if ch != ' '})
    table = {ch: free[k] for k, ch in enumerate(need)}
    print('한글 %d자 → 칸 %s' % (len(need), {c: i for c, i in table.items()}))

    # 2) 글꼴 심기
    f = bytearray(open(os.path.join(JP, 'FONT.PXL'), 'rb').read())
    for ch, i in table.items():
        krfont.put(f, i, krfont.glyph12(ch))
    assert len(f) == 65536
    open(os.path.join(OUT, 'FONT.PXL'), 'wb').write(bytes(f))
    print('FONT.PXL  글리프 %d개 심음 (크기 %d B)' % (len(table), len(f)))

    # 3) 본문 바꾸기 — 뱅크1 의 「すいませーん！…」
    d = bytearray(open(os.path.join(JP, 'MSG.BIN'), 'rb').read())
    bank = 1
    base = bank * msg.BANK
    old = bytes([0x1c, 0x11, 0x8e, 0x1d, 0x3b, 0x9d, 0x21])
    t = msg.table(bytes(d), bank)
    hit = [i for i, o in enumerate(t) if bytes(d[base + o:base + o + len(old)]) == old]
    if not hit:
        raise SystemExit('⛔ 대상 문자열을 못 찾았다')
    idx = hit[0]
    print('대상 = 뱅크%d 표 %d번 (오프셋 %04X)' % (bank, idx, t[idx]))

    new = bytearray()
    for k, (ko, tail) in enumerate(TEXT):
        if k:
            new.append(0x0A)
        for ch in ko:
            new += b'\x0f' if ch == ' ' else enc(table[ch] + 0x10)
        new += tail.encode('latin1')
    new.append(0x00)

    end = max(o + (d.index(b'\x00', base + o) + 1 - base - o) for o in t)   # 본문 끝
    put = (end + 3) & ~3
    if put + len(new) > msg.BANK:
        raise SystemExit('⛔ 뱅크에 자리가 없다')
    if any(d[base + put:base + put + len(new)]):
        raise SystemExit('⛔ 옮길 자리가 비어 있지 않다')
    d[base + put:base + put + len(new)] = new
    struct.pack_into('<H', d, base + idx * 2, put)
    print('새 문자열 %d B → 뱅크 안 %04X 에 두고 표 갱신 (원래 %04X, 뒤 빈 공간 %d B)'
          % (len(new), put, t[idx], msg.BANK - end))
    assert len(d) == 262144
    open(os.path.join(OUT, 'MSG.BIN'), 'wb').write(bytes(d))

    if not a.install:
        print('\n(디스크는 안 건드렸다 — --install 은 허락 후에)')
        return
    for name in ('FONT.PXL', 'MSG.BIN'):
        cmd = [sys.executable, os.path.join(HERE, 'discfs.py'), a.install,
               '--put', '/' + name, os.path.join(OUT, name)]
        subprocess.run(cmd, check=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
