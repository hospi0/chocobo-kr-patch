# -*- coding: utf-8 -*-
r"""번역 되채움기 — `work/kr/tr/*.tsv` → `work/kr/text.tsv` 의 kr 열 (★쓰는 순간 규칙 검사)

  python tools/fill.py            # 전부 검사 + 통과한 줄만 반영
  python tools/fill.py tr/03.tsv  # 그 배치만 보고(반영은 전부 다시)

## 번역 배치 형식
`id<TAB>kr` 한 줄씩. kr 표기는 영문 열과 같다:
  `\n` 개행 · `{D}` 페이지 넘김(뒤에 `\n`) · `¶` 메시지 끝(0C) · `<04>…<00>` 서식 · `{B}` 주인공 이름 ·
  `{6:XX}` 대기 · `{7:XX}` 숫자/문자 끼움 · `{8:XX}` — ★인자 바이트까지 원문 그대로 · 공백 ` ` = 0x0F(한 칸 12px) · `...` 은 `…` 한 칸으로 바꾼다.

## 막는 것 (확실한 것만)
  ①제어 토큰(<XX>·{B}·{6}{7}{8}·¶) 순서가 «일본어 원문»과 다르다
  ②글꼴에 없는 문자
  ③한 줄 18칸 초과 / 한 페이지 4줄 초과(원문이 더 길면 원문 기준)
  ④도감(MSG:2:0‥81)은 8칸 자동 접힘 6줄 초과
  ⑤한글 음절 종류 796 초과(글꼴 칸 예산 — 영소문자·0x10/0x20/0x25 제외)
경고: 16칸 초과 줄 · 부호 뒤 공백(빌더가 뗀다)
"""
import csv, glob, io, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msg

TSV = os.path.join(ROOT, 'work', 'kr', 'text.tsv')
TRD = os.path.join(ROOT, 'work', 'kr', 'tr')
BUDGET = 796   # 882 − ASCII 77(영소문자 포함 — 세이브 화면 printf 가 쓴다) − 기호 6(○△□×【】) − 0x10·0x20(변환기가 공백 취급)·0x25(% 서식)
W_HARD, W_SOFT, PAGE = 18, 16, 4
PUNCT = ',.!?:;'
# ○△□× 는 원래 글리프(2바이트)를 남겨 쓴다
OK_CH = set('!?,.~…·()+/:-「」―○△□×【】') | set('0123456789') | set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
TOK = re.compile(r'<[0-9A-F]{2}>|\{[0-9A-F]+(?::[0-9A-F]{2})?\}|\\n|¶')
VAR_W = {'{B}': 6, '7': 6}            # 이름·숫자 끼움 폭(가정) — {7:XX} 는 인자와 무관하게 6

# SLPS 표별 칸 폭(원문 표 전체의 최대 칸) — 목록 창의 칸이 고정이다
TABLE_W = {'CARD': 9, 'ITEM': 10, 'MON': 8, 'SKILL': 8, 'DESC': 22, 'ATTR': 22, 'ATTR2': 22, 'STAT': 24}
# ITEM 분류별 칸 폭 = 그 분류 원문 최대(v0.1 실기: 「블리자드의 책」 7칸이 Lv 칸을 덮었다)
ITEM_CAT_W = [(0, 11, 7), (12, 35, 8), (36, 66, 8), (67, 93, 7), (94, 154, 9), (155, 192, 9),
              (193, 216, 10), (217, 229, 8), (230, 239, 6), (240, 255, 9)]
# 개행 없이 «칸 수로 접히는» 창 — kr 은 \n 으로 쓰고 빌더가 줄마다 공백으로 채운다
PADROW = {'SLPS:32': 21, 'SLPS:110': 17, 'SLPS:115': 17, 'SLPS:116': 17, 'SLPS:117': 17, 'SLPS:118': 17,
          'SLPS:119': 17, 'SLPS:120': 17, 'SLPS:121': 17, 'SLPS:122': 17, 'SLPS:127': 16}

