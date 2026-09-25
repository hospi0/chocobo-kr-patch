# -*- coding: utf-8 -*-
r"""한글 빌드 — 원본에서 «한 번에» 다시 만든다

  python tools/build.py              # work/kr/ 에 FONT.PXL·MSG.BIN·SLPS_012.34 만
  python tools/build.py --disc       # + 디스크 이미지(work/out) + 배포 묶음(dist/)
  python tools/build.py --disc --install   # + F: 사본 교체

## 순서
1. `work/kr/text.tsv` kr 열(→ `tools/fill.py` 가 이미 검사·정규화) 을 읽는다
2. 음절 배정 — 1바이트(색인<240, 작은 글꼴도 그림) 189칸: 이름 → SLPS 빈출 → MSG 빈출 / 나머지는 2바이트
3. FONT.PXL — 12×12(갈무리11) + 1바이트는 8×8(갈무리7) · 쉼표(0x2C)는 한국어 쉼표로 다시 그림
4. MSG.BIN — 원래 자리에 들어가면 제자리, 안 들어가면 뱅크 끝 빈 곳으로 옮기고 표만 고친다
5. SLPS — 표 9개를 각 구역 안에서 다시 채운다(같은 문자열은 한 번만). 이름 글자판(SLPS:7)은 새로 짠다
"""
import argparse, collections, csv, hashlib, io, os, re, shutil, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msg, dump, fill, krfont, reflow, gilgfx, missgfx

JP = os.path.join(ROOT, 'work', 'jp')
OUT = os.path.join(ROOT, 'work', 'kr')
TSV = os.path.join(OUT, 'text.tsv')
ROMDIR = r'C:\claude\roms\ps\Chocobo no Fushigi na Dungeon (Japan)'
FCHD = r'F:\hospi\roms\ps roms\Chocobo no Fushigi na Dungeon (Japan).chd'   # ★사용자가 실행하는 설치본은 이 .chd 하나(옛 폴더 없음)
CHDMAN = r'C:\claude\utils\CHDMAN\chdman.exe'
BIN = 'Chocobo no Fushigi na Dungeon (Japan).bin'
SRC_MD5 = '52914D6BF757433174016768F17E016C'
VER = 'v0.91'
XDELTA = r'C:\claude\utils\xdelta.exe'
BS = chr(92)

# ── 남기는 글리프 ───────────────────────────────────────────────
# ASCII 자리 중 한국어에 쓰는 것(색인 = 코드−0x10)
PUNCT = {'!': 0x21, '(': 0x28, ')': 0x29, '+': 0x2B, ',': 0x2C, '-': 0x2D, '―': 0x2D, '.': 0x2E,
         '/': 0x2F, ':': 0x3A, '~': 0x3C, '·': 0x3D, '…': 0x3E, '?': 0x3F, '「': 0x40, '」': 0x60}
