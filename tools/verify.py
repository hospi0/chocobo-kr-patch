# -*- coding: utf-8 -*-
r"""빌드 결과 되읽기 검사 — 새 MSG.BIN·SLPS 를 표대로 다시 풀어 번역문과 전 줄 대조

  python tools/verify.py

- 표의 모든 항목이 파일 안을 가리키고, 풀어낸 글이 `build.layout()` 결과(번역 안 한 줄은 원문 바이트)와 같은지
- ★코드표로 풀어 «글자»끼리 비교한다(바이트 비교는 인코더 자기 검사라 뜻이 없다) — 코드 충돌·중복 배정도 여기서 걸린다
"""
import csv, io, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msg, dump, build

OUT = os.path.join(ROOT, 'work', 'kr')


def decoder():
    inv = {}
    for ln in io.open(os.path.join(OUT, 'codemap.tsv'), encoding='utf-8'):
        c, i, _ = ln.rstrip('\n').split('\t')
        i = int(i)
        if i in inv:
            raise SystemExit('⛔ 색인 %d 에 두 글자(%s·%s)' % (i, inv[i], c))
        inv[i] = c
    for c, v in build.ASCII.items():
        if c != '―':
            inv[v - 0x10] = c
    for c, i in build.SYM2.items():
        inv[i] = c
    inv[build.SPACE_W - 0x10] = ' '          # 대사 공백(빈 글리프 0x10)
    return inv


def text(s, inv):
    r = []
    for k, v in msg.tokens(s):
        if k == 't':
            r.append({'END': '', 'NL': '\\n', 'EOM': '¶', 'SP': ' '}[v])
        elif k == 'f':
            r.append('<%02X>' % v)
        elif k == 'a':
            r.append('{%X:%02X}' % v)
        elif v < 0x10:
            r.append('{%X}' % v)
        else:
            r.append(inv.get(v - 0x10, '〔%d〕' % (v - 0x10)))
    return ''.join(r)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    inv = decoder()
    rs = build.rows()
    by = {r[0]: r for r in rs}
    bad = 0
    m = open(os.path.join(OUT, 'MSG.BIN'), 'rb').read()
    n = 0
    for b in msg.banks(m):
        for i, (off, s) in enumerate(msg.strings(m, b)):
            r = by['MSG:%d:%d' % (b, i)]
            kr = r[5]
            if not kr:
                continue
            want = build.layout(r[0], kr, r[3]).replace('\n', '\\n')
            got = text(s, inv)
            n += 1
            if got != want:
                bad += 1
                if bad <= 20:
                    print('✗ %s\n   원 %s\n   풀 %s' % (r[0], want, got))
    e = open(os.path.join(OUT, 'SLPS_012.34'), 'rb').read()
    j = open(os.path.join(ROOT, 'work', 'jp', 'SLPS_012.34'), 'rb').read()
    tabs = dump.SLPS_TABLES + [(0x070625, None)]
    for (base, name), (nb, _) in zip(tabs[:-1], tabs[1:]):
        k = 0
        for off, s in dump.slps_strings(e, base):
            rid = '%s:%d' % (name, k); k += 1
            r = by[rid]
            kr = by[r[2]][5] if r[2] else r[5]
            got = text(s, inv)
            if rid == 'SLPS:7' or not kr:
                continue
            want = build.layout(rid, kr, r[3]).replace('\n', '\\n')
            if name == 'STAT':
                got = got.lstrip(' ')
            n += 1
            if got != want:
                bad += 1
                if bad <= 40:
                    print('✗ %s\n   원 %s\n   풀 %s' % (rid, want, got))
    # 번역 안 한 SLPS 항목은 원문 바이트 그대로인가
    for (base, name), (nb, _) in zip(tabs[:-1], tabs[1:]):
        a, b_ = dump.slps_strings(j, base), dump.slps_strings(e, base)
        for k, ((o1, s1), (o2, s2)) in enumerate(zip(a, b_)):
            r = by['%s:%d' % (name, k)]
            kr = by[r[2]][5] if r[2] else r[5]
            if not kr and '%s:%d' % (name, k) != 'SLPS:7' and s1 != s2:
                bad += 1
                print('✗ 번역 안 한 %s:%d 가 바뀜' % (name, k))
    # 이름판 미리보기
    s7 = dump.slps_strings(e, 0x06C9F0)[7][1]
    print('이름판:', text(s7, inv)[:120], '…')
    print('─ 대조 %d줄 · 불일치 %d' % (n, bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
