# -*- coding: utf-8 -*-
r"""대사창 한도(원문 폭·줄 수)에 맞춰 번역 대사를 다시 접는다 — `work/kr/tr/*.tsv` 를 고쳐 쓴다

  python tools/reflow.py            # 미리보기(고칠 줄만 출력)
  python tools/reflow.py --write    # tr 파일에 반영

- 페이지({D}) 안의 줄을 이어 붙인 뒤 «공백»과 «문장부호 뒤»에서만 접는다(⛔글자 단위 분할 없음).
- 중간 줄은 `window_limits()` 의 중간 폭, 마지막 줄은 마지막 폭. 한 페이지가 창 줄 수를 넘으면 `{D}\n` 으로 새 페이지.
- 원래 있던 {D} 는 그대로 페이지 경계로 둔다(번역자의 호흡).
- 선택지 메뉴(줄 하나 = 항목)는 건드리지 않는다 — MENU 목록.
"""
import glob, io, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fill, build

BS = '\\n'
# 줄 하나가 곧 항목 — 이어 붙이면 안 된다
MENU = {'MSG:0:5', 'MSG:0:59', 'MSG:0:104', 'MSG:0:217', 'MSG:0:303', 'MSG:0:304', 'MSG:0:305', 'MSG:0:306',
        'MSG:0:307', 'MSG:0:309', 'MSG:2:133', 'MSG:2:134', 'MSG:2:135', 'MSG:2:136', 'MSG:2:168', 'MSG:1:276',
        'MSG:0:229', 'MSG:0:230'}   # 229·230 = 대기 코드로 점 찍는 연출
BREAK_AFTER = ',.!?…~'


NBSP = ' '


def protect(text):
    """【…】 와 <0X>…<00> 안의 공백은 끊지 않는다 → NBSP 로 바꿔 둔다"""
    out, depth = [], 0
    i = 0
    while i < len(text):
        if text.startswith('【', i) or (text.startswith('<0', i) and text[i:i + 4] != '<00>'):
            depth += 1
        elif text.startswith('】', i) or text.startswith('<00>', i):
            depth = max(0, depth - 1)
        ch = text[i]
        out.append(NBSP if (ch == ' ' and depth) else ch)
        i += 1
    return ''.join(out)


def units(text):
    """끊는 자리 단위 → [(조각, 앞에 공백?)] — 공백, 그리고 공백 없는 낱말 안의 문장부호 뒤"""
    out = []
    for w in protect(text).split(' '):
        if w == '':
            continue
        parts = [p for p in re.findall(r'.*?[%s]+|.+$' % re.escape(BREAK_AFTER), w) if p]
        for pi, p in enumerate(parts):
            out.append((p, pi == 0))
    return out


def join(us):
    s = ''
    for p, sp in us:
        s += (' ' if (s and sp) else '') + p
    return s.replace(NBSP, ' ')


