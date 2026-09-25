# -*- coding: utf-8 -*-
r"""MSG.BIN — 32 KB 뱅크 8개, 뱅크마다 «u16 오프셋표 + 문자열»

구조 (실측)
```
뱅크 b 시작 = b * 0x8000
  +0   u16 off[0]        ← 이 값이 곧 표 크기(바이트). 항목 수 = off[0]/2
  …    u16 off[n]        각 문자열의 «뱅크 안» 오프셋
  …    문자열들 (0x00 으로 끝)
```
인코딩 (실측·검증)
```
0x00        문자열 끝
0x01‥0x03   한자 페이지 «앞바이트» — 다음 바이트와 합쳐 16비트 코드
0x04 XX     서식(색?)
0x0A        개행
0x0C        문단/메시지 끝
0x0F        공백
0x10‥0xFF   글리프
글리프 색인 = (코드 − 0x10)   ※코드는 1바이트 또는 2바이트 빅엔디언
아틀라스   FONT.PXL · 12×12 · 21칸/줄 · 한 «면»에 21줄(441칸)
★★★★★색인 441 미만은 «아래 2비트 면», 441 이상은 «위 2비트 면»이다:
    i = 코드 − 0x10
    면 = lo if i < 441 else hi ;  j = i if i < 441 else i − 441
    행,열 = divmod(j, 21) ;  좌표 = (열×12, 행×12)
  (면마다 첫 VRAM 페이지 y0‥251 만 글꼴이다. 아래 면의 y256+ 는 작은 글꼴·아이콘이라 코드 공간 밖)
  검증: MSG.BIN 뱅크0 0563 = 「でも、機械が動いたから許してくれよな」,
        뱅크1 = 「すいませーん！/泊まりたいんですけどー」(실기 스샷 일치)
```
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BANK = 0x8000
CAP = 21 * 21          # 한 면이 담는 글리프 수
CTRL = {0x00: 'END', 0x0A: 'NL', 0x0C: 'EOM', 0x0F: 'SP'}
# ★인자 1바이트를 먹는 코드 — 01‥03 한자 앞바이트 · 04 서식 · 06 대기(프레임) · 07 끼움(숫자/문자열) · 08 ?
# ⛔`07 00` 의 00 은 «인자»다. 이걸 끝으로 보면 「この{7}」처럼 뒤(「つでいいかい？」)가 잘린다(2026-09-21).
ARG1 = {0x01, 0x02, 0x03, 0x04, 0x06, 0x07, 0x08}


def banks(d):
    return [b for b in range(len(d) // BANK)]


def table(d, b):
    o = b * BANK
    n = struct.unpack_from('<H', d, o)[0]
    if n == 0 or n % 2 or n > BANK:
        return []
    return [struct.unpack_from('<H', d, o + i * 2)[0] for i in range(n // 2)]


def scan_end(d, p):
    """문자열 끝(0x00 다음 자리) — ⛔서식·한자 «인자»의 00 을 종료자로 착각하면 안 된다

    `04 00`(서식 되돌리기)의 00 은 인자다. 0x00 은 «토큰 경계»에 있을 때만 끝이다.
    이걸 틀리면 「セーブ」처럼 문자열이 중간에서 잘리고, 중복 판정도 엉망이 된다(2026-09-21).
    """
    while p < len(d):
        c = d[p]
        if c == 0x00:
            return p + 1
        p += 2 if c in ARG1 else 1
    return len(d)


def strings(d, b):
    """→ [(뱅크안오프셋, 바이트열)]"""
    o = b * BANK
    t = table(d, b)
    out = []
    for off in t:
        out.append((off, d[o + off:scan_end(d, o + off)]))
    return out


def tokens(s):
    """바이트열 → [('c', 코드) | ('t', 태그) | ('f', (04,XX))]"""
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c in CTRL:
            out.append(('t', CTRL[c])); i += 1
        elif c == 0x04:
            out.append(('f', s[i + 1] if i + 1 < len(s) else 0)); i += 2
        elif 0x01 <= c <= 0x03:
            out.append(('c', (c << 8) | s[i + 1])); i += 2
        elif c in ARG1:
            out.append(('a', (c, s[i + 1] if i + 1 < len(s) else 0))); i += 2
        else:
            out.append(('c', c)); i += 1
    return out


def ascii_text(s):
    """영문판용 — 코드가 곧 ASCII"""
    r = []
    for k, v in tokens(s):
        if k == 't':
            r.append({'END': '', 'NL': '\n', 'EOM': '¶', 'SP': ' '}[v])
        elif k == 'f':
            r.append('<%02X>' % v)
        elif k == 'a':
            r.append('{%X:%02X}' % v)
        else:
            r.append(chr(v) if 0x20 <= v <= 0x7E else '{%X}' % v)
    return ''.join(r)


def main():
    d = open(sys.argv[1], 'rb').read()
    tot = 0
    for b in banks(d):
        t = table(d, b)
        if not t:
            print('뱅크 %d  (표 없음)' % b); continue
        ss = strings(d, b)
        tot += len(ss)
        print('뱅크 %d  문자열 %4d개 · 표 %d B · 본문 끝 %04X' % (b, len(ss), t[0], max(o + len(s) for o, s in ss)))
        if len(sys.argv) > 2:
            for i, (o, s) in enumerate(ss[:int(sys.argv[2])]):
                print('   %3d %04X  %s' % (i, o, ascii_text(s).replace('\n', ' ⏎ ')))
    print('합계 %d 문자열' % tot)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()


# ── 글리프 아틀라스 ────────────────────────────────────────────────────────
def atlas(path=None):
    """FONT.PXL → (lo, hi) 두 면 (각각 512×256, 값 0‥3)"""
    import numpy as np
    d = np.frombuffer(open(path or os.path.join(ROOT, 'work', 'jp', 'FONT.PXL'), 'rb').read(), np.uint8)
    rows = len(d) // 128
    b = d[:rows * 128].reshape(rows, 128)
    v = np.empty((rows, 256), np.uint8)
    v[:, 0::2] = b & 15
    v[:, 1::2] = b >> 4
    return v & 3, (v >> 2) & 3


def where(i):
    """글리프 색인 → (면 0/1, x, y)"""
    p = 0 if i < CAP else 1
    r, c = divmod(i if i < CAP else i - CAP, 21)
    return p, c * 12, r * 12


def glyph(planes, i):
    p, x, y = where(i)
    return planes[p][y:y + 12, x:x + 12]