# ★영소문자도 남긴다 — 세이브 화면이 SLPS 안의 printf 서식 "%-6s Lv:%2d…"(0x13F1)·"time %5d:%2d:%2d"(0x1400) 으로
#   그린다(번역 표 밖). v0.1 에서 소문자 칸을 한글로 쓰는 바람에 「L지」「다책크잠」이 나왔다(2026-09-22).
ASCII = {c: ord(c) for c in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'}
ASCII.update(PUNCT)
KEEP1 = {v - 0x10 for v in ASCII.values()}                    # 77칸(숫자·대소문자·부호)
# 한자 칸에 있는 기호(원래 글리프를 그대로 쓴다)
SYM2 = {'【': 796, '】': 797, '×': 798, '○': 799, '□': 800, '△': 801}
# ⛔0x20·0x25 는 음절에 못 쓴다 — 문자열 변환기(0x8001F7B0)가 0x20 을 공백으로, 0x25 를 % 서식으로 처리한다.
#   0x20(색인16)은 «빈 글리프»로 비워 두고 대사 속 공백으로 쓴다(아래 SPACE_W).
#   (0x10 은 한때 «대사 공백용 빈 글리프»로 비웠다 — 공백 폭 가설은 틀렸지만 칸은 비운 채 둔다. 창 크기는 스크립트 지정.)
SPACE_W = 0x10
NOSYL1 = {0x10 - 0x10, 0x20 - 0x10, 0x25 - 0x10}
FREE1 = [i for i in range(240) if i not in KEEP1 and i not in NOSYL1]   # 160칸
# 작은 글꼴(8×8)로 그려지는 문자열 — 1바이트 음절만(작은 글꼴엔 색인<240 만 있다). v0.1 실기: 「남은」→「은」
SMALL_IDS = {'SLPS:54'}
FREE2 = [i for i in range(241, 882) if i not in SYM2.values()]  # 240(0x0100)은 비워 둔다
TOKRE = re.compile(r'<([0-9A-F]{2})>|\{([0-9A-F]+)(?::([0-9A-F]{2}))?\}')


def rows():
    r = list(csv.reader(io.open(TSV, encoding='utf-8'), delimiter='\t'))
    return r[1:]


def hangul(s):
    return [c for c in TOKRE.sub('', s.replace(BS + 'n', '')) if '가' <= c <= '힣']


# ── 음절 배정 ───────────────────────────────────────────────────
def allocate(rs, board_extra=''):
    tr = {r[0]: r[5] for r in rs if r[5]}
    uniq = [r for r in rs if not r[2] and r[5]]
    allsyl = collections.Counter(c for r in uniq for c in hangul(r[5]))
    names = set()
    for r in uniq:                                  # 화자 이름칸(작은 글꼴) · 기본 이름 · 작은 글꼴 라벨
        if (r[0].startswith('MON:') and int(r[0].split(':')[1]) >= 112) or r[0] == 'SLPS:0' or r[0] in SMALL_IDS:
            names |= set(hangul(r[5]))
    slps = collections.Counter(c for r in uniq if not r[0].startswith('MSG') for c in hangul(r[5]))
    msgc = collections.Counter(c for r in uniq if r[0].startswith('MSG') for c in hangul(r[5]))
    order = sorted(names) + [c for c, _ in slps.most_common() if c not in names]
    order += [c for c, _ in msgc.most_common() if c not in order]
    order += [c for c in allsyl if c not in order]
    one = order[:len(FREE1)]
    two = order[len(FREE1):]
    if len(two) > len(FREE2):
        raise SystemExit('⛔ 음절 %d종 > 칸 %d' % (len(order), len(FREE1) + len(FREE2)))
    code = {}
    for c, i in zip(one, FREE1):
        code[c] = i
    for c, i in zip(two, FREE2):
        code[c] = i
    return code, set(one)


def enc_idx(i):
    v = i + 0x10
    return bytes([v]) if v < 0x100 else bytes([v >> 8, v & 0xFF])


def encode(s, code, wide_space=False):
    """wide_space: 대사창 — 공백을 0x0F 대신 빈 글리프 0x20 으로

    ⛔v0.1 실기: 대사창 폭은 공백(0x0F)을 빼고 재는데 그리기는 한 칸을 차지한다 →
    공백 든 줄이 격자 폭에 딱 차면 커서가 다음 행으로 넘어가 있고, 이어 오는 \n 이 한 행을 더 넘겨 «빈 줄».
    (렌더러 0x8001FF80: 개행 = (칸÷폭+1)×폭)
    """
    out = bytearray()
    t = s.replace(BS + 'n', '\n')
    p = 0
    while p < len(t):
        m = TOKRE.match(t, p)
        if m:
            if m.group(1):
                out += bytes([0x04, int(m.group(1), 16)])
            else:
                c = int(m.group(2), 16)
                out.append(c)
                if m.group(3) is not None:
                    out.append(int(m.group(3), 16))
            p = m.end()
            continue
        ch = t[p]; p += 1
        if ch == '\n':
            out.append(0x0A)
        elif ch == '¶':
            out.append(0x0C)
        elif ch == ' ':
            out.append(SPACE_W if wide_space else 0x0F)
        elif ch in ASCII:
            out.append(ASCII[ch])
        elif ch in SYM2:
            out += enc_idx(SYM2[ch])
        elif ch in code:
            out += enc_idx(code[ch])
        else:
            raise SystemExit('⛔ 인코딩 못 하는 문자 %r in %r' % (ch, s))
    out.append(0x00)
    return bytes(out)


def cells(s):
    return fill.cells(s)


def layout(rid, kr, jp_hex):
    """화면 규칙대로 모양을 만든다 — 도감 8칸 접힘 · 줄 채움 창 · STAT 오른쪽 맞춤(선택)"""
    if fill.is_zukan(rid):
        rows_ = fill.zukan_rows(kr)
        return ''.join(r + ' ' * (8 - len(r)) if k < len(rows_) - 1 else r for k, r in enumerate(rows_))
    if rid.startswith('MSG') and rid not in reflow.MENU:   # 창이 차면 버튼 대기({D}) 자동 삽입
        out = reflow.paginate(kr, jp_hex)
        # ★접은 뒤에도 한도를 넘는 줄이 있으면 멈춘다 — 색 글자 뒤 조사(<02>…<00>라고)처럼 끊을 수 없는 덩어리가
        #   «개행 앞 줄 = 창 폭»이 되면 빈 줄이 생긴다(실기 2026-09-26: «햄 호루라기라고 / (빈 줄) / 해»). 번역을 다듬을 것.
        last, mid, H = fill.window_limits(jp_hex)
        pages = out.rstrip('¶').split('{D}')
        for pi, pg in enumerate(pages):
            ls = (pg[len(BS + 'n'):] if pg.startswith(BS + 'n') else pg).split(BS + 'n')
            for li, l in enumerate(ls):
                lim = last if (pi == len(pages) - 1 and li == len(ls) - 1) else mid
                if not any('가' <= c <= '힣' for c in l):       # 영문 그대로 둔 디버그 메뉴(MSG:x:305 START…)는 제외
                    continue
                assert fill.cells(l) <= lim, '%s 줄 폭 %d칸 > %d(창 폭 %d): %s' % (rid, fill.cells(l), lim, last, l)
        return out
    if rid in fill.PADROW:
        w = fill.PADROW[rid]
        rs_ = kr.split(BS + 'n')
        return ''.join(r + ' ' * (w - cells(r)) if k < len(rs_) - 1 else r for k, r in enumerate(rs_))
    return kr


def stat_pad(kr, jp_hex, cap=99):
    """원문은 왼쪽 공백으로 오른쪽 맞춤 — 구역이 모자라면 공백을 cap 칸까지만 넣는다"""
    jw, _ = fill.jp_shape(jp_hex)
    return ' ' * min(cap, max(0, jw - cells(kr))) + kr


# ── 글꼴 ───────────────────────────────────────────────────────
COMMA = ['............', '............', '............', '............', '............', '............',
         '............', '............', '.##@........', '.##@........', '..#@........', '.#@.........']


def build_font(code, one):
    f = bytearray(open(os.path.join(JP, 'FONT.PXL'), 'rb').read())
    for ch, i in code.items():
        krfont.put(f, i, krfont.glyph12(ch))
        if ch in one:
            krfont.put_small(f, i, krfont.glyph8(ch))
    import numpy as np
    g = np.array([['.#o@'.index(c) for c in row] for row in COMMA], np.uint8)
    krfont.put(f, 0x2C - 0x10, g)
    for i in NOSYL1:                               # 0x10 = 대사 공백(빈 글리프), 0x20·0x25 = 안 씀 → 모두 비운다
        krfont.put(f, i, np.zeros((12, 12), np.uint8))
        krfont.put_small(f, i, np.zeros((8, 8), np.uint8))
    f = bytearray(gilgfx.apply(f))                 # HUD·상점 값의 구운 «ｷﾞﾙ» 그림 → «길»
    assert len(f) == 65536
    return bytes(f)


# ── MSG.BIN ────────────────────────────────────────────────────
MSG_LOAD = 0x3000   # 뱅크 중 메모리에 올라오는 크기(세이브스테이트 실측: 뱅크1 → 0x800791F0 에 0x3000)


def build_msg(rs, code):
    """★원문과 같은 꼴로 다시 짠다 — 표 순서대로 «빈틈 없이 연속» + 끝에 0xCD 표지

    ⛔2026-09-22 v0.1: 길어진 대사를 뱅크 끝 빈 곳으로 «옮기고 표만 고쳤더니» 그 979줄만
    버튼 대기가 안 걸리고 자동으로 넘어갔다. 원문 뱅크는 오프셋이 오름차순·연속이고
    마지막 문자열 뒤에 0xCD 가 있다 — 게임이 «다음 오프셋 − 이 오프셋»을 길이로 쓰는 듯하다.
    """
    d = bytearray(open(os.path.join(JP, 'MSG.BIN'), 'rb').read())
    by = {r[0]: r for r in rs}
    for b in msg.banks(bytes(d)):
        base = b * msg.BANK
        t = msg.table(bytes(d), b)
        if not t:
            continue
        ss = msg.strings(bytes(d), b)
        n = len(t)
        blob = bytearray(); newoff = {}
        offs = []
        for i, (off, s) in enumerate(ss):
            if off in newoff:                         # 원문도 같은 곳을 가리키던 항목(뱅크2)
                offs.append(newoff[off]); continue
            r = by['MSG:%d:%d' % (b, i)]
            new = encode(layout(r[0], r[5], r[3]), code) if r[5] else s   # 공백은 원문처럼 0x0F (빈 글리프 가설은 틀렸다 — 창 폭은 스크립트 지정)
            newoff[off] = n * 2 + len(blob)
            offs.append(newoff[off])
            blob += new
        end = n * 2 + len(blob)
        if end + 1 > MSG_LOAD:
            raise SystemExit('⛔ 뱅크 %d  %04X > 적재 한도 %04X' % (b, end + 1, MSG_LOAD))
        body = bytearray(msg.BANK)
        for i, o in enumerate(offs):
            struct.pack_into('<H', body, i * 2, o)
        body[n * 2:end] = blob
        body[end] = 0xCD
        tail = bytes(d[base + msg.BANK - 0x8000 + 0x3000:base + msg.BANK])
        assert not any(tail), '뱅크 %d 0x3000 이후에 데이터가 있다' % b
        d[base:base + msg.BANK] = body
        print('  뱅크 %d  %d줄 · 끝 %04X (원문 %04X) / 한도 %04X' % (b, n, end, t[-1] + len(ss[-1][1]), MSG_LOAD))
    assert len(d) == 262144
    return bytes(d)


# ── SLPS ───────────────────────────────────────────────────────
def name_board(orig, one):
    """SLPS:7 이름 글자판 — 1쪽·2쪽(가나) 칸을 1바이트 한글로, 3쪽은 영숫자·부호만"""
    syl = sorted(one)
    out = bytearray(); page = 0; k = 0
    i = 0
    toks = []
    while i < len(orig):
        c = orig[i]
        if c in msg.ARG1:
            toks.append(orig[i:i + 2]); i += 2
        else:
            toks.append(orig[i:i + 1]); i += 1
    keep3 = set(ASCII.values())
    for t in toks:
        c = t[0]
        if c == 0x08:
            page += 1; out += t; continue
        if c in (0x00, 0x0F) or len(t) > 1:
            out += t; continue
        if page < 2:
            if k < len(syl):
                out += enc_idx(code_of[syl[k]]); k += 1
            else:
                out.append(0x0F)
        else:
            out.append(c if c in keep3 else 0x0F)
    return bytes(out), k


code_of = {}


def build_slps(rs, code, one, pad_stat=99):
    e = bytearray(open(os.path.join(JP, 'SLPS_012.34'), 'rb').read())
    by = {r[0]: r for r in rs}
    tabs = dump.SLPS_TABLES + [(0x070625, None)]
    report = []
    for (base, name), (nb, _) in zip(tabs[:-1], tabs[1:]):
        n = struct.unpack_from('<H', e, base)[0] // 2
        offs = [struct.unpack_from('<H', e, base + k * 2)[0] for k in range(n)]
        ends = [msg.scan_end(bytes(e), base + o) for o in offs]
        outside = [k for k in range(n) if ends[k] > nb or base + offs[k] >= nb]
        limit = min([nb] + [base + offs[k] for k in outside if base + offs[k] < nb])
        blob = bytearray(); pos = {}; newoffs = []
        for k in range(n):
            if k in outside:
                newoffs.append(offs[k]); continue
            rid = '%s:%d' % (name, k)
            r = by[rid]
            kr = by[r[2]][5] if r[2] else r[5]
            if rid == 'SLPS:7':
                b_, used = name_board(bytes(e[base + offs[k]:ends[k]]), one)
                report.append('이름판 한글 %d칸' % used)
            elif kr:
                s = layout(rid, kr, r[3])
                if rid in SMALL_IDS and any(c in code and code[c] >= 240 for c in s):
                    raise SystemExit('⛔ 작은 글꼴 문자열 %s 에 2바이트 음절: %s' % (rid, s))
                if name == 'STAT' and pad_stat:
                    s = stat_pad(s, r[3], pad_stat)
                b_ = encode(s, code)
            else:
                b_ = bytes(e[base + offs[k]:ends[k]])
            key = offs[k]                       # ★원문이 공유하던 곳만 공유한다(내용이 같아도 따로 둔다)
            if key not in pos:
                pos[key] = n * 2 + len(blob)
                blob += b_
            newoffs.append(pos[key])
        if base + n * 2 + len(blob) > limit:
            return None, '%s 구역 초과 %d > %d' % (name, n * 2 + len(blob), limit - base)
        for k, o in enumerate(newoffs):
            struct.pack_into('<H', e, base + k * 2, o)
        e[base + n * 2:limit] = bytes(blob) + b'\x00' * (limit - base - n * 2 - len(blob))
        report.append('%s %d/%d B' % (name, n * 2 + len(blob), limit - base))
    assert len(e) == 512000
    return bytes(e), ' · '.join(report)


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 22), b''):
            h.update(blk)
    return h.hexdigest().upper()