BANNER = ('┌ 규칙: 제어토큰=원문 순서 · 줄≤%d칸(권장%d) · 페이지≤%d줄 · 도감 8칸×6줄 · 음절≤%d\n'
          '└ 부호 뒤 공백은 빌더가 뗀다 · 글자 단위로 자르지 말 것 · 이름 = 거센소리(か=카 た=타 つ=츠)'
          % (W_HARD, W_SOFT, PAGE, BUDGET))


def norm(s):
    s = s.replace('...', '…')
    return re.sub(r'([%s]) +' % re.escape(PUNCT), r'\1', s)


def jp_tokens(hexs):
    """원문의 «지켜야 할» 토큰 순서"""
    out = []
    for k, v in msg.tokens(bytes.fromhex(hexs)):
        if k == 'f':
            out.append('<%02X>' % v)
        elif k == 't' and v == 'EOM':
            out.append('¶')
        elif k == 'a':
            out.append('{%X:%02X}' % v)
        elif k == 'c' and v < 0x10 and v != 0x0D:
            out.append('{%X}' % v)
    return out


def jp_shape(hexs):
    """원문 (최대 줄 칸, 최대 페이지 줄 수)"""
    w = n = mw = mp = 0
    for k, v in msg.tokens(bytes.fromhex(hexs)):
        if k == 't' and v in ('NL', 'EOM', 'END'):
            mw = max(mw, w); w = 0
            if v == 'NL':
                n += 1
        elif k == 'c' and v == 0x0D:
            mp = max(mp, n + 1); n = -1
        elif (k == 't' and v == 'SP') or (k == 'c' and v >= 0x10):
            w += 1
        elif k == 'a' and v[0] == 7:
            w += 6
    return mw, max(mp, n + 1)


def window_limits(jp_hex):
    """원문으로 본 대사창 한도 → (마지막 줄 폭, 중간 줄 폭, 페이지 줄 수)

    ⛔v0.1 실기: 창 폭·높이는 이벤트 스크립트가 «원문에 맞춰» 지정한다(오버레이 0x80165E80 → 0x8002B188).
    렌더러는 폭 W 격자에 채우고 개행 = (칸÷W+1)×W → 줄이 W 를 넘으면 접혀 창을 넘쳐 «자동 스크롤»,
    W 를 딱 채우면 다음 개행이 한 행을 더 건너 «빈 줄». 넘치는 건 오류가 아니라 빌더(`reflow.paginate`)가 {D} 로 넘긴다.
    """
    lines, w, pages, n = [], 0, [], 1
    for k, v in msg.tokens(bytes.fromhex(jp_hex)):
        if k == 't' and v in ('NL', 'EOM', 'END'):
            lines.append((w, v)); w = 0
            if v == 'NL':
                n += 1
        elif k == 'c' and v == 0x0D:
            pages.append(n); n = 0
        elif (k == 't' and v == 'SP') or (k == 'c' and v >= 0x10):
            w += 1
        elif k == 'a' and v[0] == 7:
            w += 6
    pages.append(n)
    jw = max(l[0] for l in lines)
    # 실측 3건(뱅크1 표10 창 10=9+1 · 뱅크0 표126 창 8=7+1 · 뱅크1 표15 창 9=8+1): 창 폭 = 원문 최장 줄 + 1
    # → 대사 끝 줄은 창 폭까지, 뒤에 개행이 오는 줄은 한 칸 덜(딱 채우면 빈 줄)
    return jw + 1, jw, max(pages)


def kr_tokens(s):
    return [t for t in TOK.findall(s) if t not in ('\\n', '{D}')]


def cells(line):
    n = 0
    for t in re.split(r'(<[0-9A-F]{2}>|\{[0-9A-F]+(?::[0-9A-F]{2})?\})', line):
        if not t:
            continue
        if t.startswith('<') and len(t) == 4:
            continue
        if t.startswith('{'):
            n += VAR_W.get(t, VAR_W.get(t[1:].split(':')[0], 0))
            continue
        n += len(t.replace('¶', ''))
    return n


