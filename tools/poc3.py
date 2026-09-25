# -*- coding: utf-8 -*-
r"""PoC 3 — 원본에서 «한 번에» 다시 만든다 (대사 + 화자 이름)

⛔PoC2 의 실패에서 배운 것
1. 이름은 MSG.BIN 뿐 아니라 **SLPS_012.34 안에도 같은 문자열**이 있고, 화면엔 그쪽이 쓰인다.
2. 이름칸은 **8×8 작은 아틀라스**인데 색인 256‥287 줄(y320)은 **HUD 숫자 글꼴과 겹친다**
   → 그 줄에 한글을 심으면 「Lv. 1 HP 30/30」이 깨진다. 작은 글꼴은 **색인<240** 에만 심는다.
3. 그래서 이름 글자는 **1바이트 코드(색인<240)** 로 넣는다. 길이가 같아 SLPS 도 «제자리» 교체가 된다.
"""
import argparse, os, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import krfont, msg

JP = os.path.join(ROOT, 'work', 'jp')
OUT = os.path.join(ROOT, 'work', 'kr')
DIALOG = [('저기요', b'\x3b\x21'), ('묵고 싶은데요', b'\x3b')]
BODY_SLOTS = list(range(869, 877))            # 본문 전용(2바이트) — 큰 글꼴만
NAME = '아트라'
NAME_SLOTS = [16, 20, 24]                     # 1바이트 코드 · 큰+작은 글꼴 둘 다
OLD_NAME = bytes([0xC0, 0xD3, 0xE6])


def enc(code):
    return bytes([code]) if code < 0x100 else bytes([code >> 8, code & 0xFF])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--install'); a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    body = sorted({c for t, _ in DIALOG for c in t if c != ' '})
    tb = dict(zip(body, BODY_SLOTS))
    tn = dict(zip(NAME, NAME_SLOTS))
    print('본문 한글 %s' % {c: i for c, i in tb.items()})
    print('이름 한글 %s → 코드 %s' % ({c: i for c, i in tn.items()},
                                     {c: '%02X' % (i + 0x10) for c, i in tn.items()}))

    f = bytearray(open(os.path.join(JP, 'FONT.PXL'), 'rb').read())
    for ch, i in tb.items():
        krfont.put(f, i, krfont.glyph12(ch))
    for ch, i in tn.items():
        krfont.put(f, i, krfont.glyph12(ch))
        krfont.put_small(f, i, krfont.glyph8(ch))
    assert len(f) == 65536
    open(os.path.join(OUT, 'FONT.PXL'), 'wb').write(bytes(f))
    print('FONT.PXL  큰 %d자 · 작은 %d자' % (len(tb) + len(tn), len(tn)))

    ko_name = b''.join(enc(tn[c] + 0x10) for c in NAME)
    assert len(ko_name) == len(OLD_NAME), '이름은 길이가 같아야 제자리 교체가 된다'

    # MSG.BIN — 대사 교체(자리 옮김) + 이름 제자리 교체
    d = bytearray(open(os.path.join(JP, 'MSG.BIN'), 'rb').read())
    d = bytearray(bytes(d).replace(OLD_NAME, ko_name))
    bank, base = 1, msg.BANK
    old = bytes([0x1c, 0x11, 0x8e, 0x1d, 0x3b, 0x9d, 0x21])
    t = msg.table(bytes(d), bank)
    idx = [i for i, o in enumerate(t) if bytes(d[base + o:base + o + len(old)]) == old][0]
    new = bytearray()
    for k, (ko, tail) in enumerate(DIALOG):
        if k:
            new.append(0x0A)
        for ch in ko:
            new += b'\x0f' if ch == ' ' else enc(tb[ch] + 0x10)
        new += tail
    new.append(0x00)
    ss = msg.strings(bytes(d), bank)
    cur = (max(o + len(s) for o, s in ss) + 3) & ~3
    if any(d[base + cur:base + cur + len(new)]):
        raise SystemExit('⛔ 옮길 자리가 비어 있지 않다')
    d[base + cur:base + cur + len(new)] = new
    struct.pack_into('<H', d, base + idx * 2, cur)
    assert len(d) == 262144
    open(os.path.join(OUT, 'MSG.BIN'), 'wb').write(bytes(d))
    print('MSG.BIN   대사 1줄(뱅크1 표%d → %04X) · 이름 %d곳' % (idx, cur, bytes(d).count(ko_name)))

    # SLPS — 이름 제자리 교체
    e = bytearray(open(os.path.join(JP, 'SLPS_012.34'), 'rb').read())
    n = bytes(e).count(OLD_NAME)
    e = bytearray(bytes(e).replace(OLD_NAME, ko_name))
    assert len(e) == 512000
    open(os.path.join(OUT, 'SLPS_012.34'), 'wb').write(bytes(e))
    print('SLPS      이름 %d곳 제자리 교체' % n)

    if not a.install:
        print('\n(디스크는 안 건드렸다)')
        return
    for name in ('FONT.PXL', 'MSG.BIN', 'SLPS_012.34'):
        subprocess.run([sys.executable, os.path.join(HERE, 'discfs.py'), a.install,
                        '--put', '/' + name, os.path.join(OUT, name)], check=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
