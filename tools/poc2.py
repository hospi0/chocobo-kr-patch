# -*- coding: utf-8 -*-
r"""PoC 2 — 화자 이름 「アトラ」 → 「아트라」

이름은 본문과 «같은 코드»이고 서식 `04 04 … 04 00` 로 감싸여 있다(docs §7-2).
이름칸은 **8×8 작은 아틀라스**(y=256·줄당 32칸·같은 색인)를 쓰므로 **두 벌을 그려야** 한다.

  python tools/poc2.py [--install <F: 사본 .bin>]
"""
import argparse, os, struct, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import krfont, msg

JP = os.path.join(ROOT, 'work', 'jp')
OUT = os.path.join(ROOT, 'work', 'kr')
OLD = bytes([0xC0, 0xD3, 0xE6])          # アトラ
NEW_KO = '아트라'
# 색인 선택 — 본문 미사용 + 작은칸도 안 쓰는 자리 + 2바이트 코드의 아랫바이트가 0x10 이상
SLOTS = [270, 273, 274]


def enc(code):
    return bytes([code]) if code < 0x100 else bytes([code >> 8, code & 0xFF])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    table = dict(zip(NEW_KO, SLOTS))
    print('이름 글자 → 칸 %s (코드 %s)' % (table, {c: '%04X' % (i + 0x10) for c, i in table.items()}))

    src = os.path.join(OUT, 'FONT.PXL') if os.path.exists(os.path.join(OUT, 'FONT.PXL')) else os.path.join(JP, 'FONT.PXL')
    f = bytearray(open(src, 'rb').read())
    for ch, i in table.items():
        krfont.put(f, i, krfont.glyph12(ch))          # 12×12 큰 글꼴
        krfont.put_small(f, i, krfont.glyph8(ch))     # 8×8 이름칸 글꼴
    assert len(f) == 65536
    open(os.path.join(OUT, 'FONT.PXL'), 'wb').write(bytes(f))
    print('FONT.PXL  큰 글꼴 + 작은 글꼴 %d자씩 심음' % len(table))

    ko = b''.join(enc(table[c] + 0x10) for c in NEW_KO)
    src = os.path.join(OUT, 'MSG.BIN') if os.path.exists(os.path.join(OUT, 'MSG.BIN')) else os.path.join(JP, 'MSG.BIN')
    d = bytearray(open(src, 'rb').read())
    n = 0
    for bank in msg.banks(bytes(d)):
        base = bank * msg.BANK
        t = msg.table(bytes(d), bank)
        if not t:
            continue
        ss = msg.strings(bytes(d), bank)
        cur = max(o + len(s) for o, s in ss)
        cur = (cur + 3) & ~3
        for i, (off, s) in enumerate(ss):
            if OLD not in s:
                continue
            new = s.replace(OLD, ko)
            if len(new) <= len(s):
                d[base + off:base + off + len(new)] = new
            else:
                if cur + len(new) > msg.BANK:
                    raise SystemExit('⛔ 뱅크%d 자리 부족' % bank)
                if any(d[base + cur:base + cur + len(new)]):
                    raise SystemExit('⛔ 뱅크%d %04X 가 비어 있지 않다' % (bank, cur))
                d[base + cur:base + cur + len(new)] = new
                struct.pack_into('<H', d, base + i * 2, cur)
                cur = (cur + len(new) + 3) & ~3
            n += 1
    assert len(d) == 262144
    open(os.path.join(OUT, 'MSG.BIN'), 'wb').write(bytes(d))
    print('이름 문자열 %d개 교체' % n)

    if not a.install:
        print('\n(디스크는 안 건드렸다)')
        return
    for name in ('FONT.PXL', 'MSG.BIN'):
        subprocess.run([sys.executable, os.path.join(HERE, 'discfs.py'), a.install,
                        '--put', '/' + name, os.path.join(OUT, name)], check=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