def is_zukan(rid):
    p = rid.split(':')
    return p[0] == 'MSG' and p[1] == '2' and int(p[2]) <= 81


def zukan_rows(s, w=8):
    """8칸 자동 접힘 — 낱말 경계에서 공백으로 채운다(빌더와 같은 규칙)"""
    rows, cur = [], ''
    for word in s.split(' '):
        if not cur:
            cand = word
        else:
            cand = cur + ' ' + word
        if len(cand) <= w:
            cur = cand
            continue
        if cur:
            rows.append(cur)
        while len(word) > w:          # 8칸보다 긴 낱말만 어쩔 수 없이
            rows.append(word[:w]); word = word[w:]
        cur = word
    if cur:
        rows.append(cur)
    return rows


def check(rid, jp_hex, kr):
    err, warn = [], []
    k = norm(kr)
    jt, kt = jp_tokens(jp_hex), kr_tokens(k)
    if jt != kt:
        err.append('토큰 %s ≠ 원문 %s' % (''.join(kt), ''.join(jt)))
    if '¶' in jt and not k.endswith('¶'):
        err.append('¶ 는 맨 끝')
    plain = TOK.sub('', k)
    plain = re.sub(r'\{[0-9A-F]+(?::[0-9A-F]{2})?\}', '', plain)
    bad = sorted({c for c in plain if not ('가' <= c <= '힣' or c == ' ' or c in OK_CH)})
    if bad:
        err.append('글꼴에 없는 문자 %r' % ''.join(bad))
    if re.search(r'\{D\}(?!\\n|$)', k):
        err.append('{D} 뒤엔 \\n')
    if is_zukan(rid):
        if '\\n' in k:
            err.append('도감은 개행 없이 쓴다(8칸 자동 접힘)')
        rows = zukan_rows(plain)
        if len(rows) > 6:
            err.append('도감 %d줄 > 6 : %s' % (len(rows), ' / '.join(rows)))
        if any(len(r) > 8 for r in rows):      # ⛔글자 단위로 잘라 넣지 않는다 — 실패시키고 사람이 줄인다
            err.append('8칸 넘는 낱말(글자 단위 분할 금지): ' + ' / '.join(rows))
        return err, warn
    jw, jp_pages = jp_shape(jp_hex)
    tb = rid.split(':')[0]
    if rid in PADROW:                       # 고정 폭 줄 채움 창(개행 코드 없이 칸 수로 접힌다)
        w = PADROW[rid]
        rows = k.split('\\n')
        if any(cells(r) > w for r in rows):
            err.append('줄 채움 창 %d칸 초과: %s' % (w, ' / '.join(rows)))
        return err, warn
    if tb in TABLE_W:                       # 이름표 — 표 전체의 최대 칸이 곧 칸 폭
        if '\\n' in k:
            err.append('이름표엔 개행 없음')
        c = cells(k)
        lim = TABLE_W[tb]
        if tb == 'ITEM':                    # ★목록에서 이름 뒤 «Lv» 칸이 분류마다 고정(책 6칸째) — 분류별 원문 최대
            n = int(rid.split(':')[1])
            lim = next(w for a, b, w in ITEM_CAT_W if a <= n <= b)
        if c > lim:
            err.append('%d칸>%d(%s 폭) 「%s」' % (c, lim, tb, k))
        return err, warn
    if tb == 'SLPS':                        # 메뉴 — 원문 칸 수가 곧 칸 폭(3칸 이하는 +1 까지 경고)
        for l in k.split('\\n'):
            c = cells(l)
            if c > (jw + 1 if jw <= 3 else jw):
                err.append('%d칸>원문 %d 「%s」' % (c, jw, l))
            elif c > jw:
                warn.append('%d칸>원문 %d 「%s」' % (c, jw, l))
        return err, warn
    if rid.startswith('MSG'):               # ★대사창 크기는 «스크립트가 원문 기준으로 지정» — 원문 폭·줄 수 안에
        lim_last, lim_mid, H = window_limits(jp_hex)
        pages = k.split('{D}')
        for pi, page in enumerate(pages):
            lines = page.split('\\n')
            if lines and lines[0] == '' and pi > 0:
                lines = lines[1:]
            if len(lines) > H:
                warn.append('페이지 %d줄>창 %d줄 → 빌더가 {D}' % (len(lines), H))
            for li, l in enumerate(lines):
                last = (pi == len(pages) - 1 and li == len(lines) - 1)
                lim = lim_last if last else lim_mid
                c = cells(l)
                if c > lim:
                    warn.append('%d칸>창 %d칸%s → 빌더가 나눔' % (c, lim, '' if last else '(중간 줄)'))
        return err, warn
    hard = max(W_HARD, jw)
    for page in k.split('{D}'):
        lines = [l for l in page.split('\\n')]
        if lines and lines[0] == '':
            lines = lines[1:]
        if len(lines) > max(PAGE, jp_pages):
            err.append('페이지 %d줄' % len(lines))
        for l in lines:
            c = cells(l)
            if c > hard:
                err.append('%d칸>%d 「%s」' % (c, hard, l))
            elif c > max(W_SOFT, jw):
                warn.append('%d칸 「%s」' % (c, l))
    if re.search(r'[%s] ' % re.escape(PUNCT), kr.replace('...', '…')):
        pass  # 빌더가 뗀다(norm)
    return err, warn