def disc_and_dist(files, install):
    outdir = os.path.join(ROOT, 'work', 'out')
    os.makedirs(outdir, exist_ok=True)
    src = os.path.join(ROMDIR, BIN)
    dst = os.path.join(outdir, BIN)
    assert md5(src) == SRC_MD5, '원본 md5 불일치'
    shutil.copyfile(src, dst)
    for name in files:
        subprocess.run([sys.executable, os.path.join(HERE, 'discfs.py'), dst, '--put', '/' + name,
                        os.path.join(OUT, name)], check=True)
    dmd5 = md5(dst)
    print('패치본 md5', dmd5)
    dist = os.path.join(ROOT, 'dist', 'Chocobo_KR_%s' % VER)
    os.makedirs(dist, exist_ok=True)
    patch = 'Chocobo_KR_%s.xdelta' % VER
    pp = os.path.join(dist, patch)
    if os.path.exists(pp):
        os.remove(pp)
    subprocess.run([XDELTA, '-e', '-9', '-s', src, dst, pp], check=True)
    shutil.copyfile(XDELTA, os.path.join(dist, 'xdelta.exe'))
    pmd5 = md5(pp)
    bat = BAT.replace('@NAME@', BIN).replace('@PATCH@', patch).replace('@SRC@', SRC_MD5.lower()) \
             .replace('@DST@', dmd5.lower()).replace('@VER@', VER)
    open(os.path.join(dist, '패치적용.bat'), 'wb').write(bat.replace('\n', '\r\n').encode('cp949'))
    rd = README.replace('@NAME@', BIN).replace('@SRC@', SRC_MD5).replace('@DST@', dmd5).replace('@VER@', VER)
    open(os.path.join(dist, 'readme.txt'), 'wb').write(rd.replace('\n', '\r\n').encode('cp949'))
    print('배포 %s  (xdelta md5 %s)' % (dist, pmd5))
    if install:
        cue = os.path.join(outdir, BIN[:-4] + '.cue')
        shutil.copyfile(os.path.join(ROMDIR, BIN[:-4] + '.cue'), cue)
        subprocess.run([CHDMAN, 'createcd', '-f', '-i', cue, '-o', FCHD], check=True)
        print('F: 교체', FCHD)
    return dmd5, pmd5


