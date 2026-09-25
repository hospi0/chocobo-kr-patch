# -*- coding: utf-8 -*-
r"""대사창 줄 폭 전수 검사 — 빌더와 같은 `reflow.paginate()` 결과에서 «개행 앞 줄 > 중간 폭»(딱 차면 빈 줄 / 넘치면 접힘)을 찾는다.

  python tools/widthscan.py
창 폭 W = 원문 최장 줄 + 1. 개행이 뒤따르는 줄은 W-1(=mid)까지, 페이지 마지막 줄은 W(=last)까지.
"""
import glob, io, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build, fill, reflow

BS = '\\n'


def scan():
    rs = {r[0]: r for r in build.rows()}
    bad = []
    for p in sorted(glob.glob(os.path.join(ROOT, 'work', 'kr', 'tr', '*.tsv'))):
        for ln in io.open(p, encoding='utf-8').read().split('\n'):
            rid, _, kr = ln.partition('\t')
            if not rid.startswith('MSG') or rid not in rs or fill.is_zukan(rid) or rid in reflow.MENU:
                continue
            out = reflow.paginate(fill.norm(kr), rs[rid][3])
            last, mid, H = fill.window_limits(rs[rid][3])
            pages = out.rstrip('¶').split('{D}')
            for pi, pg in enumerate(pages):
                if pg.startswith(BS):
                    pg = pg[len(BS):]
                ls = pg.split(BS)
                for li, l in enumerate(ls):
                    lim = last if (pi == len(pages) - 1 and li == len(ls) - 1) else mid
                    if fill.cells(l) > lim:
                        bad.append((rid, fill.cells(l), lim, l, kr))
    return bad


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    bad = scan()
    print('넘치는 줄 %d' % len(bad))
    for rid, c, lim, l, kr in bad:
        print('%s  %d칸 > %d  「%s」   ← %s' % (rid, c, lim, l, kr))