def load_tr(paths):
    tr = collections.OrderedDict()
    src = {}
    for p in paths:
        for ln in io.open(p, encoding='utf-8'):
            ln = ln.rstrip('\r\n')
            if not ln.strip() or ln.startswith('#'):
                continue
            rid, _, kr = ln.partition('\t')
            tr[rid.strip()] = kr
            src[rid.strip()] = os.path.basename(p)
    return tr, src


def syllables(texts):
    c = collections.Counter()
    for t in texts:
        for ch in TOK.sub('', t):
            if '가' <= ch <= '힣':
                c[ch] += 1
    return c


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print(BANNER)
    rows = list(csv.reader(io.open(TSV, encoding='utf-8'), delimiter='\t'))
    head, body = rows[0], rows[1:]
    byid = {r[0]: r for r in body}
    allp = sorted(glob.glob(os.path.join(TRD, '*.tsv')))
    only = [os.path.join(ROOT, 'work', 'kr', a) if not os.path.isabs(a) else a for a in sys.argv[1:]]
    tr, src = load_tr(allp)
    nerr = nwarn = 0
    good = {}
    for rid, kr in tr.items():
        if rid not in byid:
            print('✗ %s 없는 id' % rid); nerr += 1; continue
        r = byid[rid]
        if r[2]:
            print('✗ %s 는 %s 의 중복 — 대표 id 에 쓸 것' % (rid, r[2])); nerr += 1; continue
        err, warn = check(rid, r[3], kr)
        show = not only or any(os.path.basename(o) == src[rid] for o in only)
        if err:
            nerr += 1
            print('✗ %s  %s\n     %s' % (rid, ' · '.join(err), kr))
        else:
            good[rid] = norm(kr)
            if warn and show:
                nwarn += 1
                print('△ %s  %s' % (rid, ' · '.join(warn)))
    for r in body:
        rep = r[2] or r[0]
        r[5] = good.get(rep, '')
    with io.open(TSV, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join('\t'.join(r) for r in [head] + body) + '\n')
    syl = syllables(good.values())
    uniq = [r for r in body if not r[2]]
    done = sum(1 for r in uniq if r[0] in good)
    print('─ 반영 %d/%d줄 · 오류 %d · 경고 %d · 음절 %d종/%d%s'
          % (done, len(uniq), nerr, nwarn, len(syl), BUDGET, '  ⛔초과' if len(syl) > BUDGET else ''))
    if len(syl) > BUDGET:
        rare = sorted(syl.items(), key=lambda x: x[1])[:60]
        print('  드문 음절:', ' '.join('%s%d' % x for x in rare))
    return 1 if nerr or len(syl) > BUDGET else 0


if __name__ == '__main__':
    sys.exit(main())