BAT = r'''@echo off
setlocal
set NAME=@NAME@
set PATCH=@PATCH@
set SRCMD5=@SRC@
set DSTMD5=@DST@

echo.
echo  ==============================================
echo    Chocobo no Fushigi na Dungeon ^(PS1 JP^) Korean Patch @VER@
echo  ==============================================
echo.

if not exist "%NAME%" (
  echo  [!] "%NAME%" 파일이 이 폴더에 없습니다.
  echo      원본 .bin 과 같은 폴더에 두고 실행하세요.
  goto END
)
if not exist "%~dp0xdelta.exe" (
  echo  [!] xdelta.exe 가 없습니다. 패치 묶음을 그대로 풀고 실행하세요.
  goto END
)

echo  [1/3] 원본 검사 중...
set HASH=
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%NAME%" MD5') do (
  if not defined HASH set HASH=%%H
)
set HASH=%HASH: =%

if /I "%HASH%"=="%DSTMD5%" (
  echo.
  echo  [!] 이미 이 버전의 한글 패치가 적용된 파일입니다.
  goto END
)
if /I not "%HASH%"=="%SRCMD5%" (
  echo.
  echo  [!] 원본 MD5 가 다릅니다. 패치하지 않고 중단합니다.
  echo      필요 : %SRCMD5%
  echo      현재 : %HASH%
  goto END
)

echo  [2/3] 패치 적용 중... ^(1~2분 걸립니다^)
"%~dp0xdelta.exe" -d -f -s "%NAME%" "%~dp0%PATCH%" "%NAME%.kr"
if errorlevel 1 (
  echo  [!] 패치에 실패했습니다.
  if exist "%NAME%.kr" del "%NAME%.kr"
  goto END
)

echo  [3/3] 결과 검사 중...
set HASH2=
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%NAME%.kr" MD5') do (
  if not defined HASH2 set HASH2=%%H
)
set HASH2=%HASH2: =%

if /I not "%HASH2%"=="%DSTMD5%" (
  echo  [!] 결과 MD5 가 다릅니다. 원본은 그대로 두고 중단합니다.
  del "%NAME%.kr"
  goto END
)

move /y "%NAME%" "%NAME%.bak" >nul
move /y "%NAME%.kr" "%NAME%" >nul
echo.
echo  [OK] 한글 패치 완료. 원본은 "%NAME%.bak" 으로 남겨 두었습니다.

:END
echo.
pause
endlocal
'''

