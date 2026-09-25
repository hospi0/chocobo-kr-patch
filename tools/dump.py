# -*- coding: utf-8 -*-
r"""본문 전량 추출 → TSV (번역용)

  python tools/dump.py            # work/kr/msg.tsv · slps.tsv

## 열
```
id       MSG:뱅크:표번호  또는  SLPS:표번호
off      파일 안 오프셋(16진)
dup      같은 원문이 여러 곳에 있으면 «대표 id» (번역은 한 번만 쓰면 된다)
jp       원문 바이트(16진) — 되돌릴 때 이걸 기준으로 검사한다
en       영문판 본문(ASCII·제어 토큰) ← **번역 원본**
kr       (빈칸) 번역을 여기에
```
⛔영문판 문자열은 «같은 자리»의 것을 짝지어 온다. 표 길이가 다르면 빈칸으로 둔다.
"""
import io, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msg

JP = os.path.join(ROOT, 'work', 'jp')
EN = os.path.join(ROOT, 'work', 'en')
OUT = os.path.join(ROOT, 'work', 'kr')
SLPS_TBL = 0x06C9F0
# ★SLPS 안의 표는 이것 말고도 8개 더 있다(2026-09-21 — 영문 패치가 바꾼 구간으로 찾음).
# 표마다 «u16 오프셋표(첫 값 = 표 크기) + 문자열», 오프셋은 표 시작 기준. 표끼리는 빈틈 없이 붙어 있다.
SLPS_TABLES = [(0x06C9F0, 'SLPS'), (0x06D228, 'CARD'), (0x06D678, 'ITEM'), (0x06DF60, 'MON'),
               (0x06E30C, 'SKILL'), (0x06E7DC, 'DESC'), (0x06F964, 'ATTR'), (0x06FED8, 'ATTR2'),
               (0x070238, 'STAT')]
TAB = chr(9)


def slps_strings(d, base=SLPS_TBL):
    n = struct.unpack_from('<H', d, base)[0] // 2
    out = []
    for i in range(n):
        o = struct.unpack_from('<H', d, base + i * 2)[0]
        out.append((o, d[base + o:msg.scan_end(d, base + o)]))   # ⛔첫 00 아님 — `07 00` 의 00 은 인자
    return out


def rows():
    jm = open(os.path.join(JP, 'MSG.BIN'), 'rb').read()
    em = open(os.path.join(EN, 'MSG.BIN'), 'rb').read()
    out = []
    for b in msg.banks(jm):
        js = msg.strings(jm, b)
        es = msg.strings(em, b)
        for i, (off, s) in enumerate(js):
            en = msg.ascii_text(es[i][1]) if i < len(es) else ''
            out.append(('MSG:%d:%d' % (b, i), b * msg.BANK + off, s, en))
    js = open(os.path.join(JP, 'SLPS_012.34'), 'rb').read()
    es = open(os.path.join(EN, 'SLPS_012.34'), 'rb').read()
    for base, name in SLPS_TABLES:
        ss, se = slps_strings(js, base), slps_strings(es, base)
        for i, (off, s) in enumerate(ss):
            en = msg.ascii_text(se[i][1]) if i < len(se) else ''
            out.append(('%s:%d' % (name, i), base + off, s, en))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    rs = rows()
    first = {}
    n_msg = n_slps = 0
    lines = ['id\toff\tdup\tjp\ten\tkr']
    for rid, off, s, en in rs:
        key = bytes(s)
        dup = first.get(key, '')
        if not dup:
            first[key] = rid
        lines.append(TAB.join([rid, '%06X' % off, dup, s.hex(),
                               en.replace(TAB, ' ').replace('\n', chr(92) + 'n'), '']))
        if rid.startswith('MSG'):
            n_msg += 1
        else:
            n_slps += 1
    p = os.path.join(OUT, 'text.tsv')
    data = (chr(10).join(lines) + chr(10)).encode('utf-8')
    with open(p, 'wb') as f:
        f.write(data)
    uniq = len(first)
    print('MSG %d줄 + SLPS %d줄 = %d줄 · 서로 다른 원문 %d줄 (중복 %d줄)'
          % (n_msg, n_slps, len(rs), uniq, len(rs) - uniq))
    print('→', p, '%d B' % len(data))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