def wrap(text, lim_mid, lim_last, want, maxn, final):
    """줄 길이를 «고르게» — 줄 수는 want(원래 줄 수) 부터 maxn 까지 시도, 각 줄 ≤ 한도, 짧은 꼬리 줄 벌점"""
    us = units(text)
    m = len(us)
    if m == 0:
        return ['']
    W = [[0] * (m + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(i + 1, m + 1):
            W[i][j] = fill.cells(join(us[i:j]))
    best = None
    for n in range(max(1, want), maxn + 1):
        INF = float('inf')
        dp = [[INF] * (m + 1) for _ in range(n + 1)]
        bk = [[-1] * (m + 1) for _ in range(n + 1)]
        dp[0][0] = 0
        for k in range(1, n + 1):
            for j in range(1, m + 1):
                lim = lim_last if (k == n and final) else lim_mid
                for i in range(k - 1, j):
                    if dp[k - 1][i] == INF:
                        continue
                    w = W[i][j]
                    if w > lim:
                        continue
                    cost = dp[k - 1][i] + (lim_mid - w) ** 2 + (40 if w <= 2 else 0)
                    if cost < dp[k][j]:
                        dp[k][j] = cost; bk[k][j] = i
        if dp[n][m] < float('inf'):
            lines, j = [], m
            for k in range(n, 0, -1):
                i = bk[k][j]; lines.append(join(us[i:j])); j = i
            best = lines[::-1]
            break
    return best


def reflow(kr, jp_hex):
    lim_last, lim_mid, H = fill.window_limits(jp_hex)
    tail = '¶' if kr.endswith('¶') else ''
    body = kr[:-1] if tail else kr
    pages = body.split('{D}')
    out_pages = []
    for pi, page in enumerate(pages):
        if page.startswith(BS):
            page = page[len(BS):]
        want = len(page.split(BS))
        lead = ' ' if page.startswith(' ') else ''
        text = re.sub(' +', ' ', ' '.join(l.strip(' ') for l in page.split(BS))).strip(' ')
        ls = wrap(text, lim_mid, lim_last, min(want, H), H, pi == len(pages) - 1)
        if ls is None:
            return None
        if lead:
            ls[0] = lead + ls[0]
        out_pages.append(BS.join(ls))
    return ('{D}' + BS).join(out_pages) + tail


def paginate(kr, jp_hex):
    """★빌드 때 쓰는 자동 버튼 대기 — 번역문(낱말)은 그대로, 창에 안 들어가는 페이지만 창 폭에 «꽉 채워» 다시 접어
    줄 수를 최소로 만든 뒤 창 줄 수(H)가 찰 때마다 {D}(버튼 대기)를 넣는다. 들어가는 페이지는 손대지 않는다.
    창 크기는 스크립트가 원문 기준으로 정한다(폭 = 원문 최장 줄 + 1).
    """
    lim_last, lim_mid, H = fill.window_limits(jp_hex)
    tail = '¶' if kr.endswith('¶') else ''
    body = kr[:-1] if tail else kr
    pages = body.split('{D}')
    out = []
    for pi, page in enumerate(pages):
        if page.startswith(BS):
            page = page[len(BS):]
        src = page.split(BS)
        final_page = pi == len(pages) - 1
        fits = len(src) <= H and all(
            fill.cells(l) <= (lim_last if (final_page and li == len(src) - 1) else lim_mid)
            for li, l in enumerate(src))
        if fits:
            out.append(page); continue
        lead = ' ' if page.startswith(' ') else ''
        text = re.sub(' +', ' ', ' '.join(l.strip(' ') for l in src)).strip(' ')
        lines, cur = [], lead
        for p_, sp in units(text):
            cand = cur + (' ' if (sp and cur.strip()) else '') + p_
            if fill.cells(cand.replace(NBSP, ' ')) <= lim_mid or not cur.strip():
                cur = cand
            else:
                lines.append(cur.replace(NBSP, ' ')); cur = p_
        lines.append(cur.replace(NBSP, ' '))
        # 끝 줄은 한 칸 더 쓸 수 있다 — 마지막 두 줄이 합쳐지면 합친다
        if final_page and len(lines) >= 2:
            j = lines[-2] + ' ' + lines[-1]
            if fill.cells(j) <= lim_last:
                lines[-2:] = [j]
        for i in range(0, len(lines), H):
            out.append(BS.join(lines[i:i + H]))
    return ('{D}' + BS).join(out) + tail


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    write = '--write' in sys.argv
    rs = {r[0]: r for r in build.rows()}
    left = []
    n = 0
    for p in sorted(glob.glob(os.path.join(ROOT, 'work', 'kr', 'tr', '*.tsv'))):
        L = io.open(p, encoding='utf-8').read().split('\n')
        changed = False
        for i, ln in enumerate(L):
            rid, _, kr = ln.partition('\t')
            if not rid.startswith('MSG') or fill.is_zukan(rid) or rid not in rs:
                continue
            err, _ = fill.check(rid, rs[rid][3], kr)
            if not err:
                continue
            if rid in MENU:
                left.append((rid, kr, err)); continue
            new = reflow(fill.norm(kr), rs[rid][3])
            # 페이지({D})를 늘리는 재조판은 받지 않는다 — 1줄 창에서 낱말마다 넘기게 된다. 그건 번역을 줄인다.
            if new is not None and new.count('{D}') > kr.count('{D}'):
                new = None
            if new is None or fill.check(rid, rs[rid][3], new)[0]:
                left.append((rid, kr, err)); continue
            n += 1
            print('%s\n   전 %s\n   후 %s' % (rid, kr, new))
            L[i] = rid + '\t' + new
            changed = True
        if write and changed:
            io.open(p, 'w', encoding='utf-8').write('\n'.join(L))
    print('─ 다시 접음 %d줄 · 손으로 볼 것 %d줄' % (n, len(left)))
    for rid, kr, err in left:
        print('✗ %s  %s\n     %s' % (rid, ' · '.join(err), kr))


if __name__ == '__main__':
    main()