README = '''초코보의 이상한 던전 (PS1 일본판) 한글 패치 @VER@
==========================================

@NAME@ 에 패치하시면 됩니다.

원본md5 : @SRC@
패치md5 : @DST@

입니다.


[ 적용 방법 ]

1. 원본 @NAME@ 과 .cue 를 한 폴더에 둡니다.
   (트랙 1개 · MODE2/2352 · 709,332,624 바이트)
2. 이 패치 묶음을 통째로 그 폴더에 풀고 「패치적용.bat」 을 실행합니다.
3. 배치가 원본 MD5 를 먼저 확인하고, 끝난 뒤 결과 MD5 까지 검사합니다.
4. .cue 는 고치지 않아도 됩니다. 파일 크기도 바뀌지 않습니다.


[ 바뀌는 것 ]

■ 마을·던전 대사 전부, 몬스터 도감, 책(힌트), 메뉴·설정·세이브 화면
■ 아이템·몬스터·기술 이름, 아이템 설명, 속성 부여 문구, 상태 메시지
■ 이름 입력 글자판(한글)


[ 알려진 사항 ]

■ v0.91 : 상점 가격·소지금 옆 그림 글자 「ギル」를 「길」로, 공격이 빗나갈 때 뜨는 「ミス」를 「미스」로 바꾸고, 대사창을 넘어 줄이 밀리던 대사 2곳과 화면 아래 상태 줄이 잘리던 문구를 고쳤습니다.
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', action='store_true')
    ap.add_argument('--install', action='store_true')
    a = ap.parse_args()
    rs = rows()
    code, one = allocate(rs)
    code_of.update(code)
    print('음절 %d종 · 1바이트 %d · 2바이트 %d' % (len(code), len(one), len(code) - len(one)))
    font = build_font(code, one)
    m = build_msg(rs, code)
    for cap in range(24, -1, -1):              # STAT 오른쪽 맞춤 공백 — 구역에 들어가는 만큼
        e, rep = build_slps(rs, code, one, pad_stat=cap)
        if e is not None:
            break
    if e is None:
        raise SystemExit('⛔ ' + rep)
    print('  STAT 맞춤 공백 최대 %d칸' % cap)
    print('SLPS      ' + rep)
    os.makedirs(OUT, exist_ok=True)
    fb = missgfx.apply(open(missgfx.SRC, 'rb').read())   # 데미지 숫자 판 «ミス» 그림 → «미스»
    for name, data in (('FONT.PXL', font), ('MSG.BIN', m), ('SLPS_012.34', e), ('FBDAP.BIN', fb)):
        open(os.path.join(OUT, name), 'wb').write(data)
    io.open(os.path.join(OUT, 'codemap.tsv'), 'w', encoding='utf-8').write(
        ''.join('%s\t%d\t%s\n' % (c, i, enc_idx(i).hex()) for c, i in sorted(code.items(), key=lambda x: x[1])))
    print('→ work/kr/ FONT.PXL · MSG.BIN · SLPS_012.34 · FBDAP.BIN · codemap.tsv')
    if a.disc:
        disc_and_dist(['FONT.PXL', 'MSG.BIN', 'SLPS_012.34', 'FBDAP.BIN'], a.install)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
